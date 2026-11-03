"""Teachers and parents (administrators too): classes, assignments, reports, content review, question bank, library. The administrator's console is in admin.py."""
from __future__ import annotations

import base64
import csv
import io
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import accounts, audit, classes, config, curriculum, db, exams, factcheck, lesson, rag, reports, scheduler
from ..deps import current_user, roles
from .learn import _ingest_upload, _ai

router = APIRouter(prefix="/api")
staff = roles("teacher", "school_admin")


# ---- classes & assignments (teacher) -----------------------------------------------------------
class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    grade: int | None = None


@router.get("/classes")
def my_classes(user: dict = Depends(current_user)):
    return {"items": classes.classes_for(user)}


@router.post("/classes")
def new_class(body: ClassIn, user: dict = Depends(staff)):
    return classes.create_class(user, body.name, body.grade)


def _managed(class_id: str, user: dict) -> dict:
    cls = classes.get_class(class_id)
    if not cls or not classes.can_manage(user, cls):
        raise HTTPException(404, "Class not found")
    return cls


@router.get("/classes/{class_id}")
def class_detail(class_id: str, user: dict = Depends(staff)):
    cls = _managed(class_id, user)
    assignments = db.all("SELECT * FROM assignments WHERE class_id=? ORDER BY created_at DESC", (class_id,))
    for a in assignments:
        prog = classes.assignment_progress(a["id"])
        a["done"], a["total"] = sum(1 for p in prog if p["status"] == "done"), len(prog)
    return {"class": cls, "roster": classes.roster(class_id), "assignments": assignments, "leaderboard": classes.leaderboard(class_id)}


@router.get("/classes/{class_id}/report")
def class_report(class_id: str, subject: str = "maths", user: dict = Depends(staff)):
    _managed(class_id, user)
    if subject not in curriculum.SUBJECTS:
        raise HTTPException(404, "Unknown subject")
    return reports.class_report(class_id, subject)


@router.delete("/classes/{class_id}/members/{student_id}")
def remove_member(class_id: str, student_id: str, user: dict = Depends(staff)):
    _managed(class_id, user)
    classes.remove_member(class_id, student_id)
    return {"ok": True}


class AssignIn(BaseModel):
    kind: Literal["lesson", "quiz", "practice", "test"]
    subtopic_id: str | None = None
    title: str = Field("", max_length=120)
    note: str = Field("", max_length=500)
    due_at: float | None = None


@router.post("/classes/{class_id}/assignments")
def new_assignment(class_id: str, body: AssignIn, user: dict = Depends(staff)):
    _managed(class_id, user)
    try:
        return classes.assign(user, class_id, body.kind, body.subtopic_id, body.title, body.note, body.due_at)
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, str(exc))


@router.get("/assignments/{assignment_id}/progress")
def assignment_progress(assignment_id: str, user: dict = Depends(staff)):
    a = db.one("SELECT * FROM assignments WHERE id=?", (assignment_id,))
    if not a:
        raise HTTPException(404)
    _managed(a["class_id"], user)
    return {"assignment": a, "students": classes.assignment_progress(assignment_id)}


@router.get("/students/{student_id}/overview")
def student_overview(student_id: str, user: dict = Depends(current_user)):
    if not accounts.can_view_student(user, student_id):
        raise HTTPException(403, "You do not have access to this student")
    if user["id"] != student_id:
        audit.log(user["id"], "viewed_student", student_id)
    return reports.student_overview(student_id)


@router.get("/students/{student_id}/weekly")
def student_weekly(student_id: str, user: dict = Depends(current_user)):
    if not accounts.can_view_student(user, student_id):
        raise HTTPException(403, "You do not have access to this student")
    return reports.weekly_summary(student_id)


# ---- parent ------------------------------------------------------------------------------------
@router.get("/parent/children")
def my_children(user: dict = Depends(roles("parent"))):
    out = []
    for c in accounts.children_of(user["id"]):
        ov = reports.student_overview(c["id"]) if c["consent"] == "granted" else {}
        out.append({**c, "overview": ov, "weekly": reports.weekly_summary(c["id"]) if ov else None})
    return {"children": out}


# ---- content review (teacher / admin) ----------------------------------------------------------
@router.get("/review/queue")
def review_queue(status: str = "draft", user: dict = Depends(staff)):
    if status not in ("draft", "approved", "rejected"):
        raise HTTPException(400, "bad status")
    return {"items": lesson.review_queue(status)}


@router.get("/review/topic/{subtopic_id}")
def review_topic(subtopic_id: str, variant: str | None = None, user: dict = Depends(staff)):
    if subtopic_id.startswith("my-"):
        raise HTTPException(404, "Unknown topic")
    return {"versions": lesson.list_versions(subtopic_id, variant)}


@router.get("/review/version/{version_id}")
def review_version(version_id: int, user: dict = Depends(staff)):
    v = lesson.get_version(version_id)
    if v and str(v["subtopic_id"]).startswith("my-"):
        v = None
    if not v:
        raise HTTPException(404)
    return v


class ReviewIn(BaseModel):
    status: Literal["approved", "rejected", "draft"]
    note: str = Field("", max_length=1000)


@router.post("/review/version/{version_id}")
def review_decision(version_id: int, body: ReviewIn, user: dict = Depends(staff)):
    v = lesson.get_version(version_id)
    if not v or str(v["subtopic_id"]).startswith("my-"):
        raise HTTPException(404, "Unknown lesson version")
    lesson.review(version_id, user["id"], body.status, body.note)
    audit.log(user["id"], f"lesson_{body.status}", str(version_id), body.note[:200])
    return {"ok": True}


class EditIn(BaseModel):
    variant: str
    sections: list[dict] = Field(min_length=1, max_length=14)
    approve: bool = True


@router.post("/review/topic/{subtopic_id}/edit")
def review_edit(subtopic_id: str, body: EditIn, user: dict = Depends(staff)):
    """A teacher's edited lesson becomes a new version (approved by default) and is served to students immediately."""
    if not curriculum.get_subtopic(subtopic_id, owner=""):
        raise HTTPException(404)
    clean = []
    for s in body.sections:
        if not all(isinstance(s.get(k), str) for k in ("kind", "title", "display", "speech")):
            raise HTTPException(400, "Each section needs kind, title, display and speech")
        clean.append({k: s[k][:6000] for k in ("kind", "title", "display", "speech")})
    vid = lesson.save_version(subtopic_id, body.variant, clean, [], "teacher", "teacher", "approved" if body.approve else "draft", user["id"], activate=True)
    audit.log(user["id"], "lesson_edited", subtopic_id, {"version": vid})
    return {"id": vid}


class RegenIn(BaseModel):
    variant: str
    section: int = Field(ge=0, le=11)
    guidance: str = Field("", max_length=300)


@router.post("/review/topic/{subtopic_id}/rewrite-section")
def review_rewrite(subtopic_id: str, body: RegenIn, user: dict = Depends(staff)):
    language, level, group = (body.variant.split(":") + ["standard", "cbse"])[:3]
    return _ai(lesson.regenerate_section, subtopic_id, language, level, "ICSE" if group == "icse" else "CBSE", body.section, body.guidance, _priority=scheduler.LESSON)


class RegenAllIn(BaseModel):
    language: str = "en"
    level: str = "standard"
    board: str = "CBSE"


@router.post("/review/topic/{subtopic_id}/regenerate")
def review_regenerate(subtopic_id: str, body: RegenAllIn, user: dict = Depends(staff)):
    """Generate a brand-new draft (kept alongside the old versions). Streams are not used here: it runs to completion."""
    if body.language not in config.LANGUAGES or body.level not in config.LEVELS:
        raise HTTPException(400, "bad language or level")
    var = lesson.variant(body.language, body.level, body.board)

    def work():
        last = None
        for ev in lesson.stream_lesson(subtopic_id, body.language, body.level, body.board, force=True):
            last = ev
        return last

    last = _ai(work, _priority=scheduler.LESSON)  # the old version stays active until the new one is fully written
    if last and last.get("type") == "error":
        raise HTTPException(502, last["message"])
    audit.log(user["id"], "lesson_regenerated", subtopic_id)
    return {"ok": True, "versions": lesson.list_versions(subtopic_id, var)}


@router.post("/review/version/{version_id}/factcheck")
def run_factcheck(version_id: int, user: dict = Depends(staff)):
    factcheck.run_async(version_id)
    return {"started": True}


# ---- reports queue -----------------------------------------------------------------------------
@router.get("/reports")
def reports_queue(status: str = "open", user: dict = Depends(staff)):
    rows = db.all("SELECT * FROM reports WHERE status=? ORDER BY id DESC LIMIT 200", (status,))
    for r in rows:
        t = curriculum.get_subtopic(r["subtopic_id"]) if r["subtopic_id"] else None
        r["topic"] = t["title"] if t else None
    return {"items": rows}


class ResolveIn(BaseModel):
    resolution: str = Field("", max_length=1000)
    status: Literal["resolved", "dismissed"] = "resolved"


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: int, body: ResolveIn, user: dict = Depends(staff)):
    db.run("UPDATE reports SET status=?, resolution=?, resolved_by=?, resolved_at=? WHERE id=?", (body.status, body.resolution, user["id"], time.time(), report_id))
    audit.log(user["id"], "report_resolved", str(report_id))
    return {"ok": True}


# ---- media, question bank, library -------------------------------------------------------------
class MediaIn(BaseModel):
    subtopic_id: str
    kind: Literal["video", "link", "audio"] = "video"
    url: str = Field(max_length=500)
    title: str = Field("", max_length=160)


@router.post("/media")
def add_media(body: MediaIn, user: dict = Depends(staff)):
    if not body.url.startswith(("https://", "/media/")):
        raise HTTPException(400, "Use an https:// link")
    if not curriculum.get_subtopic(body.subtopic_id, owner=""):
        raise HTTPException(404)
    mid = db.run("INSERT INTO media (subtopic_id, kind, url, title, added_by, created_at) VALUES (?,?,?,?,?,?)", (body.subtopic_id, body.kind, body.url, body.title, user["id"], time.time()))
    return {"id": mid}


@router.delete("/media/{media_id}")
def del_media(media_id: int, user: dict = Depends(staff)):
    db.run("DELETE FROM media WHERE id=?", (media_id,))
    return {"ok": True}


@router.get("/bank")
def bank_list(subtopic_id: str | None = None, kind: str | None = None, approved: bool | None = None, user: dict = Depends(staff)):
    return {"items": exams.bank_search(subtopic_id, kind, approved)}


class BankIn(BaseModel):
    subtopic_id: str
    kind: Literal["mcq", "short", "long", "case", "numeric"]
    marks: int = Field(1, ge=1, le=10)
    question: str = Field(min_length=5, max_length=3000)
    options: list[str] = Field(default_factory=list, max_length=6)
    answer: str = Field("", max_length=2000)
    solution: str = Field("", max_length=3000)
    difficulty: int = Field(2, ge=1, le=3)
    board: str = ""
    year: str = ""


@router.post("/bank")
def bank_add(body: BankIn, user: dict = Depends(staff)):
    if not curriculum.get_subtopic(body.subtopic_id, owner=""):
        raise HTTPException(404)
    return {"id": exams.bank_add(user["id"], body.subtopic_id, body.kind, body.marks, body.question, body.answer, body.solution, body.options, body.difficulty, "teacher", body.board, body.year)}


class BankImport(BaseModel):
    format: Literal["json", "csv"] = "json"
    data: str = Field(max_length=2_000_000)


@router.post("/bank/import")
def bank_import(body: BankImport, user: dict = Depends(staff)):
    try:
        rows = json.loads(body.data) if body.format == "json" else list(csv.DictReader(io.StringIO(body.data)))
    except ValueError:
        raise HTTPException(400, "Could not parse the data")
    if not isinstance(rows, list):
        raise HTTPException(400, "Expected a list of questions")
    audit.log(user["id"], "bank_import", "", {"rows": len(rows)})
    return exams.bank_import(user["id"], rows)


@router.post("/bank/{qid}/approve")
def bank_approve(qid: int, approved: bool = True, user: dict = Depends(staff)):
    db.run("UPDATE question_bank SET approved=? WHERE id=?", (int(approved), qid))
    return {"ok": True}


@router.get("/library")
def library_list(user: dict = Depends(current_user)):
    return {"items": rag.docs("library")}


class LibUpload(BaseModel):
    filename: str = Field(max_length=200)
    data_b64: str
    title: str = Field("", max_length=200)
    subject: str | None = None
    grade: int | None = None


@router.post("/library")
def library_upload(body: LibUpload, user: dict = Depends(staff)):
    try:
        raw = base64.b64decode(body.data_b64, validate=True)
    except ValueError:
        raise HTTPException(400, "The file could not be read")
    if len(raw) > config.MAX_UPLOAD:
        raise HTTPException(413, "File too large")
    if body.subject and body.subject not in curriculum.SUBJECTS:
        raise HTTPException(400, "Unknown subject")
    out = _ai(_ingest_upload, raw, body.filename, body.title or body.filename, user["id"], "library", body.subject, body.grade, _priority=scheduler.BATCH)
    audit.log(user["id"], "library_upload", body.filename)
    return out


@router.delete("/library/{doc_id}")
def library_delete(doc_id: int, user: dict = Depends(staff)):
    if not rag.delete_doc(doc_id):
        raise HTTPException(404)
    audit.log(user["id"], "library_delete", str(doc_id))
    return {"ok": True}
