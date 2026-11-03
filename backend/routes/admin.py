"""The administrator's console: people, schools, topics and curriculum, lessons and other content, bulk jobs, announcements, system care.

Administrators (role "admin") can use all of it. A school administrator ("school_admin") can see their own school's people and the curriculum, nothing else.
"""
from __future__ import annotations

import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import accounts, admin_service as svc, audit, config, curriculum, db, jobs, lesson, metrics, reports, scheduler, semantic
from ..deps import client_ip, roles

router = APIRouter(prefix="/api/admin")
admin_only = roles()
school_or_admin = roles("school_admin")


def _run(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except svc.AdminError as exc:
        raise HTTPException(exc.status, str(exc))
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---- overview, analytics, audit, health --------------------------------------------------------
@router.get("/overview")
def overview(user: dict = Depends(admin_only)):
    return svc.overview()


@router.get("/analytics")
def analytics(days: int = 14, user: dict = Depends(admin_only)):
    return reports.analytics(max(1, min(days, 90)))


@router.get("/audit")
def audit_log(action: str | None = None, q: str = "", limit: int = 300, user: dict = Depends(admin_only)):
    items = audit.recent(max(1, min(limit, 1000)), action)
    if q.strip():
        needle = q.strip().lower()
        items = [i for i in items if needle in f"{i.get('action', '')} {i.get('target', '')} {i.get('detail', '')} {i.get('actor_id', '')}".lower()]
    return {"items": items}


@router.get("/audit/actions")
def audit_actions(user: dict = Depends(admin_only)):
    return {"items": [r["action"] for r in db.all("SELECT DISTINCT action FROM audit_log ORDER BY action")]}


@router.get("/health")
def admin_health(user: dict = Depends(admin_only)):
    from .. import llm, voice
    h = llm.health()
    models = llm.provider().roles() if config.PROVIDER == "ollama" and h["ready"] else {}
    return {"model": {"provider": config.PROVIDER, "name": config.model(), "roles": models, **h}, "queue": scheduler.scheduler.stats(),
            "voice": {"tts": config.TTS, "tts_languages": voice.tts_languages(), "stt": voice.stt_available()},
            "channels": {"email": bool(config.SMTP_HOST), "push": bool(config.VAPID_PUBLIC), "whatsapp": bool(config.WHATSAPP_TOKEN)}, "metrics": metrics.snapshot(),
            "db_bytes": db.path().stat().st_size if db.path().exists() else 0, "schema": db.migrate()}


# ---- people ------------------------------------------------------------------------------------
USER_COLS = "id, username, display_name, role, consent, school_id, disabled, created_at, last_login, email, email_verified"


@router.get("/users")
def list_users(q: str = "", role: str = "", status: Literal["", "active", "disabled", "no_email", "pending_consent"] = "", offset: int = 0, limit: int = 50,
               user: dict = Depends(school_or_admin)):
    where, args = ["(username LIKE ? OR display_name LIKE ? OR COALESCE(email,'') LIKE ?)", "username NOT LIKE 'anon-%'"], [f"%{q}%"] * 3
    if user["role"] == "school_admin":
        where.append("school_id=?")
        args.append(user.get("school_id"))
    if role in config.ROLES:
        where.append("role=?")
        args.append(role)
    where.append({"": "1=1", "active": "disabled=0", "disabled": "disabled=1", "no_email": "(email IS NULL OR email_verified=0)", "pending_consent": "consent='pending'"}[status])
    total = db.scalar(f"SELECT COUNT(*) FROM users WHERE {' AND '.join(where)}", tuple(args), 0)
    rows = db.all(f"SELECT {USER_COLS} FROM users WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*args, max(1, min(limit, 200)), max(0, offset)))
    return {"total": total, "items": rows}


@router.get("/users/{user_id}")
def user_detail(user_id: str, user: dict = Depends(school_or_admin)):
    d = svc.user_detail(user_id)
    if not d or (user["role"] == "school_admin" and d.get("school_id") != user.get("school_id")):
        raise HTTPException(404, "No such person.")
    return d


class NewUser(BaseModel):
    username: str
    display_name: str = Field(min_length=1, max_length=40)
    role: Literal["student", "parent", "teacher", "school_admin", "admin"] = "student"
    password: str = ""
    email: str = ""
    birth_year: int | None = None
    grade: int = 9
    school_id: str | None = None


@router.post("/users")
def create_user(body: NewUser, request: Request, user: dict = Depends(admin_only)):
    """Make an account directly (for a class list, a new teacher...). The email, if given, counts as confirmed. A password is made up if none is typed."""
    password = body.password or svc.generated_password()
    if body.grade not in config.GRADES:
        raise HTTPException(400, "Grade must be 7-12")
    year = __import__("datetime").date.today().year
    birth = body.birth_year or (year - (body.grade + 5) if body.role == "student" else 1985)  # a student's year of birth is guessed from the class when it is not given
    created = _run(accounts.create_user, body.username, password, body.display_name, body.role, birth, None, {"grade": body.grade}, client_ip(request), body.email or None)
    if body.school_id:
        if not db.one("SELECT 1 FROM schools WHERE id=?", (body.school_id,)):
            raise HTTPException(404, "No such school.")
        db.run("UPDATE users SET school_id=? WHERE id=?", (body.school_id, created["id"]))
    if body.email:
        db.run("UPDATE users SET email_verified=1 WHERE id=?", (created["id"],))
    audit.log(user["id"], "admin_user_created", created["id"], {"role": body.role}, client_ip(request))
    return {"id": created["id"], "username": created["username"], "password": None if body.password else password, "consent": created["consent"]}


class UserEdit(BaseModel):
    role: Literal["student", "parent", "teacher", "school_admin", "admin"]
    school_id: str | None = None
    disabled: bool | None = None
    display_name: str | None = Field(None, min_length=1, max_length=40)


@router.put("/users/{user_id}")
def edit_user(user_id: str, body: UserEdit, request: Request, user: dict = Depends(admin_only)):
    target = accounts.get_user(user_id)
    if not target:
        raise HTTPException(404, "No such person.")
    if user_id == user["id"] and (body.role != "admin" or body.disabled):
        raise HTTPException(400, "You cannot demote or disable yourself")
    if target["role"] == "admin" and body.role != "admin" and db.scalar("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0", (), 0) <= 1:
        raise HTTPException(400, "There must always be one administrator.")
    if body.school_id and not db.one("SELECT 1 FROM schools WHERE id=?", (body.school_id,)):
        raise HTTPException(404, "No such school.")
    db.run("UPDATE users SET role=?, school_id=?, disabled=COALESCE(?, disabled), display_name=COALESCE(?, display_name) WHERE id=?",
           (body.role, body.school_id, None if body.disabled is None else int(body.disabled), body.display_name, user_id))
    if body.disabled:
        db.run("DELETE FROM sessions WHERE user_id=?", (user_id,))
    audit.log(user["id"], "user_edited", user_id, body.model_dump(), client_ip(request))
    return {"ok": True}


class PasswordIn(BaseModel):
    new_password: str = ""


@router.post("/users/{user_id}/password")
def reset_password(user_id: str, body: PasswordIn, user: dict = Depends(admin_only)):
    """Set a new password (made up if none is typed; shown once) and sign the person out everywhere."""
    password = body.new_password or svc.generated_password()
    _run(accounts.admin_reset_password, user, user_id, password)
    return {"password": None if body.new_password else password}


@router.post("/users/{user_id}/signout")
def sign_out(user_id: str, user: dict = Depends(admin_only)):
    if not accounts.get_user(user_id):
        raise HTTPException(404, "No such person.")
    n = db.scalar("SELECT COUNT(*) FROM sessions WHERE user_id=?", (user_id,), 0)
    db.run("DELETE FROM sessions WHERE user_id=?", (user_id,))
    audit.log(user["id"], "admin_signout", user_id)
    return {"sessions": n}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request, user: dict = Depends(admin_only)):
    target = accounts.get_user(user_id)
    if not target:
        raise HTTPException(404, "No such person.")
    if user_id == user["id"]:
        raise HTTPException(400, "You cannot delete yourself.")
    if target["role"] == "admin" and db.scalar("SELECT COUNT(*) FROM users WHERE role='admin'", (), 0) <= 1:
        raise HTTPException(400, "There must always be one administrator.")
    accounts.delete_account(user_id, user["id"], client_ip(request))
    return {"ok": True}


# ---- schools -----------------------------------------------------------------------------------
class SchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)


@router.get("/schools")
def list_schools(user: dict = Depends(school_or_admin)):
    where, args = ("WHERE s.id=?", (user.get("school_id"),)) if user["role"] == "school_admin" else ("", ())
    return {"items": db.all(f"SELECT s.*, (SELECT COUNT(*) FROM users u WHERE u.school_id=s.id) AS people, (SELECT COUNT(*) FROM classes c WHERE c.school_id=s.id) AS classes FROM schools s {where} ORDER BY s.created_at DESC", args)}


@router.post("/schools")
def new_school(body: SchoolIn, user: dict = Depends(admin_only)):
    import secrets
    sid, code = accounts.new_id("s"), secrets.token_hex(3).upper()
    db.run("INSERT INTO schools (id, name, code, created_at) VALUES (?,?,?,?)", (sid, body.name.strip(), code, time.time()))
    audit.log(user["id"], "school_created", sid)
    return {"id": sid, "name": body.name, "code": code}


@router.put("/schools/{school_id}")
def rename_school(school_id: str, body: SchoolIn, user: dict = Depends(admin_only)):
    if not db.one("SELECT 1 FROM schools WHERE id=?", (school_id,)):
        raise HTTPException(404, "No such school.")
    db.run("UPDATE schools SET name=? WHERE id=?", (body.name.strip(), school_id))
    audit.log(user["id"], "school_renamed", school_id)
    return {"ok": True}


@router.post("/schools/{school_id}/code")
def school_code(school_id: str, user: dict = Depends(admin_only)):
    code = _run(svc.new_school_code, school_id)
    audit.log(user["id"], "school_code_changed", school_id)
    return {"code": code}


@router.delete("/schools/{school_id}")
def delete_school(school_id: str, user: dict = Depends(admin_only)):
    _run(svc.delete_school, school_id)
    audit.log(user["id"], "school_deleted", school_id)
    return {"ok": True}


# ---- topics and curriculum ---------------------------------------------------------------------
@router.get("/curriculum")
def curriculum_tree(subject: str, grade: int, user: dict = Depends(school_or_admin)):
    if subject not in curriculum.SUBJECTS or grade not in config.GRADES:
        raise HTTPException(400, "Choose a subject and a class (7-12).")
    chapters = curriculum.admin_tree(subject, grade)
    written = {r["subtopic_id"]: r["n"] for r in db.all("SELECT subtopic_id, COUNT(*) AS n FROM lesson_versions WHERE is_active=1 AND subtopic_id LIKE ? GROUP BY subtopic_id", (f"{subject[:3]}-{grade}-%",))}
    for c in chapters:
        for s in c["subtopics"]:
            s["lessons"] = written.get(s["id"], 0)
    return {"subject": subject, "grade": grade, "chapters": chapters, "edits": len(curriculum.edits())}


class CurEdit(BaseModel):
    op: Literal["add_chapter", "rename_chapter", "hide_chapter", "add_subtopic", "rename_subtopic", "hide_subtopic", "unhide_subtopic"]
    id: str | None = None
    subject: str | None = None
    grade: int | None = None
    title: str | None = Field(None, max_length=120)
    chapter: str | None = None
    track: str = ""
    hidden: bool = True
    subtopics: list[str] = Field(default_factory=list, max_length=30)


@router.get("/curriculum/edits")
def curriculum_edits(user: dict = Depends(school_or_admin)):
    return {"edits": curriculum.edits()}


@router.post("/curriculum/edit")
def curriculum_edit(body: CurEdit, user: dict = Depends(school_or_admin)):
    op = body.op
    if op == "add_chapter":
        if body.subject not in curriculum.SUBJECTS or body.grade not in config.GRADES or not body.title:
            raise HTTPException(400, "Need subject, grade and title")
        cid = f"{body.subject[:3]}-{body.grade}-x-{re.sub(r'[^a-z0-9]+', '-', body.title.lower()).strip('-')[:30]}"
        curriculum.apply_edit({"op": op, "id": cid, "subject": body.subject, "grade": body.grade, "title": body.title, "track": body.track.upper(),
                               "subtopics": [{"key": f"x{i + 1}", "title": t} for i, t in enumerate(body.subtopics) if t.strip()]})
    elif op in ("rename_chapter", "rename_subtopic") and body.id and body.title:
        curriculum.apply_edit({"op": op, "id": body.id, "title": body.title})
    elif op == "hide_chapter" and body.id:
        curriculum.apply_edit({"op": op, "id": body.id, "hidden": body.hidden})
    elif op == "add_subtopic" and body.chapter and body.title:
        curriculum.apply_edit({"op": op, "chapter": body.chapter, "key": f"x{int(time.time() * 1000)}", "title": body.title})
    elif op in ("hide_subtopic", "unhide_subtopic") and body.id:
        curriculum.apply_edit({"op": op, "id": body.id})
    else:
        raise HTTPException(400, "Missing fields for this edit")
    audit.log(user["id"], "curriculum_edit", op, body.model_dump(exclude_none=True))
    semantic.build_async()
    return {"ok": True}


@router.post("/curriculum/undo")
def curriculum_undo(user: dict = Depends(school_or_admin)):
    """Take back the most recent curriculum edit."""
    last = curriculum.undo_last_edit()
    if not last:
        raise HTTPException(404, "There is nothing to undo.")
    audit.log(user["id"], "curriculum_undo", last.get("op", ""), last)
    semantic.build_async()
    return {"undone": last}


# ---- lessons and other content -----------------------------------------------------------------
@router.get("/lessons")
def lessons(status: Literal["", "draft", "approved", "rejected"] = "", q: str = "", subject: str = "", grade: str = "", flagged: bool = False,
            offset: int = 0, limit: int = 50, user: dict = Depends(admin_only)):
    if grade and not grade.isdigit():
        raise HTTPException(400, "Class must be a number.")
    return svc.list_lessons(status, q, subject, int(grade) if grade else None, flagged, max(0, offset), max(1, min(limit, 200)))


@router.get("/lessons/{version_id}")
def lesson_version(version_id: int, user: dict = Depends(admin_only)):
    v = lesson.get_version(version_id)
    if not v or str(v["subtopic_id"]).startswith("my-"):
        raise HTTPException(404, "No such lesson version.")
    t = curriculum.get_subtopic(v["subtopic_id"], owner="") or {}
    return {**v, "title": t.get("title"), "chapter": t.get("chapter"), "subject_name": t.get("subject_name"), "grade": t.get("grade")}


class DecisionIn(BaseModel):
    status: Literal["approved", "rejected", "draft"]
    note: str = Field("", max_length=1000)


@router.post("/lessons/{version_id}/status")
def lesson_status(version_id: int, body: DecisionIn, user: dict = Depends(admin_only)):
    v = lesson.get_version(version_id)
    if not v or str(v["subtopic_id"]).startswith("my-"):
        raise HTTPException(404, "No such lesson version.")
    lesson.review(version_id, user["id"], body.status, body.note)
    audit.log(user["id"], f"lesson_{body.status}", str(version_id), body.note[:200])
    return {"ok": True}


@router.post("/lessons/{version_id}/activate")
def lesson_activate(version_id: int, user: dict = Depends(admin_only)):
    """Show this version to students (an older one, say, after a bad rewrite)."""
    v = lesson.get_version(version_id)
    if not v or str(v["subtopic_id"]).startswith("my-") or v["status"] == "rejected":
        raise HTTPException(404, "No such lesson version.")
    lesson.activate(version_id)
    audit.log(user["id"], "lesson_activated", str(version_id))
    return {"ok": True}


@router.delete("/lessons/{version_id}")
def lesson_delete(version_id: int, user: dict = Depends(admin_only)):
    out = _run(svc.delete_version, version_id)
    audit.log(user["id"], "lesson_deleted", str(version_id), out)
    return out


class ClearIn(BaseModel):
    what: Literal["extras", "lessons"]


@router.post("/topics/{subtopic_id}/clear")
def clear_topic(subtopic_id: str, body: ClearIn, user: dict = Depends(admin_only)):
    out = _run(svc.clear_topic, subtopic_id, body.what)
    audit.log(user["id"], "topic_cleared", subtopic_id, {"what": body.what, **out})
    return out


@router.get("/custom-topics")
def custom_topics(q: str = "", offset: int = 0, limit: int = 50, user: dict = Depends(admin_only)):
    return svc.custom_topics(q, max(0, offset), max(1, min(limit, 200)))


@router.delete("/custom-topics/{topic_id}")
def delete_custom_topic(topic_id: str, user: dict = Depends(admin_only)):
    _run(svc.delete_custom_topic, topic_id)
    audit.log(user["id"], "custom_topic_removed", topic_id)
    return {"ok": True}


# ---- bulk jobs ---------------------------------------------------------------------------------
class JobIn(BaseModel):
    subject: str
    grade: int
    chapter_id: str | None = None
    language: str = "en"
    level: str = "standard"
    board: str = "CBSE"
    extras: bool = False
    force: bool = False


@router.get("/jobs")
def job_list(user: dict = Depends(admin_only)):
    return {"items": jobs.listing()}


@router.post("/jobs")
def job_start(body: JobIn, user: dict = Depends(admin_only)):
    """Write every lesson of a class or chapter now, one after another in the background."""
    if body.subject not in curriculum.SUBJECTS or body.grade not in config.GRADES or body.language not in config.LANGUAGES or body.level not in config.LEVELS or body.board not in config.BOARDS:
        raise HTTPException(400, "Check the subject, class, language, level and board.")
    ids = curriculum.topic_ids(body.subject, body.grade, body.chapter_id, body.board, body.level)
    where = next((c["title"] for c in curriculum.admin_tree(body.subject, body.grade) if c["id"] == body.chapter_id), "") if body.chapter_id else ""
    title = f"{curriculum.SUBJECTS[body.subject]['name']} class {body.grade}" + (f" - {where}" if where else "") + f" ({body.language}, {body.level})"
    job = _run(jobs.submit, title, ids, body.language, body.level, body.board, body.extras, body.force, user["id"])
    audit.log(user["id"], "bulk_write_started", str(job["id"]), {"title": title, "topics": job["total"]})
    return job


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: int, user: dict = Depends(admin_only)):
    if not jobs.cancel(job_id):
        raise HTTPException(404, "That job is not running.")
    audit.log(user["id"], "bulk_write_cancelled", str(job_id))
    return {"ok": True}


# ---- announcements -----------------------------------------------------------------------------
class AnnounceIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field("", max_length=600)
    audience: Literal["all", "students", "parents", "teachers", "school"] = "all"
    school_id: str | None = None
    link: str = Field("", max_length=200)


@router.post("/announce")
def announce(body: AnnounceIn, user: dict = Depends(admin_only)):
    """A notice that appears under the 🔔 of everyone in the audience."""
    if body.link and not (body.link.startswith("#/") or body.link.startswith("https://")):
        raise HTTPException(400, "A link must start with #/ (inside the app) or https://")
    return {"recipients": _run(svc.announce, user["id"], body.title.strip(), body.body.strip(), body.audience, body.school_id, body.link)}


# ---- system ------------------------------------------------------------------------------------
@router.get("/system")
def system(user: dict = Depends(admin_only)):
    return svc.system()


@router.post("/backup")
def make_backup(user: dict = Depends(admin_only)):
    out = db.backup()
    audit.log(user["id"], "backup", out.name)
    return {"file": out.name, "bytes": out.stat().st_size}


@router.get("/backups/{name}")
def download_backup(name: str, user: dict = Depends(admin_only)):
    path = _run(svc.backup_path, name)
    audit.log(user["id"], "backup_downloaded", name)
    return FileResponse(path, media_type="application/octet-stream", filename=name)


@router.delete("/backups/{name}")
def delete_backup(name: str, user: dict = Depends(admin_only)):
    _run(svc.backup_path, name).unlink(missing_ok=True)
    audit.log(user["id"], "backup_deleted", name)
    return {"ok": True}


class PurgeIn(BaseModel):
    what: Literal["sessions", "codes", "tts_cache", "audit_90d"]


@router.post("/system/purge")
def purge(body: PurgeIn, user: dict = Depends(admin_only)):
    n = _run(svc.purge, body.what)
    audit.log(user["id"], "housekeeping", body.what, {"removed": n})
    return {"removed": n}
