"""Teacher worksheet maker: question paper + answer key from chosen topics."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import audit, config, llm, scheduler, worksheets
from ..deps import queued, roles

router = APIRouter(prefix="/api")
staff = roles("teacher", "school_admin")


def _wrap(fn):
    try:
        return fn()
    except worksheets.WorksheetError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 400, str(exc))


class Item(BaseModel):
    kind: Literal["mcq", "short", "long", "case", "numeric"]
    marks: int = Field(0, ge=0, le=10)
    count: int = Field(ge=1, le=20)


class MakeIn(BaseModel):
    topics: list[str] = Field(min_length=1, max_length=12)
    items: list[Item] = Field(min_length=1, max_length=6)
    title: str = Field("", max_length=120)
    difficulty: Literal["easy", "standard", "hard"] = "standard"
    language: str = "en"
    board: str = "CBSE"
    note: str = Field("", max_length=500)
    minutes: int = Field(0, ge=0, le=300)


@router.post("/worksheets/make")
def make(body: MakeIn, user: dict = Depends(staff)):
    """Streams progress while the sheet is written (a minute or two for a full one), then {"type": "done", "id": ...}."""
    if body.language not in config.LANGUAGES:
        raise HTTPException(400, "Unknown language")
    plan = _wrap(lambda: worksheets.clean_plan([i.model_dump() for i in body.items]))
    audit.log(user["id"], "worksheet_made", "", {"topics": len(body.topics), "questions": sum(p[2] for p in plan)})

    def run():
        try:
            yield from worksheets.make(user, body.topics, plan, body.title, body.difficulty, body.language, body.board, body.note, body.minutes)
        except worksheets.WorksheetError as exc:
            yield {"type": "error", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 - tell the teacher in plain words, not a stack trace
            yield {"type": "error", "message": llm.friendly_error(exc)}

    return queued(run, scheduler.ASSESS, user["id"])


@router.get("/worksheets")
def sheets(user: dict = Depends(staff)):
    return {"items": worksheets.listing(user)}


@router.get("/worksheets/{wid}")
def sheet(wid: str, user: dict = Depends(staff)):
    return _wrap(lambda: worksheets.get(user, wid))


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.put("/worksheets/{wid}")
def sheet_rename(wid: str, body: RenameIn, user: dict = Depends(staff)):
    _wrap(lambda: worksheets.rename(user, wid, body.title))
    return {"ok": True}


@router.delete("/worksheets/{wid}")
def sheet_delete(wid: str, user: dict = Depends(staff)):
    _wrap(lambda: worksheets.delete(user, wid))
    return {"ok": True}


class ReplaceIn(BaseModel):
    question_id: str = Field(max_length=16)


@router.post("/worksheets/{wid}/replace")
def sheet_replace(wid: str, body: ReplaceIn, user: dict = Depends(staff)):
    """Swap one question for a fresh one (takes a few seconds, like any model work)."""
    def work():
        with scheduler.slot(scheduler.ASSESS):
            return worksheets.replace_question(user, wid, body.question_id)
    try:
        return _wrap(work)
    except TimeoutError as exc:
        raise HTTPException(503, str(exc))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, llm.friendly_error(exc))
