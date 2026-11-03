"""Daily 5 and the answer-writing coach: two ways for a student to practise a little every day."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import coach, daily, prefetch
from ..deps import ai_student, student_user
from .learn import _ai, _screen

router = APIRouter(prefix="/api")


# ---- Daily 5 -----------------------------------------------------------------------------------
@router.get("/daily")
def daily_status(student: dict = Depends(student_user)):
    """For the home page: is there a set, how far along, the last seven days. Makes nothing itself; if today's set is missing it is written in the background."""
    out = daily.status(student)
    if out["state"] == "new" and not out["ready"]:
        prefetch.daily_ahead(student)
    return out


@router.post("/daily/open")
def daily_open(student: dict = Depends(ai_student)):
    """Today's five questions, made now if this is the first look today (a few seconds to half a minute)."""
    return daily.existing(student) or _ai(daily.today, student)


class DailyAnswer(BaseModel):
    question_id: str = Field(max_length=16)
    choice: int = Field(ge=0, le=5)


@router.post("/daily/answer")
def daily_answer(body: DailyAnswer, student: dict = Depends(student_user)):
    try:
        return daily.answer(student, body.question_id, body.choice)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---- answer-writing coach ----------------------------------------------------------------------
class CoachStart(BaseModel):
    subtopic_id: str = Field("", max_length=80)
    marks: Literal[2, 3, 5] = 3
    question: str = Field("", max_length=1500)
    retry_of: int | None = None


@router.post("/coach/start")
def coach_start(body: CoachStart, student: dict = Depends(ai_student)):
    if body.question.strip():
        _screen(student, body.question)
    return _ai(coach.start, student, body.subtopic_id, body.marks, body.question, body.retry_of)


class CoachAnswer(BaseModel):
    answer: str = Field(min_length=3, max_length=coach.MAX_ANSWER)


@router.post("/coach/{attempt_id}/submit")
def coach_submit(attempt_id: int, body: CoachAnswer, student: dict = Depends(ai_student)):
    _screen(student, body.answer)
    return _ai(coach.submit, student, attempt_id, body.answer)


@router.get("/coach/{attempt_id}")
def coach_get(attempt_id: int, student: dict = Depends(student_user)):
    try:
        return coach.result(student, attempt_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/coach")
def coach_history(student: dict = Depends(student_user)):
    return {"items": coach.history(student)}
