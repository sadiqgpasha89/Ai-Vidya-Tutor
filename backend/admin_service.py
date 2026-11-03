"""What the administrator's console can do, apart from the HTTP layer: counts, lesson and topic management, announcements, maintenance."""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from . import accounts, audit, config, curriculum, db, jobs, lesson, notify, scheduler, voice

BACKUP_NAME = "teacher-"


class AdminError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def generated_password() -> str:
    """A password the administrator can read out: 12 characters, no look-alikes."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


# ---- overview ----------------------------------------------------------------------------------
def overview() -> dict:
    now = time.time()
    week = now - 7 * 86400
    roles = {r["role"]: r["n"] for r in db.all("SELECT role, COUNT(*) AS n FROM users WHERE username NOT LIKE 'anon-%' GROUP BY role")}
    topics_total = len(curriculum._load()[1])
    written = db.scalar("SELECT COUNT(DISTINCT subtopic_id) FROM lesson_versions WHERE subtopic_id NOT LIKE 'my-%' AND is_active=1", (), 0)
    by_status = {r["status"]: r["n"] for r in db.all("SELECT status, COUNT(*) AS n FROM lesson_versions WHERE is_active=1 AND subtopic_id NOT LIKE 'my-%' GROUP BY status")}
    flagged = 0
    for r in db.all("SELECT factcheck FROM lesson_versions WHERE is_active=1 AND status!='approved' AND factcheck IS NOT NULL AND subtopic_id NOT LIKE 'my-%'"):
        try:
            flagged += any(i.get("severity") == "high" for i in json.loads(r["factcheck"]).get("issues", []))
        except ValueError:
            continue
    extras = {r["k"]: r["n"] for r in db.all("SELECT substr(kind, 1, instr(kind || ':', ':') - 1) AS k, COUNT(*) AS n FROM extras GROUP BY k")}
    guard = {r["action"]: r["n"] for r in db.all("SELECT action, COUNT(*) AS n FROM audit_log WHERE ts>=? AND action LIKE 'moderation_%' GROUP BY action", (week,))}
    return {
        "users": {"by_role": roles, "total": sum(roles.values()), "disabled": db.scalar("SELECT COUNT(*) FROM users WHERE disabled=1", (), 0),
                  "without_email": db.scalar("SELECT COUNT(*) FROM users WHERE (email IS NULL OR email_verified=0) AND username NOT LIKE 'anon-%'", (), 0),
                  "pending_consent": db.scalar("SELECT COUNT(*) FROM users WHERE consent='pending'", (), 0),
                  "new_7d": db.scalar("SELECT COUNT(*) FROM users WHERE created_at>=? AND username NOT LIKE 'anon-%'", (week,), 0),
                  "active_7d": db.scalar("SELECT COUNT(DISTINCT user_id) FROM events WHERE ts>=?", (week,), 0)},
        "content": {"topics": topics_total, "topics_with_lesson": written, "coverage": round(100 * written / topics_total, 1) if topics_total else 0,
                    "versions": db.scalar("SELECT COUNT(*) FROM lesson_versions WHERE subtopic_id NOT LIKE 'my-%'", (), 0), "by_status": by_status, "flagged": flagged,
                    "extras": extras, "study_notes": db.scalar("SELECT COUNT(*) FROM study_notes", (), 0), "custom_topics": db.scalar("SELECT COUNT(*) FROM custom_topics", (), 0),
                    "questions": db.scalar("SELECT COUNT(*) FROM question_bank", (), 0), "library_docs": db.scalar("SELECT COUNT(*) FROM library_docs", (), 0),
                    "curriculum_edits": len(curriculum.edits())},
        "attention": {"reports_open": db.scalar("SELECT COUNT(*) FROM reports WHERE status='open'", (), 0), "drafts": by_status.get("draft", 0), "flagged": flagged,
                      "guardrail_blocks_7d": sum(guard.values()), "guardrail": guard},
        "queue": scheduler.scheduler.stats(), "jobs_running": sum(1 for j in jobs.listing() if j["status"] in ("queued", "running")),
    }


# ---- lessons (every version ever written) -------------------------------------------------------
def list_lessons(status: str = "", q: str = "", subject: str = "", grade: int | None = None, flagged: bool = False, offset: int = 0, limit: int = 50) -> dict:
    where, args = ["subtopic_id NOT LIKE 'my-%'"], []
    if status:
        where.append("status=?")
        args.append(status)
    rows = db.all(f"SELECT id, subtopic_id, variant, version, model, source, status, is_active, created_at, reviewed_at, factcheck FROM lesson_versions WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 5000", tuple(args))
    out, ql = [], q.strip().lower()
    for r in rows:
        t = curriculum.get_subtopic(r["subtopic_id"], owner="") or {}
        if subject and t.get("subject") != subject:
            continue
        if grade and t.get("grade") != grade:
            continue
        issues = high = None
        if r["factcheck"]:
            try:
                fc = json.loads(r["factcheck"])["issues"]
                issues, high = len(fc), sum(1 for i in fc if i.get("severity") == "high")
            except (ValueError, KeyError):
                pass
        if flagged and not (high and r["status"] != "approved"):
            continue
        title = t.get("title") or r["subtopic_id"]
        if ql and ql not in title.lower() and ql not in r["subtopic_id"].lower() and ql not in (t.get("chapter") or "").lower():
            continue
        out.append({**{k: r[k] for k in ("id", "subtopic_id", "variant", "version", "model", "source", "status", "created_at", "reviewed_at")}, "active": bool(r["is_active"]),
                    "title": title, "chapter": t.get("chapter"), "subject_name": t.get("subject_name"), "grade": t.get("grade"), "issues": issues, "high_issues": high})
    return {"total": len(out), "items": out[offset:offset + limit]}


def delete_version(version_id: int) -> dict:
    """Remove one version of a lesson, with the pictures, summaries and notes made from it. If it was the one students saw, the newest remaining version takes over
    (or, if there is none, the lesson is simply written again the next time a student opens the topic)."""
    row = db.one("SELECT id, subtopic_id, variant, is_active FROM lesson_versions WHERE id=?", (version_id,))
    if not row:
        raise AdminError("No such lesson version.", 404)
    sid, var = row["subtopic_id"], row["variant"]
    db.run("DELETE FROM lesson_versions WHERE id=?", (version_id,))
    for like in (f"%:v{version_id}", f"%:v{version_id}:%"):
        db.run("DELETE FROM extras WHERE subtopic_id=? AND variant=? AND kind LIKE ?", (sid, var, like))
    db.run("DELETE FROM study_notes WHERE version_id=?", (version_id,))
    promoted = None
    if row["is_active"]:
        nxt = db.one("SELECT id FROM lesson_versions WHERE subtopic_id=? AND variant=? AND status!='rejected' ORDER BY version DESC", (sid, var))
        if nxt:
            lesson.activate(nxt["id"])
            promoted = nxt["id"]
    return {"deleted": version_id, "now_active": promoted}


def clear_topic(subtopic_id: str, what: str) -> dict:
    """what = "extras" (pictures, facts, summaries, cheat sheets: made again when needed) or "lessons" (the lesson itself too: written again when a student opens it)."""
    if subtopic_id.startswith("my-") or not curriculum.get_subtopic(subtopic_id, owner=""):
        raise AdminError("Unknown topic.", 404)
    extras_n = db.scalar("SELECT COUNT(*) FROM extras WHERE subtopic_id=?", (subtopic_id,), 0)
    db.run("DELETE FROM extras WHERE subtopic_id=?", (subtopic_id,))
    lessons_n = notes_n = 0
    if what == "lessons":
        lessons_n = db.scalar("SELECT COUNT(*) FROM lesson_versions WHERE subtopic_id=?", (subtopic_id,), 0)
        notes_n = db.scalar("SELECT COUNT(*) FROM study_notes WHERE subtopic_id=?", (subtopic_id,), 0)
        db.run("DELETE FROM lesson_versions WHERE subtopic_id=?", (subtopic_id,))
        db.run("DELETE FROM study_notes WHERE subtopic_id=?", (subtopic_id,))
    return {"extras": extras_n, "lessons": lessons_n, "study_notes": notes_n}


# ---- topics students added ----------------------------------------------------------------------
def custom_topics(q: str = "", offset: int = 0, limit: int = 50) -> dict:
    where, args = "1=1", []
    if q.strip():
        where, args = "(c.title LIKE ? OR u.username LIKE ? OR u.display_name LIKE ?)", [f"%{q.strip()}%"] * 3
    total = db.scalar(f"SELECT COUNT(*) FROM custom_topics c LEFT JOIN users u ON u.id=c.student_id WHERE {where}", tuple(args), 0)
    rows = db.all(f"SELECT c.id, c.title, c.details, c.subject, c.grade, c.created_at, u.username, u.display_name, "
                  f"(SELECT COUNT(*) FROM lesson_versions v WHERE v.subtopic_id=c.id) AS lessons FROM custom_topics c LEFT JOIN users u ON u.id=c.student_id WHERE {where} "
                  f"ORDER BY c.created_at DESC LIMIT ? OFFSET ?", (*args, limit, offset))
    return {"total": total, "items": rows}


def delete_custom_topic(topic_id: str) -> None:
    from . import mytopics
    owner = mytopics.owner_of(topic_id)
    if not owner or not mytopics.delete(owner, topic_id):
        raise AdminError("No such topic.", 404)


# ---- announcements ------------------------------------------------------------------------------
AUDIENCES = ("all", "students", "parents", "teachers", "school")


def announce(actor_id: str, title: str, body: str, audience: str, school_id: str | None = None, link: str = "") -> int:
    where, args = ["disabled=0", "username NOT LIKE 'anon-%'"], []
    if audience in ("students", "parents", "teachers"):
        where.append("role=?")
        args.append(audience[:-1])
    elif audience == "school":
        if not school_id or not db.one("SELECT 1 FROM schools WHERE id=?", (school_id,)):
            raise AdminError("Choose a school.", 400)
        where.append("school_id=?")
        args.append(school_id)
    elif audience != "all":
        raise AdminError("Unknown audience.", 400)
    ids = [r["id"] for r in db.all(f"SELECT id FROM users WHERE {' AND '.join(where)} LIMIT 5001", tuple(args))]
    if len(ids) > 5000:
        raise AdminError("That is more than 5000 people. Choose a smaller audience.", 400)
    for uid in ids:
        notify.create(uid, "announcement", title, body, link, deliver=False)
    audit.log(actor_id, "announcement", audience, {"title": title[:100], "recipients": len(ids), "school": school_id})
    return len(ids)


# ---- schools ------------------------------------------------------------------------------------
def delete_school(school_id: str) -> None:
    if not db.one("SELECT 1 FROM schools WHERE id=?", (school_id,)):
        raise AdminError("No such school.", 404)
    if db.scalar("SELECT COUNT(*) FROM users WHERE school_id=?", (school_id,), 0) or db.scalar("SELECT COUNT(*) FROM classes WHERE school_id=?", (school_id,), 0):
        raise AdminError("This school still has people or classes. Move or remove them first.", 409)
    db.run("DELETE FROM schools WHERE id=?", (school_id,))


def new_school_code(school_id: str) -> str:
    if not db.one("SELECT 1 FROM schools WHERE id=?", (school_id,)):
        raise AdminError("No such school.", 404)
    code = secrets.token_hex(3).upper()
    db.run("UPDATE schools SET code=? WHERE id=?", (code, school_id))
    return code


# ---- system -------------------------------------------------------------------------------------
def _dir_size(path: Path) -> tuple[int, int]:
    files = [f for f in path.glob("*") if f.is_file()] if path.exists() else []
    return sum(f.stat().st_size for f in files), len(files)


def backups_dir() -> Path:
    return config.DATA_DIR / "backups"


def list_backups() -> list[dict]:
    d = backups_dir()
    return [{"name": f.name, "bytes": f.stat().st_size, "at": f.stat().st_mtime} for f in sorted(d.glob(f"{BACKUP_NAME}*.db"), reverse=True)] if d.exists() else []


def backup_path(name: str) -> Path:
    """Only a file this app made, inside the backups folder: nothing a person types can point anywhere else."""
    if not name.startswith(BACKUP_NAME) or not name.endswith(".db") or "/" in name or "\\" in name or ".." in name:
        raise AdminError("No such backup.", 404)
    p = backups_dir() / name
    if not p.is_file():
        raise AdminError("No such backup.", 404)
    return p


def system() -> dict:
    tts_bytes, tts_files = _dir_size(voice.CACHE)
    return {
        "app": {"auth": config.AUTH, "provider": config.PROVIDER, "model": config.model(), "mock": config.MOCK, "concurrency": config.CONCURRENCY, "prefetch": config.PREFETCH},
        "settings": {"idle_minutes": config.IDLE_MINUTES, "session_days": config.SESSION_DAYS, "remember_days": config.REMEMBER_DAYS, "otp_minutes": config.OTP_MINUTES, "otp_resend_seconds": config.OTP_RESEND_SECONDS,
                     "rate_ai_per_minute": config.RATE_AI, "rate_auth_per_minute": config.RATE_AUTH, "backup_keep": config.BACKUP_KEEP, "languages": len(config.LANGUAGES)},
        "channels": {"email": notify.email_ready(), "push": notify.push_ready(), "whatsapp": notify.whatsapp_ready()},
        "storage": {"db_bytes": db.path().stat().st_size if db.path().exists() else 0, "tts_cache_bytes": tts_bytes, "tts_cache_files": tts_files, "backups": list_backups()},
        "sessions": {"active": db.scalar("SELECT COUNT(*) FROM sessions WHERE expires_at>?", (time.time(),), 0), "pending_codes": db.scalar("SELECT COUNT(*) FROM email_otps", (), 0)},
    }


def purge(what: str) -> int:
    """Housekeeping. -> how many things were removed."""
    now = time.time()
    if what == "sessions":
        n = db.scalar("SELECT COUNT(*) FROM sessions WHERE expires_at<? OR COALESCE(last_seen, created_at)<?", (now, now - config.IDLE_MINUTES * 60), 0)
        db.run("DELETE FROM sessions WHERE expires_at<? OR COALESCE(last_seen, created_at)<?", (now, now - config.IDLE_MINUTES * 60))
        return n
    if what == "codes":
        n = db.scalar("SELECT COUNT(*) FROM email_otps WHERE expires_at<?", (now,), 0)
        db.run("DELETE FROM email_otps WHERE expires_at<?", (now,))
        return n
    if what == "tts_cache":
        n = 0
        for f in (voice.CACHE.glob("*") if voice.CACHE.exists() else []):
            if f.is_file():
                f.unlink(missing_ok=True)
                n += 1
        return n
    if what == "audit_90d":
        n = db.scalar("SELECT COUNT(*) FROM audit_log WHERE ts<?", (now - 90 * 86400,), 0)
        db.run("DELETE FROM audit_log WHERE ts<?", (now - 90 * 86400,))
        return n
    raise AdminError("Unknown housekeeping task.", 400)


def user_detail(user_id: str) -> dict | None:
    u = accounts.get_user(user_id)
    if not u:
        return None
    from . import learning, store
    out = {k: u[k] for k in ("id", "username", "display_name", "role", "consent", "school_id", "disabled", "created_at", "last_login", "birth_year", "email", "email_verified") if k in u}
    out["sessions"] = db.scalar("SELECT COUNT(*) FROM sessions WHERE user_id=? AND expires_at>?", (user_id, time.time()), 0)
    school = db.one("SELECT id, name, code FROM schools WHERE id=?", (u.get("school_id"),)) if u.get("school_id") else None
    out["school"] = school
    if u["role"] == "student":
        out["profile"] = store.get_student(user_id)
        prog = store.progress_map(user_id)
        out["learning"] = {"topics_started": len(prog), "topics_completed": sum(1 for p in prog.values() if p["status"] == "completed"), "xp": learning.total_xp(user_id), "streak": store.streak(user_id),
                           "custom_topics": db.scalar("SELECT COUNT(*) FROM custom_topics WHERE student_id=?", (user_id,), 0), "study_notes": db.scalar("SELECT COUNT(*) FROM study_notes WHERE student_id=?", (user_id,), 0),
                           "classes": db.all("SELECT c.id, c.name FROM classes c JOIN class_members m ON m.class_id=c.id WHERE m.student_id=?", (user_id,)),
                           "parents": [{"id": r["id"], "name": r["display_name"]} for r in db.all("SELECT u.id, u.display_name FROM parent_links p JOIN users u ON u.id=p.parent_id WHERE p.student_id=?", (user_id,))]}
    if u["role"] == "parent":
        out["children"] = accounts.children_of(user_id)
    if u["role"] == "teacher":
        out["classes_taught"] = db.all("SELECT id, name, grade FROM classes WHERE teacher_id=?", (user_id,))
    out["recent_activity"] = db.all("SELECT ts, action, target FROM audit_log WHERE actor_id=? OR target=? ORDER BY id DESC LIMIT 15", (user_id, user_id))
    return out
