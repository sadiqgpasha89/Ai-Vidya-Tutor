"""One-time email codes: six digits, valid for a few minutes, usable once, with limits on guessing and on how often a code can be asked for."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time

from . import config, db, notify

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
MAX_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 5


class OtpError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email) or ".." in email:
        raise OtpError("Please enter a valid email address, for example name@example.com.")
    return email


def mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}{'*' * max(1, min(len(name) - 1, 5))}@{domain}"


def _hash(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def issue(purpose: str, email: str, user_id: str | None = None, payload: dict | None = None, otp_id: str | None = None) -> tuple[str, str]:
    """Make (or, with otp_id, re-send) a code and email it. -> (id, delivery); `delivery` is "email" or "log"."""
    now = time.time()
    prev = db.one("SELECT * FROM email_otps WHERE id=?", (otp_id,)) if otp_id else None
    if not prev:
        prev = db.one("SELECT * FROM email_otps WHERE email=? AND purpose=? ORDER BY created_at DESC", (email, purpose))
    if prev:
        wait = prev["last_sent"] + config.OTP_RESEND_SECONDS - now
        if wait > 0:
            raise OtpError(f"Please wait {int(wait) + 1} seconds before asking for another code.", 429)
        sends = prev["sends"] + 1 if now - prev["created_at"] < 3600 else 1
        if sends > MAX_SENDS_PER_HOUR:
            raise OtpError("Too many codes were requested for this email address. Please try again in an hour.", 429)
        payload = payload if payload is not None else json.loads(prev["payload"] or "null")
        db.run("DELETE FROM email_otps WHERE id=?", (prev["id"],))
    else:
        sends = 1
    code, salt, oid = f"{secrets.randbelow(10**6):06d}", secrets.token_hex(8), otp_id or secrets.token_urlsafe(16)
    db.run("INSERT INTO email_otps (id, purpose, email, user_id, code_hash, salt, payload, sends, created_at, last_sent, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (oid, purpose, email, user_id, _hash(code, salt), salt, json.dumps(payload) if payload is not None else None, sends, prev["created_at"] if prev and sends > 1 else now, now, now + config.OTP_MINUTES * 60))
    try:
        delivery = notify.send_code(email, code, purpose)
    except Exception as exc:  # noqa: BLE001 - the mail server said no: nothing was sent, so do not leave a code nobody has
        db.run("DELETE FROM email_otps WHERE id=?", (oid,))
        notify.log.warning(f"could not send a code to {mask(email)}: {exc}")
        raise OtpError("We could not send the email right now. Please check the address and try again in a moment.", 503) from exc
    return oid, delivery


def check(code: str, otp_id: str | None = None, purpose: str = "", user_id: str | None = None) -> dict:
    """Use up a code. -> {"email", "user_id", "payload"}. Wrong codes count against 5 tries; the code then dies."""
    row = db.one("SELECT * FROM email_otps WHERE id=?", (otp_id,)) if otp_id else db.one("SELECT * FROM email_otps WHERE user_id=? AND purpose=? ORDER BY created_at DESC", (user_id, purpose))
    if not row or (purpose and row["purpose"] != purpose):
        raise OtpError("That code is not valid any more. Ask for a new one.", 400)
    if row["expires_at"] < time.time():
        db.run("DELETE FROM email_otps WHERE id=?", (row["id"],))
        raise OtpError("That code has expired. Ask for a new one.", 400)
    if row["attempts"] >= MAX_ATTEMPTS:
        db.run("DELETE FROM email_otps WHERE id=?", (row["id"],))
        raise OtpError("Too many wrong tries. Ask for a new code.", 429)
    good = hmac.compare_digest(_hash(re.sub(r"\D", "", code or ""), row["salt"]), row["code_hash"])
    if not good:
        db.run("UPDATE email_otps SET attempts=attempts+1 WHERE id=?", (row["id"],))
        left = MAX_ATTEMPTS - row["attempts"] - 1
        if left <= 0:
            db.run("DELETE FROM email_otps WHERE id=?", (row["id"],))
            raise OtpError("That code is wrong. Too many wrong tries - ask for a new code.", 429)
        raise OtpError(f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.", 400)
    db.run("DELETE FROM email_otps WHERE id=?", (row["id"],))
    return {"email": row["email"], "user_id": row["user_id"], "payload": json.loads(row["payload"] or "null")}


TICKET_MINUTES = 30


def make_ticket(email: str) -> str:
    """Proof that this email address was verified a moment ago: the sign-up form's last step presents it. -> the ticket (also its row id)."""
    tid, now = secrets.token_urlsafe(24), time.time()
    db.run("INSERT INTO email_otps (id, purpose, email, user_id, code_hash, salt, payload, sends, created_at, last_sent, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (tid, "ticket", email, None, "-", "-", None, 1, now, now, now + TICKET_MINUTES * 60))
    return tid


def ticket_email(ticket: str) -> str:
    """-> the verified address a ticket stands for, without using the ticket up (so a form with a typo can be corrected and sent again)."""
    row = db.one("SELECT email, expires_at FROM email_otps WHERE id=? AND purpose='ticket'", (ticket or "",))
    if not row or row["expires_at"] < time.time():
        raise OtpError("Your email check has expired. Please start again.", 400)
    return row["email"]


def burn_ticket(ticket: str) -> None:
    db.run("DELETE FROM email_otps WHERE id=? AND purpose='ticket'", (ticket,))


def purge_expired() -> None:
    db.run("DELETE FROM email_otps WHERE expires_at < ?", (time.time() - 3600,))
