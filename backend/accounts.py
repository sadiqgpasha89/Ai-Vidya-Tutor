"""Accounts, sessions, roles, email verification (one-time codes), parental consent, class/school membership, data export and erasure."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import date

from . import audit, config, db, otp, store

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
_failures: dict[str, list[float]] = {}  # username -> recent failed-login times


class AccountError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "") -> None:
        super().__init__(message)
        self.status, self.code = status, code


# ---- passwords & tokens ------------------------------------------------------------------------
def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_secret(secret: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, digest = stored.split("$")
    got = hashlib.scrypt(secret.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(got.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_id(prefix: str = "u") -> str:
    return prefix + secrets.token_hex(10)


# ---- users -------------------------------------------------------------------------------------
def public(user: dict | None) -> dict | None:
    if not user:
        return None
    return {k: user[k] for k in ("id", "username", "display_name", "role", "consent", "school_id") if k in user}


def get_user(user_id: str) -> dict | None:
    return db.one("SELECT * FROM users WHERE id=?", (user_id,))


def get_by_username(username: str) -> dict | None:
    return db.one("SELECT * FROM users WHERE username=?", (username.strip().lower(),))


def get_by_email(email: str) -> dict | None:
    return db.one("SELECT * FROM users WHERE lower(email)=? AND email_verified=1", (email.strip().lower(),))


def find_by_identifier(identifier: str) -> dict | None:
    """A person types a username or an email address: whichever it is, find the account."""
    identifier = (identifier or "").strip().lower()
    return get_by_email(identifier) if "@" in identifier else get_by_username(identifier)


def validate_credentials(username: str, password: str) -> str:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise AccountError("Username must be 3-32 characters: letters, digits, dot, dash or underscore.")
    if len(password) < 8 or len(password) > 200:
        raise AccountError("Password must be at least 8 characters.")
    if password.lower() == username or password.lower() in ("password", "12345678", "qwertyui", "password1"):
        raise AccountError("That password is too easy to guess. Choose another.")
    return username


def _check_new_account(username: str, password: str | None, display_name: str, role: str, birth_year: int | None, school_code: str | None, email: str | None) -> dict:
    """Everything that must be true before an account is made. -> the cleaned values."""
    if role not in config.ROLES:
        raise AccountError("Unknown role.")
    username = validate_credentials(username, password) if password is not None else username
    display_name = display_name.strip()[:40]
    if not display_name:
        raise AccountError("Please enter your name.")
    if get_by_username(username):
        raise AccountError("That username is already taken.", 409)
    if email is not None:
        try:
            email = otp.normalize_email(email)
        except otp.OtpError as exc:
            raise AccountError(str(exc)) from exc
        if db.one("SELECT 1 FROM users WHERE lower(email)=?", (email,)):
            raise AccountError("An account with that email address already exists. Sign in instead: we can email you a code.", 409)
    year = date.today().year
    if role == "student":
        if not birth_year or not (year - 25 <= birth_year <= year - 6):
            raise AccountError("Please enter a valid year of birth.")
        consent = "na" if year - birth_year >= config.ADULT_AGE else "pending"
    else:
        consent = "na"
        if role in ("parent", "teacher") and (not birth_year or year - birth_year < config.ADULT_AGE):
            raise AccountError("Parent and teacher accounts are for adults (18 or older).")
    school_id = None
    if school_code:
        school = db.one("SELECT id FROM schools WHERE code=?", (school_code.strip().upper(),))
        if not school:
            raise AccountError("School code not found.", 404)
        school_id = school["id"]
    return {"username": username, "display_name": display_name, "role": role, "birth_year": birth_year, "consent": consent, "school_id": school_id, "email": email}


def _insert_user(c: dict, password_hash: str, profile: dict | None, email_verified: bool, ip: str) -> dict:
    uid = new_id()
    db.run("INSERT INTO users (id, username, display_name, role, password_hash, birth_year, consent, school_id, email, email_verified, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (uid, c["username"], c["display_name"], c["role"], password_hash, c["birth_year"], c["consent"], c["school_id"], c["email"], int(email_verified), time.time()))
    if c["role"] == "student":
        p = profile or {}
        store.upsert_student(uid, c["display_name"], int(p.get("grade", 9)), p.get("language", "en"), p.get("level", "standard"), p.get("board", "CBSE"))
    audit.log(uid, "signup", c["role"], {"consent": c["consent"], "email_verified": email_verified}, ip)
    return get_user(uid)


def create_user(username: str, password: str, display_name: str, role: str = "student", birth_year: int | None = None,
                school_code: str | None = None, profile: dict | None = None, ip: str = "", email: str | None = None) -> dict:
    """Make an account directly (scripts, tests, the first administrator). People signing up on the website go through start_signup / finish_signup,
    which prove they own the email address first. Students under 18 start with consent 'pending'."""
    c = _check_new_account(username, password, display_name, role, birth_year, school_code, email)
    return _insert_user(c, hash_secret(password), profile, False, ip)


# ---- signing up: email, then the code, then a short form ---------------------------------------
def make_username(email: str) -> str:
    """People sign in with their email, so the username is only a handle: take it from the part before the @ and make it unique."""
    base = re.sub(r"[^a-z0-9._-]+", ".", email.split("@")[0].lower()).strip("._-")[:24]
    base = base if len(base) >= 3 and base[0].isalnum() else (base + "user")[:24].lstrip("._-") or "user"
    name = base
    while get_by_username(name):
        name = f"{base[:24]}{secrets.randbelow(10000):04d}"
    return name


def start_signup(email: str) -> dict:
    """Step 1: email a six-digit code to the address. Nothing is created yet.
    -> {"pending": id, "email": masked, "delivery": "email"|"log", "resend_seconds": n}"""
    try:
        email = otp.normalize_email(email)
    except otp.OtpError as exc:
        raise AccountError(str(exc)) from exc
    if db.one("SELECT 1 FROM users WHERE lower(email)=?", (email,)):
        raise AccountError("An account with that email address already exists. Sign in instead: we can email you a code.", 409)
    try:
        oid, delivery = otp.issue("signup", email, None, None)
    except otp.OtpError as exc:
        raise AccountError(str(exc), exc.status) from exc
    return {"pending": oid, "email": otp.mask(email), "delivery": delivery, "resend_seconds": config.OTP_RESEND_SECONDS}


def resend_signup(pending: str) -> dict:
    row = db.one("SELECT email FROM email_otps WHERE id=? AND purpose='signup'", (pending,))
    if not row:
        raise AccountError("This sign-up has expired. Please start again.", 404)
    try:
        _, delivery = otp.issue("signup", row["email"], None, None, otp_id=pending)
    except otp.OtpError as exc:
        raise AccountError(str(exc), exc.status) from exc
    return {"pending": pending, "email": otp.mask(row["email"]), "delivery": delivery, "resend_seconds": config.OTP_RESEND_SECONDS}


def verify_signup(pending: str, code: str) -> dict:
    """Step 2: the code from the email. -> {"ticket": proof for step 3, "email": masked}"""
    try:
        got = otp.check(code, pending, "signup")
    except otp.OtpError as exc:
        raise AccountError(str(exc), exc.status) from exc
    return {"ticket": otp.make_ticket(got["email"]), "email": otp.mask(got["email"])}


def finish_signup(ticket: str, display_name: str, role: str = "student", birth_year: int | None = None, school_code: str | None = None,
                  profile: dict | None = None, ip: str = "") -> dict:
    """Step 3: who they are. The email was proven in step 2, so there is no password: the next sign-in is another emailed code (a password can be added in Settings)."""
    try:
        email = otp.ticket_email(ticket)
    except otp.OtpError as exc:
        raise AccountError(str(exc), exc.status) from exc
    c = _check_new_account(make_username(email), None, display_name, role, birth_year, school_code, email)
    user = _insert_user(c, None, profile, True, ip)
    otp.burn_ticket(ticket)
    return user


def ensure_admin() -> None:
    """Create the bootstrap admin from TEACHER_ADMIN_USER / TEACHER_ADMIN_PASSWORD if it does not exist."""
    if not (config.ADMIN_USER and config.ADMIN_PASSWORD) or get_by_username(config.ADMIN_USER):
        return
    uid = new_id()
    db.run("INSERT INTO users (id, username, display_name, role, password_hash, consent, created_at) VALUES (?,?,?,?,?,?,?)",
           (uid, config.ADMIN_USER.lower(), "Administrator", "admin", hash_secret(config.ADMIN_PASSWORD), "na", time.time()))
    audit.log(uid, "admin_bootstrap", config.ADMIN_USER)


def anonymous_user(anon_id: str) -> dict:
    """AUTH=off: a password-less student profile tied to a random browser cookie."""
    username = "anon-" + anon_id[:24].lower()
    user = get_by_username(username)
    if user:
        return user
    uid = new_id()
    db.run("INSERT INTO users (id, username, display_name, role, consent, created_at) VALUES (?,?,?,?,?,?)",
           (uid, username, "Student", "student", "na", time.time()))
    store.upsert_student(uid, "Student", 9, "en", "standard", "CBSE")
    return get_user(uid)


# ---- login / sessions --------------------------------------------------------------------------
def _throttle(username: str) -> None:
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < 600]
    _failures[username] = recent
    if len(recent) >= 8:
        raise AccountError("Too many wrong tries. Wait ten minutes, or ask for an emailed code.", 429)


def login(username: str, password: str, user_agent: str = "", ip: str = "", remember: bool = False) -> tuple[dict, str]:
    username = username.strip().lower()
    _throttle(username)
    user = find_by_identifier(username)
    # Verify even when the user is unknown so response time does not reveal which usernames exist.
    ok = check_secret(password, user["password_hash"] if user else hash_secret("x"))
    if not user or not ok or user["disabled"]:
        _failures.setdefault(username, []).append(time.time())
        audit.log(user["id"] if user else None, "login_failed", username, "", ip)
        raise AccountError("Wrong username or password. No password yet? Ask for an emailed code instead.", 401)
    _failures.pop(username, None)
    return user, start_session(user["id"], user_agent, ip, remember)


def start_login_code(identifier: str) -> None:
    """Email a sign-in code to whoever owns this username or email address. Says nothing about whether such an account exists."""
    user = find_by_identifier(identifier)
    if not user or user["disabled"] or not user.get("email") or not user["email_verified"]:
        return
    try:
        otp.issue("login", user["email"], user["id"])
    except otp.OtpError:
        pass  # asking too often or the mail server refused: the person sees the same message either way


def login_with_code(identifier: str, code: str, user_agent: str = "", ip: str = "", remember: bool = False) -> tuple[dict, str]:
    identifier = (identifier or "").strip().lower()
    _throttle(identifier)
    user = find_by_identifier(identifier)
    if not user or user["disabled"]:
        _failures.setdefault(identifier, []).append(time.time())
        audit.log(user["id"] if user else None, "login_failed", identifier, "", ip)
        raise AccountError("That code is not right or has expired. Ask for a new one.", 400)
    try:
        otp.check(code, None, "login", user["id"])
    except otp.OtpError as exc:
        _failures.setdefault(identifier, []).append(time.time())
        audit.log(user["id"], "login_failed", identifier, "", ip)
        raise AccountError(str(exc), exc.status) from exc
    _failures.pop(identifier, None)
    return user, start_session(user["id"], user_agent, ip, remember)


def start_session(user_id: str, user_agent: str = "", ip: str = "", remember: bool = False) -> str:
    """`remember`: the person said this is their own device. The sign-in then lasts REMEMBER_DAYS and is not ended by the idle limit."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    days = config.REMEMBER_DAYS if remember else config.SESSION_DAYS
    db.run("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, user_agent, last_seen, remember) VALUES (?,?,?,?,?,?,?)",
           (_token_hash(token), user_id, now, now + days * 86400, user_agent[:200], now, int(remember)))
    db.run("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
    audit.log(user_id, "login", "", "", ip)
    return token


def session_user(token: str | None) -> tuple[dict | None, str]:
    """-> (user, why): why is "" when the session is good, "idle" when it lapsed from inactivity, else "none"."""
    return _session(token)[:2]


def _session(token: str | None) -> tuple[dict | None, str, bool]:
    if not token:
        return None, "none", False
    h, now = _token_hash(token), time.time()
    row = db.one("SELECT user_id, expires_at, last_seen, created_at, remember FROM sessions WHERE token_hash=?", (h,))
    if not row or row["expires_at"] < now:
        return None, "none", False
    seen = row["last_seen"] or row["created_at"] or now
    if not row["remember"] and now - seen > config.IDLE_MINUTES * 60:
        db.run("DELETE FROM sessions WHERE token_hash=?", (h,))
        return None, "idle", False
    user = get_user(row["user_id"])
    if not user or user["disabled"]:
        return None, "none", False
    if now - seen > 30:  # no need to write on every request
        db.run("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, h))
    return user, "", bool(row["remember"])


def is_remembered(token: str | None) -> bool:
    return _session(token)[2]


def user_for_token(token: str | None) -> dict | None:
    return session_user(token)[0]


def logout(token: str | None, everywhere_for: str | None = None) -> None:
    if token:
        db.run("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
    if everywhere_for:
        db.run("DELETE FROM sessions WHERE user_id=?", (everywhere_for,))


def change_password(user: dict, old: str, new: str) -> None:
    """Change the password, or set the first one on an account that signs in with emailed codes (nothing to type as the old one)."""
    if user["password_hash"] and not check_secret(old, user["password_hash"]):
        raise AccountError("Current password is wrong.", 401)
    validate_credentials(user["username"], new)
    db.run("UPDATE users SET password_hash=? WHERE id=?", (hash_secret(new), user["id"]))
    db.run("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    audit.log(user["id"], "password_changed")


def start_reset(identifier: str) -> None:
    """Email a code to whoever owns this username or email address. Says nothing about whether such an account exists."""
    user = find_by_identifier(identifier)
    if not user or user["disabled"] or not user.get("email") or not user["email_verified"]:
        return
    try:
        otp.issue("reset", user["email"], user["id"])
    except otp.OtpError:
        pass  # asking too often or the mail server refused: the person sees the same message either way


def reset_with_code(identifier: str, code: str, new_password: str, ip: str = "") -> None:
    identifier = (identifier or "").strip().lower()
    _throttle(identifier)
    user = find_by_identifier(identifier)
    bad = AccountError("That code is not right or has expired. Ask for a new one.", 400)
    if not user:
        _failures.setdefault(identifier, []).append(time.time())
        raise bad
    try:
        otp.check(code, None, "reset", user["id"])
    except otp.OtpError as exc:
        _failures.setdefault(identifier, []).append(time.time())
        raise AccountError(str(exc), exc.status) from exc
    validate_credentials(user["username"], new_password)
    db.run("UPDATE users SET password_hash=? WHERE id=?", (hash_secret(new_password), user["id"]))
    db.run("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    db.run("DELETE FROM email_otps WHERE user_id=?", (user["id"],))
    _failures.pop(identifier, None)
    audit.log(user["id"], "password_reset_email", "", "", ip)


def start_email(user: dict, email: str, password: str = "") -> dict:
    """Add or change the email address of a signed-in account (accounts made before email codes existed have none). Changing an existing one needs the password."""
    if user.get("email") and user["password_hash"] and not check_secret(password, user["password_hash"]):
        raise AccountError("Please type your current password to change your email address.", 401)
    try:
        email = otp.normalize_email(email)
    except otp.OtpError as exc:
        raise AccountError(str(exc)) from exc
    other = db.one("SELECT id FROM users WHERE lower(email)=?", (email,))
    if other and other["id"] != user["id"]:
        raise AccountError("An account with that email address already exists.", 409)
    try:
        _, delivery = otp.issue("email", email, user["id"], {"email": email})
    except otp.OtpError as exc:
        raise AccountError(str(exc), exc.status) from exc
    return {"email": otp.mask(email), "delivery": delivery, "resend_seconds": config.OTP_RESEND_SECONDS}


def verify_email(user: dict, code: str) -> dict:
    try:
        got = otp.check(code, None, "email", user["id"])
    except otp.OtpError as exc:
        raise AccountError(str(exc), exc.status) from exc
    email = got["payload"]["email"]
    if db.one("SELECT 1 FROM users WHERE lower(email)=? AND id<>?", (email, user["id"])):
        raise AccountError("An account with that email address already exists.", 409)
    db.run("UPDATE users SET email=?, email_verified=1 WHERE id=?", (email, user["id"]))
    audit.log(user["id"], "email_verified")
    return get_user(user["id"])


def admin_reset_password(actor: dict, target_id: str, new_password: str) -> None:
    target = get_user(target_id)
    if not target or not can_manage(actor, target_id):
        raise AccountError("Not allowed.", 403)
    validate_credentials(target["username"], new_password)
    db.run("UPDATE users SET password_hash=? WHERE id=?", (hash_secret(new_password), target_id))
    db.run("DELETE FROM sessions WHERE user_id=?", (target_id,))
    audit.log(actor["id"], "password_reset_by_admin", target_id)


# ---- consent & parent links --------------------------------------------------------------------
def make_link_code(student_id: str) -> str:
    code = secrets.token_hex(4).upper()
    db.run("INSERT INTO link_codes (code, student_id, expires_at) VALUES (?,?,?)", (code, student_id, time.time() + 7 * 86400))
    return code


def link_child(parent: dict, code: str, ip: str = "") -> dict:
    """A parent enters the child's code: links them and records consent."""
    row = db.one("SELECT * FROM link_codes WHERE code=?", (code.strip().upper(),))
    if not row or row["expires_at"] < time.time():
        raise AccountError("That code is wrong or has expired. Ask your child to show a fresh one.", 404)
    sid = row["student_id"]
    db.run("INSERT OR IGNORE INTO parent_links (parent_id, student_id, created_at) VALUES (?,?,?)", (parent["id"], sid, time.time()))
    db.run("DELETE FROM link_codes WHERE code=?", (row["code"],))
    db.run("INSERT INTO consents (student_id, parent_id, notice_version, action, method, created_at) VALUES (?,?,?,?,?,?)",
           (sid, parent["id"], config.NOTICE_VERSION, "granted", "parent_code", time.time()))
    db.run("UPDATE users SET consent='granted' WHERE id=? AND consent IN ('pending','revoked')", (sid,))
    audit.log(parent["id"], "consent_granted", sid, {"notice": config.NOTICE_VERSION}, ip)
    return get_user(sid)


def revoke_consent(parent: dict, student_id: str) -> None:
    if not is_parent_of(parent["id"], student_id):
        raise AccountError("Not allowed.", 403)
    db.run("INSERT INTO consents (student_id, parent_id, notice_version, action, method, created_at) VALUES (?,?,?,?,?,?)",
           (student_id, parent["id"], config.NOTICE_VERSION, "revoked", "parent", time.time()))
    db.run("UPDATE users SET consent='revoked' WHERE id=?", (student_id,))
    db.run("DELETE FROM sessions WHERE user_id=?", (student_id,))
    audit.log(parent["id"], "consent_revoked", student_id)


def is_parent_of(parent_id: str, student_id: str) -> bool:
    return bool(db.one("SELECT 1 FROM parent_links WHERE parent_id=? AND student_id=?", (parent_id, student_id)))


def children_of(parent_id: str) -> list[dict]:
    return db.all("SELECT u.id, u.display_name, u.username, u.consent FROM parent_links p JOIN users u ON u.id=p.student_id WHERE p.parent_id=?", (parent_id,))


# ---- who may see whom --------------------------------------------------------------------------
def can_view_student(viewer: dict, student_id: str) -> bool:
    if viewer["id"] == student_id or viewer["role"] == "admin":
        return True
    if viewer["role"] == "parent":
        return is_parent_of(viewer["id"], student_id)
    if viewer["role"] == "teacher":
        return bool(db.one("SELECT 1 FROM class_members m JOIN classes c ON c.id=m.class_id WHERE m.student_id=? AND c.teacher_id=?", (student_id, viewer["id"])))
    if viewer["role"] == "school_admin" and viewer.get("school_id"):
        student = get_user(student_id)
        return bool(student and student.get("school_id") == viewer["school_id"])
    return False


def can_manage(actor: dict, target_id: str) -> bool:
    if actor["role"] == "admin":
        return True
    if actor["role"] == "parent":
        return is_parent_of(actor["id"], target_id)
    target = get_user(target_id)
    return bool(actor["role"] == "school_admin" and target and target.get("school_id") == actor.get("school_id") and actor.get("school_id"))


# ---- data export & erasure ---------------------------------------------------------------------
_PER_STUDENT = ["students", "progress", "signals", "revision", "activity", "chat_messages", "boards", "notes", "highlights", "bookmarks",
                "mistakes", "card_state", "xp_events", "badges", "feedback", "student_memory", "practice_items", "viva_sessions", "tests",
                "assignment_status", "class_members", "consents", "custom_topics", "study_notes", "daily_sets", "answer_attempts", "doubts"]
_ID_COL = {"students": "id", "consents": "student_id"}


def export_data(user_id: str) -> dict:
    out: dict = {"exported_at": time.time(), "account": public(get_user(user_id))}
    user = get_user(user_id) or {}
    out["account"]["birth_year"] = user.get("birth_year")
    for table in _PER_STUDENT:
        col = _ID_COL.get(table, "student_id")
        out[table] = db.all(f"SELECT * FROM {table} WHERE {col}=?", (user_id,))
    out["doubt_messages"] = db.all("SELECT m.* FROM doubt_messages m JOIN doubts d ON d.id=m.doubt_id WHERE d.student_id=?", (user_id,))
    out["reports"] = db.all("SELECT * FROM reports WHERE student_id=?", (user_id,))
    out["notifications"] = db.all("SELECT * FROM notifications WHERE user_id=?", (user_id,))
    out["parent_links"] = db.all("SELECT * FROM parent_links WHERE student_id=? OR parent_id=?", (user_id, user_id))
    out["library_docs"] = db.all("SELECT id, title, filename, pages, created_at FROM library_docs WHERE owner_id=?", (user_id,))
    return json.loads(json.dumps(out, default=str))


def delete_account(user_id: str, actor_id: str | None = None, ip: str = "") -> None:
    """Erase the account and everything tied to it. The audit trail keeps only that an erasure happened."""
    from . import mytopics
    mytopics.delete_all(user_id)  # their own topics, and the lessons written for them
    db.run("DELETE FROM doubt_messages WHERE doubt_id IN (SELECT id FROM doubts WHERE student_id=?)", (user_id,))
    db.run("DELETE FROM worksheets WHERE created_by=?", (user_id,))
    for table in _PER_STUDENT:
        col = _ID_COL.get(table, "student_id")
        db.run(f"DELETE FROM {table} WHERE {col}=?", (user_id,))
    docs = db.all("SELECT id FROM library_docs WHERE owner_id=?", (user_id,))
    for d in docs:
        db.run("DELETE FROM library_chunks WHERE doc_id=?", (d["id"],))
    db.run("DELETE FROM library_docs WHERE owner_id=?", (user_id,))
    for table, col in (("reports", "student_id"), ("notifications", "user_id"), ("push_subs", "user_id"), ("contacts", "user_id"),
                       ("sessions", "user_id"), ("usage", "user_id"), ("events", "user_id"), ("link_codes", "student_id")):
        db.run(f"DELETE FROM {table} WHERE {col}=?", (user_id,))
    db.run("DELETE FROM parent_links WHERE student_id=? OR parent_id=?", (user_id, user_id))
    db.run("DELETE FROM email_otps WHERE user_id=?", (user_id,))
    db.run("UPDATE audit_log SET actor_id=NULL, detail='' WHERE actor_id=? OR target=?", (user_id, user_id))
    db.run("DELETE FROM users WHERE id=?", (user_id,))
    audit.log(actor_id, "account_erased", hashlib.sha256(user_id.encode()).hexdigest()[:12], "", ip)
