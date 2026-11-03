"""Signing in without a password (emailed code), "keep me signed in on this device", and accounts that have no password."""
import time

import pytest
from fastapi.testclient import TestClient

from backend import accounts, config, db

from .test_api import PW, signup

pytestmark = pytest.mark.usefixtures("mailbox")


@pytest.fixture(scope="module")
def app_client():
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "MOCK", True)
    from backend.app import app
    yield app
    mp.undo()


@pytest.fixture(autouse=True)
def quick_codes(monkeypatch):
    monkeypatch.setattr(config, "OTP_RESEND_SECONDS", 0)


def passwordless(app_client, name):
    """A person who signed up the new way: no password, signed out again."""
    c = TestClient(app_client)
    signup(c, name)
    db.run("UPDATE users SET password_hash=NULL WHERE username=?", (name,))
    c.post("/api/auth/logout")
    return c


def sent_code(mailbox, email, purpose="login", wait=2.0):
    """The code endpoint answers at once and sends in the background, so look for the mail for a moment."""
    end = time.time() + wait
    while time.time() < end:
        hits = [m for m in mailbox if m[0] == email and m[2] == purpose]
        if hits:
            return hits[-1][1]
        time.sleep(0.05)
    return None


def test_a_code_signs_you_in(app_client, mailbox):
    c = passwordless(app_client, "code_user1")
    assert c.get("/api/auth/me").status_code == 401
    r = c.post("/api/auth/code/start", json={"identifier": "Code_User1@Example.com"})
    assert r.status_code == 200 and r.json()["ok"] and "email" not in r.json()
    code = sent_code(mailbox, "code_user1@example.com")
    assert code and len(code) == 6
    r = c.post("/api/auth/code/verify", json={"identifier": "code_user1@example.com", "code": f"{code[:3]} {code[3:]}"})
    assert r.status_code == 200 and r.json()["user"]["username"] == "code_user1"
    assert c.get("/api/auth/me").status_code == 200
    c.post("/api/auth/logout")
    assert c.post("/api/auth/code/verify", json={"identifier": "code_user1@example.com", "code": code}).status_code == 400  # a code works once


def test_the_username_works_too_and_goes_to_the_email_on_file(app_client, mailbox):
    c = passwordless(app_client, "code_user2")
    c.post("/api/auth/code/start", json={"identifier": "code_user2"})
    code = sent_code(mailbox, "code_user2@example.com")
    assert code and c.post("/api/auth/code/verify", json={"identifier": "code_user2", "code": code}).status_code == 200


def test_asking_for_a_code_never_reveals_who_has_an_account(app_client, mailbox):
    c = TestClient(app_client)
    n = len(mailbox)
    known = c.post("/api/auth/code/start", json={"identifier": "nobody.here@example.com"})
    assert known.status_code == 200 and known.json()["ok"]
    assert c.post("/api/auth/code/start", json={"identifier": "no_such_user"}).json() == known.json()
    time.sleep(0.3)
    assert len(mailbox) == n  # nothing was sent, and the answer looked the same
    assert c.post("/api/auth/code/verify", json={"identifier": "nobody.here@example.com", "code": "123456"}).status_code == 400


def test_wrong_codes_run_out_then_the_door_closes(app_client, mailbox):
    c = passwordless(app_client, "code_user3")
    c.post("/api/auth/code/start", json={"identifier": "code_user3"})
    code = sent_code(mailbox, "code_user3@example.com")
    bad = "000000" if code != "000000" else "111111"
    for _ in range(4):
        assert c.post("/api/auth/code/verify", json={"identifier": "code_user3", "code": bad}).status_code == 400
    assert c.post("/api/auth/code/verify", json={"identifier": "code_user3", "code": bad}).status_code == 429
    assert c.post("/api/auth/code/verify", json={"identifier": "code_user3", "code": code}).status_code == 400  # five misses kill even the right code


def test_a_disabled_account_gets_no_code(app_client, mailbox):
    c = passwordless(app_client, "code_user4")
    db.run("UPDATE users SET disabled=1 WHERE username='code_user4'")
    n = len(mailbox)
    c.post("/api/auth/code/start", json={"identifier": "code_user4"})
    time.sleep(0.3)
    assert len(mailbox) == n


def test_a_code_cannot_be_used_for_a_different_purpose(app_client, mailbox):
    c = passwordless(app_client, "code_user5")
    c.post("/api/auth/signup/start", json={"email": "code_user5_other@example.com"})
    other = mailbox[-1][1]  # a sign-up code for another address
    assert c.post("/api/auth/code/verify", json={"identifier": "code_user5", "code": other}).status_code == 400


def test_keep_me_signed_in_skips_the_idle_sign_out(app_client, mailbox):
    for remember in (False, True):
        c = passwordless(app_client, f"remember_{int(remember)}")
        c.post("/api/auth/code/start", json={"identifier": f"remember_{int(remember)}"})
        code = sent_code(mailbox, f"remember_{int(remember)}@example.com")
        r = c.post("/api/auth/code/verify", json={"identifier": f"remember_{int(remember)}", "code": code, "remember": remember})
        assert r.status_code == 200
        assert c.get("/api/auth/me").json()["remembered"] is remember
        row = db.one("SELECT expires_at, created_at, remember FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (f"remember_{int(remember)}",))
        days = round((row["expires_at"] - row["created_at"]) / 86400)
        assert row["remember"] == int(remember) and days == (config.REMEMBER_DAYS if remember else config.SESSION_DAYS)
        cookie = r.headers["set-cookie"]
        assert f"Max-Age={(config.REMEMBER_DAYS if remember else config.SESSION_DAYS) * 86400}" in cookie
        db.run("UPDATE sessions SET last_seen=? WHERE user_id=(SELECT id FROM users WHERE username=?)", (time.time() - (config.IDLE_MINUTES + 30) * 60, f"remember_{int(remember)}"))
        got = c.get("/api/auth/me")
        assert (got.status_code == 200) is remember, remember  # two idle hours: the shared-computer sign-in ends, the remembered one stays
        if not remember:
            assert got.json()["detail"]["code"] == "idle"


def test_password_sign_in_can_be_remembered_too(app_client):
    c = TestClient(app_client)
    signup(c, "remember_pw")
    c.post("/api/auth/logout")
    r = c.post("/api/auth/login", json={"username": "remember_pw", "password": PW, "remember": True})
    assert r.status_code == 200 and c.get("/api/auth/me").json()["remembered"] is True


def test_no_password_yet_the_account_still_works_and_can_add_one(app_client, mailbox):
    c = passwordless(app_client, "nopw_user")
    assert c.post("/api/auth/login", json={"username": "nopw_user", "password": PW}).status_code == 401
    c.post("/api/auth/code/start", json={"identifier": "nopw_user"})
    c.post("/api/auth/code/verify", json={"identifier": "nopw_user", "code": sent_code(mailbox, "nopw_user@example.com")})
    assert c.get("/api/auth/me").json()["has_password"] is False
    assert c.post("/api/auth/password", json={"new_password": "short"}).status_code == 400
    assert c.post("/api/auth/password", json={"new_password": PW}).status_code == 200  # nothing to type as the "old" one
    assert c.get("/api/auth/me").status_code == 401  # all sign-ins end, as for any password change
    assert c.post("/api/auth/login", json={"username": "nopw_user", "password": PW}).status_code == 200
    assert c.get("/api/auth/me").json()["has_password"] is True
    assert c.post("/api/auth/password", json={"old_password": "wrong-one", "new_password": "An0ther-pass"}).status_code == 401  # now the old one is needed


def test_a_passwordless_account_can_delete_itself_by_typing_delete(app_client):
    c = passwordless(app_client, "nopw_gone")
    uid = db.one("SELECT id FROM users WHERE username='nopw_gone'")["id"]
    db.run("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen) VALUES ('h-gone', ?, ?, ?, ?)", (uid, time.time(), time.time() + 3600, time.time()))
    token = "tok-gone"
    db.run("UPDATE sessions SET token_hash=? WHERE token_hash='h-gone'", (accounts._token_hash(token),))
    from backend.deps import COOKIE
    c.cookies.set(COOKIE, token)
    assert c.post("/api/me/delete", json={"confirm": "nope"}).status_code == 400
    assert c.post("/api/me/delete", json={"confirm": "DELETE"}).status_code == 200
    assert db.one("SELECT 1 FROM users WHERE id=?", (uid,)) is None
