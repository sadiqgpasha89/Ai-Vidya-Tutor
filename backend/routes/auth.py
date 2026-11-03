"""Sign-up, sign-in, consent, profile, privacy (export/delete), notifications."""
from __future__ import annotations

import io
import json
import threading
import zipfile
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .. import accounts, audit, config, db, learning, notify, otp, store
from ..deps import COOKIE, client_ip, current_user, roles, set_session_cookie, student_user
from ..ratelimit import limiter

router = APIRouter(prefix="/api")
Language = Literal[tuple(config.LANGUAGES)]  # type: ignore[valid-type]
Level = Literal[tuple(config.LEVELS)]  # type: ignore[valid-type]


def _auth_limit(request: Request) -> None:
    ok, wait = limiter.allow(f"auth:{client_ip(request)}", config.RATE_AUTH)
    if not ok:
        raise HTTPException(429, f"Too many attempts. Try again in {int(wait) + 1} seconds.", headers={"Retry-After": str(int(wait) + 1)})


def _wrap(fn):
    try:
        return fn()
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, str(exc))


class Profile(BaseModel):
    grade: int = 9
    language: Language = "en"
    level: Level = "standard"
    board: str = "CBSE"
    stream: str = ""
    track: str = ""
    goal: str = "boards"
    exam_date: str = ""
    daily_minutes: int = Field(30, ge=5, le=300)


class SignupFinishIn(BaseModel):
    ticket: str = Field(max_length=64)
    display_name: str = Field(min_length=1, max_length=40)
    role: Literal["student", "parent", "teacher"] = "student"
    birth_year: int | None = None
    school_code: str | None = None
    accept_terms: bool = False
    remember: bool = False
    profile: Profile | None = None


def _clean_profile(p: Profile) -> dict:
    d = p.model_dump()
    if d["grade"] not in config.GRADES:
        raise HTTPException(400, "Grade must be 7-12")
    d["board"] = d["board"] if d["board"] in config.BOARDS else "CBSE"
    d["stream"] = d["stream"] if d["stream"] in config.STREAMS else ""
    d["track"] = d["track"].upper() if d["track"].upper() in ("CS", "IP") else ""
    d["goal"] = d["goal"] if d["goal"] in config.GOALS else "boards"
    if d["exam_date"]:
        from datetime import date
        try:
            date.fromisoformat(d["exam_date"])
        except ValueError:
            d["exam_date"] = ""
    return d


@router.get("/auth/config")
def auth_config():
    return {"auth": config.AUTH, "adult_age": config.ADULT_AGE, "notice_version": config.NOTICE_VERSION, "email": notify.email_ready(), "otp_minutes": config.OTP_MINUTES, "remember_days": config.REMEMBER_DAYS}


class EmailOnlyIn(BaseModel):
    email: str = Field(max_length=254)


@router.post("/auth/signup/start")
def signup_start(body: EmailOnlyIn, request: Request):
    """Step 1: email a six-digit code. No account exists yet."""
    _auth_limit(request)
    if config.AUTH == "off":
        raise HTTPException(400, "Accounts are disabled on this server")
    return _wrap(lambda: accounts.start_signup(body.email))


class PendingIn(BaseModel):
    pending: str = Field(max_length=64)


@router.post("/auth/signup/resend")
def signup_resend(body: PendingIn, request: Request):
    _auth_limit(request)
    return _wrap(lambda: accounts.resend_signup(body.pending))


class VerifyIn(BaseModel):
    pending: str = Field(max_length=64)
    code: str = Field(max_length=12)


@router.post("/auth/signup/verify")
def signup_verify(body: VerifyIn, request: Request):
    """Step 2: the code from the email. Proves the address; the account is made in step 3."""
    _auth_limit(request)
    return _wrap(lambda: accounts.verify_signup(body.pending, body.code))


@router.post("/auth/signup/finish")
def signup_finish(body: SignupFinishIn, request: Request, response: Response):
    """Step 3: name, birth year and grade. Creates the account and signs the person in."""
    _auth_limit(request)
    if not body.accept_terms:
        raise HTTPException(400, "Please accept the terms and privacy notice to continue.")
    prof = _clean_profile(body.profile) if body.profile else None
    user = _wrap(lambda: accounts.finish_signup(body.ticket, body.display_name, body.role, body.birth_year, body.school_code, prof, client_ip(request)))
    token = accounts.start_session(user["id"], request.headers.get("user-agent", ""), client_ip(request), body.remember)
    set_session_cookie(response, token, body.remember)
    out = {"user": accounts.public(user)}
    if user["role"] == "student" and user["consent"] == "pending":
        out["link_code"] = accounts.make_link_code(user["id"])
    return out


class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = False


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    _auth_limit(request)
    user, token = _wrap(lambda: accounts.login(body.username, body.password, request.headers.get("user-agent", ""), client_ip(request), body.remember))
    set_session_cookie(response, token, body.remember)
    return {"user": accounts.public(user)}


class CodeStartIn(BaseModel):
    identifier: str = Field(max_length=254)


@router.post("/auth/code/start")
def code_start(body: CodeStartIn, request: Request):
    """Sign in without a password, step 1: email a code to the address on the account. The answer never says whether the account exists."""
    _auth_limit(request)
    if config.AUTH == "off":
        raise HTTPException(400, "Accounts are disabled on this server")
    threading.Thread(target=accounts.start_login_code, args=(body.identifier,), daemon=True, name="login-code").start()  # same speed whether or not the account exists
    return {"ok": True, "minutes": config.OTP_MINUTES, "resend_seconds": config.OTP_RESEND_SECONDS, "delivery": "email" if notify.email_ready() else "log"}


class CodeVerifyIn(BaseModel):
    identifier: str = Field(max_length=254)
    code: str = Field(max_length=12)
    remember: bool = False


@router.post("/auth/code/verify")
def code_verify(body: CodeVerifyIn, request: Request, response: Response):
    """Step 2: the code from the email signs the person in."""
    _auth_limit(request)
    user, token = _wrap(lambda: accounts.login_with_code(body.identifier, body.code, request.headers.get("user-agent", ""), client_ip(request), body.remember))
    set_session_cookie(response, token, body.remember)
    return {"user": accounts.public(user)}


@router.post("/auth/logout")
def logout(request: Request, response: Response, all_devices: bool = False, user: dict = Depends(current_user)):
    accounts.logout(request.cookies.get(COOKIE), user["id"] if all_devices else None)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/ping")
def ping(user: dict = Depends(current_user)):
    """The page calls this while the student is active but not asking for anything (reading), so the idle sign-out does not fire."""
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, user: dict = Depends(current_user)):
    out = {"user": accounts.public(user), "unread": notify.unread_count(user["id"]), "email": otp.mask(user["email"]) if user.get("email") else None, "email_verified": bool(user.get("email_verified")),
           "has_password": bool(user.get("password_hash")), "remembered": accounts.is_remembered(request.cookies.get(COOKIE))}
    if user["role"] == "student":
        out["profile"] = store.get_student(user["id"])
        if user["consent"] == "pending":
            out["link_code"] = accounts.make_link_code(user["id"])
    if user["role"] == "parent":
        out["children"] = accounts.children_of(user["id"])
    return out


class PasswordIn(BaseModel):
    old_password: str = ""
    new_password: str


@router.post("/auth/password")
def change_password(body: PasswordIn, user: dict = Depends(current_user)):
    _wrap(lambda: accounts.change_password(user, body.old_password, body.new_password))
    return {"ok": True}


class ResetStartIn(BaseModel):
    identifier: str = Field(max_length=254)


@router.post("/auth/reset/start")
def reset_start(body: ResetStartIn, request: Request):
    """Forgot password, step 1: email a code to the address on the account. The answer never says whether the account exists."""
    _auth_limit(request)
    threading.Thread(target=accounts.start_reset, args=(body.identifier,), daemon=True, name="reset-code").start()  # same speed whether or not the account exists
    return {"ok": True, "minutes": config.OTP_MINUTES}


class ResetCodeIn(BaseModel):
    identifier: str = Field(max_length=254)
    code: str = Field(max_length=12)
    new_password: str


@router.post("/auth/reset/verify")
def reset_verify(body: ResetCodeIn, request: Request):
    _auth_limit(request)
    _wrap(lambda: accounts.reset_with_code(body.identifier, body.code, body.new_password, client_ip(request)))
    return {"ok": True}


class EmailIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = ""


@router.post("/auth/email/start")
def email_start(body: EmailIn, request: Request, user: dict = Depends(current_user)):
    """Add or change the email address on the account you are signed in to: a code is sent to it."""
    _auth_limit(request)
    return _wrap(lambda: accounts.start_email(user, body.email, body.password))


class CodeIn(BaseModel):
    code: str = Field(max_length=12)


@router.post("/auth/email/verify")
def email_verify(body: CodeIn, request: Request, user: dict = Depends(current_user)):
    _auth_limit(request)
    updated = _wrap(lambda: accounts.verify_email(user, body.code))
    return {"user": accounts.public(updated), "email": otp.mask(updated["email"]), "email_verified": True}


class LinkIn(BaseModel):
    code: str


@router.post("/parent/link")
def parent_link(body: LinkIn, request: Request, user: dict = Depends(roles("parent"))):
    child = _wrap(lambda: accounts.link_child(user, body.code, client_ip(request)))
    return {"child": {"id": child["id"], "display_name": child["display_name"]}}


@router.post("/parent/revoke/{student_id}")
def parent_revoke(student_id: str, user: dict = Depends(roles("parent"))):
    _wrap(lambda: accounts.revoke_consent(user, student_id))
    return {"ok": True}


class ResetIn(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password")
def reset_other(user_id: str, body: ResetIn, user: dict = Depends(roles("parent", "school_admin"))):
    _wrap(lambda: accounts.admin_reset_password(user, user_id, body.new_password))
    return {"ok": True}


# ---- profile & privacy -------------------------------------------------------------------------
@router.put("/me/profile")
def update_profile(body: Profile, user: dict = Depends(student_user)):
    p = _clean_profile(body)
    updated = store.upsert_student(user["id"], user["name"], p["grade"], p["language"], p["level"], p["board"], stream=p["stream"], track=p["track"],
                                   goal=p["goal"], exam_date=p["exam_date"], daily_minutes=p["daily_minutes"])
    return {"profile": updated}


class RenameIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


@router.put("/me/name")
def rename(body: RenameIn, user: dict = Depends(student_user)):
    db.run("UPDATE users SET display_name=? WHERE id=?", (body.display_name.strip(), user["id"]))
    store.upsert_student(user["id"], body.display_name.strip(), user["grade"], user["language"], user["level"], user["board"])
    return {"ok": True}


@router.get("/me/export")
def export_me(user: dict = Depends(current_user)):
    data = accounts.export_data(user["id"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("aividya-data.json", json.dumps(data, ensure_ascii=False, indent=1))
        if user["role"] == "student":
            z.writestr("notes.md", learning.export_notes_markdown(user["id"]))
    audit.log(user["id"], "data_exported")
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="aividya-my-data.zip"'})


class DeleteIn(BaseModel):
    confirm: str
    password: str | None = None


@router.post("/me/delete")
def delete_me(body: DeleteIn, request: Request, response: Response, user: dict = Depends(current_user)):
    if body.confirm != "DELETE":
        raise HTTPException(400, "Type DELETE to confirm")
    if config.AUTH == "on" and user["password_hash"] and not accounts.check_secret(body.password or "", user["password_hash"]):
        raise HTTPException(401, "Wrong password")
    accounts.delete_account(user["id"], user["id"], client_ip(request))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/students/{student_id}/delete")
def delete_child(student_id: str, request: Request, body: DeleteIn, user: dict = Depends(roles("parent", "school_admin"))):
    """A parent (or school admin) erasing a child's account."""
    if body.confirm != "DELETE" or not accounts.can_manage(user, student_id):
        raise HTTPException(403, "Not allowed")
    accounts.delete_account(student_id, user["id"], client_ip(request))
    return {"ok": True}


# ---- notifications & contact -------------------------------------------------------------------
@router.get("/notifications")
def notifications(unread: bool = False, user: dict = Depends(current_user)):
    return {"items": notify.listing(user["id"], unread), "unread": notify.unread_count(user["id"])}


class ReadIn(BaseModel):
    id: int | None = None


@router.post("/notifications/read")
def notifications_read(body: ReadIn, user: dict = Depends(current_user)):
    notify.mark_read(user["id"], body.id)
    return {"ok": True}


class ContactIn(BaseModel):
    email: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=20)
    notify_email: bool = False
    notify_whatsapp: bool = False


@router.get("/me/contact")
def get_contact(user: dict = Depends(current_user)):
    c = db.one("SELECT * FROM contacts WHERE user_id=?", (user["id"],)) or {}
    return {"email": c.get("email"), "phone": c.get("phone"), "notify_email": bool(c.get("notify_email")), "notify_whatsapp": bool(c.get("notify_whatsapp")),
            "channels": {"email": notify.email_ready(), "push": notify.push_ready(), "whatsapp": notify.whatsapp_ready()}, "vapid_public": config.VAPID_PUBLIC}


@router.put("/me/contact")
def save_contact(body: ContactIn, user: dict = Depends(current_user)):
    notify.save_contact(user["id"], body.email, body.phone, body.notify_email, body.notify_whatsapp)
    return {"ok": True}


@router.post("/me/push")
def save_push(subscription: dict, user: dict = Depends(current_user)):
    notify.save_push(user["id"], subscription)
    return {"ok": True}


# ---- legal pages ---------------------------------------------------------------------------------
@router.get("/legal/{page}", response_class=PlainTextResponse)
def legal(page: str):
    from ..legal import PAGES
    if page not in PAGES:
        raise HTTPException(404)
    return PAGES[page]
