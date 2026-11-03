"""FastAPI dependencies: who is calling, what role, which student profile, and per-user AI rate limits."""
from __future__ import annotations

import json
import secrets
from typing import Iterator

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from . import accounts, config, scheduler, store
from .ratelimit import limiter

COOKIE = "vidya_session"
ANON_COOKIE = "vidya_anon"


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or "?"


def set_session_cookie(response: Response, token: str, remember: bool = False) -> None:
    response.set_cookie(COOKIE, token, max_age=(config.REMEMBER_DAYS if remember else config.SESSION_DAYS) * 86400, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, path="/")


def current_user(request: Request, response: Response) -> dict:
    if config.AUTH == "off":
        anon = request.cookies.get(ANON_COOKIE)
        if not anon or len(anon) < 16:
            anon = secrets.token_hex(12)
            response.set_cookie(ANON_COOKIE, anon, max_age=3 * 365 * 86400, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, path="/")
        return accounts.anonymous_user(anon)
    user, why = accounts.session_user(request.cookies.get(COOKIE))
    if not user:
        if why == "idle":
            raise HTTPException(401, detail={"code": "idle", "message": f"You were signed out after {config.IDLE_MINUTES} minutes of inactivity. Please sign in again."})
        raise HTTPException(401, "Please sign in")
    return user


def roles(*allowed: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed and user["role"] != "admin":
            raise HTTPException(403, "You do not have access to this")
        return user
    return dep


def student_user(user: dict = Depends(current_user)) -> dict:
    """The signed-in student (with their learning profile merged in). Blocks accounts still waiting for parental consent."""
    if user["role"] != "student":
        raise HTTPException(403, "This is for student accounts")
    if user["consent"] not in ("na", "granted"):
        raise HTTPException(403, detail={"code": "consent_required", "message": "A parent or guardian must approve this account first."})
    profile = store.get_student(user["id"])
    if not profile:
        raise HTTPException(409, "Profile missing")
    return {**profile, "id": user["id"], "role": "student", "username": user["username"], "consent": user["consent"], "school_id": user.get("school_id")}


def ai_student(request: Request, student: dict = Depends(student_user)) -> dict:
    """Student + per-user AI rate limit."""
    ok, wait = limiter.allow(f"ai:{student['id']}", config.RATE_AI)
    if not ok:
        raise HTTPException(429, f"You're going a little fast! Please wait {int(wait) + 1} seconds.", headers={"Retry-After": str(int(wait) + 1)})
    return student


def sse(events: Iterator[dict]) -> StreamingResponse:
    def gen():
        for ev in events:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def queued(factory, priority: int, user_id: str | None = None) -> StreamingResponse:
    return sse(scheduler.pump(factory, priority, user_id=user_id))
