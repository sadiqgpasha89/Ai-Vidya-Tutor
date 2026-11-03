"""Doubt inbox: students send a doubt to their class teacher, the teacher replies, they go back and forth until it is cleared."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import doubts, moderation
from ..deps import current_user, student_user

router = APIRouter(prefix="/api")


def _wrap(fn):
    try:
        return fn()
    except doubts.DoubtError as exc:
        raise HTTPException(exc.status, str(exc))


def _polite(student: dict, *texts: str) -> None:
    """Word-list guardrails on what a student sends to a teacher (no model call: this is a message, not a question to the AI)."""
    verdict = moderation.check_input("\n".join(texts), student.get("language", "en"))
    if verdict["action"] != "allow":
        raise HTTPException(422, verdict["reply"])


@router.get("/doubts")
def doubt_list(status: str = "", class_id: str = "", user: dict = Depends(current_user)):
    if user["role"] not in ("student", "teacher", "school_admin", "admin"):
        raise HTTPException(403, "You do not have access to this")
    return {"items": doubts.listing(user, status, class_id), "waiting": doubts.waiting_for_teacher(user) if user["role"] != "student" else 0}


class DoubtIn(BaseModel):
    class_id: str = Field(max_length=40)
    question: str = Field(min_length=5, max_length=doubts.MAX_TEXT)
    subtopic_id: str = Field("", max_length=80)
    ai_answer: str = Field("", max_length=doubts.MAX_TEXT)


@router.post("/doubts")
def doubt_ask(body: DoubtIn, student: dict = Depends(student_user)):
    _polite(student, body.question)
    return _wrap(lambda: doubts.ask(student, body.class_id, body.question, body.subtopic_id, body.ai_answer))


@router.get("/doubts/{doubt_id}")
def doubt_thread(doubt_id: str, user: dict = Depends(current_user)):
    return _wrap(lambda: doubts.thread(user, doubt_id))


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=doubts.MAX_TEXT)


@router.post("/doubts/{doubt_id}/reply")
def doubt_reply(doubt_id: str, body: ReplyIn, user: dict = Depends(current_user)):
    if user["role"] == "student":
        _polite(user, body.body)
    elif user["role"] not in ("teacher", "school_admin", "admin"):
        raise HTTPException(403, "You do not have access to this")
    return _wrap(lambda: doubts.reply(user, doubt_id, body.body))


class ResolveIn(BaseModel):
    resolved: bool = True


@router.post("/doubts/{doubt_id}/resolve")
def doubt_resolve(doubt_id: str, body: ResolveIn, user: dict = Depends(current_user)):
    return _wrap(lambda: doubts.resolve(user, doubt_id, body.resolved))
