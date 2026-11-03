"""Topics a student adds themselves ("how do black holes form?", "the history of chess"). They are private to that student:
the local model writes the explanation on demand, exactly as for a syllabus topic, and nobody else (teachers included) can open it."""
from __future__ import annotations

import re
import secrets
import time

from . import curriculum, db, moderation

MAX_TOPICS = 40
PREFIX = "my-"
GENERAL = "general"


class TopicError(ValueError):
    """The message is safe to show to the student."""


def is_custom(subtopic_id: str) -> bool:
    return isinstance(subtopic_id, str) and subtopic_id.startswith(PREFIX)


def _clean(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", moderation.scrub_untrusted(text or "")).strip()[:limit]


def create(student: dict, title: str, details: str = "", subject: str = GENERAL) -> dict:
    title, details = _clean(title, 120), _clean(details, 500)
    if len(title) < 3:
        raise TopicError("Give your topic a name of at least 3 letters.")
    if not re.search(r"[^\W\d_]{3}", title):
        raise TopicError("Please write the topic in words, for example “How do vaccines work?”.")
    for text in (title, details):
        verdict = moderation.check_input(text, student.get("language", "en"), deep=True) if text else {"action": "allow"}
        if verdict["action"] in ("block", "support"):
            raise TopicError("I can't write a lesson on that. Pick something you would like to learn about school subjects or the world around you.")
    if subject not in curriculum.SUBJECTS:
        subject = GENERAL
    if db.scalar("SELECT COUNT(*) FROM custom_topics WHERE student_id=?", (student["id"],), 0) >= MAX_TOPICS:
        raise TopicError(f"You already have {MAX_TOPICS} topics of your own. Remove one you no longer need first.")
    dup = db.one("SELECT * FROM custom_topics WHERE student_id=? AND lower(title)=lower(?)", (student["id"], title))
    if dup:
        return _public(dup)
    tid = PREFIX + secrets.token_hex(8)
    db.run("INSERT INTO custom_topics (id, student_id, subject, title, details, grade, created_at) VALUES (?,?,?,?,?,?,?)",
           (tid, student["id"], subject, title, details, int(student.get("grade") or 9), time.time()))
    return _public(db.one("SELECT * FROM custom_topics WHERE id=?", (tid,)))


def _public(row: dict) -> dict:
    return {"id": row["id"], "title": row["title"], "details": row["details"], "subject": row["subject"], "grade": row["grade"], "created_at": row["created_at"]}


def list_for(student_id: str) -> list[dict]:
    return [_public(r) for r in db.all("SELECT * FROM custom_topics WHERE student_id=? ORDER BY created_at DESC", (student_id,))]


def owner_of(subtopic_id: str) -> str | None:
    row = db.one("SELECT student_id FROM custom_topics WHERE id=?", (subtopic_id,))
    return row["student_id"] if row else None


def topic(subtopic_id: str, owner: str | None = None) -> dict | None:
    """The same shape as a syllabus topic (see curriculum.get_subtopic). `owner`: only that student may see it; None skips the check (internal use)."""
    row = db.one("SELECT * FROM custom_topics WHERE id=?", (subtopic_id,))
    if not row or (owner is not None and row["student_id"] != owner):
        return None
    meta = curriculum.SUBJECTS.get(row["subject"]) or {"name": "My topics"}
    return {"id": row["id"], "title": row["title"], "chapter_id": "my-topics", "chapter": "My topics", "subject": row["subject"], "subject_name": meta["name"], "grade": row["grade"],
            "track": "", "board": "", "chapter_subtopics": [], "prev": None, "next": None, "custom": True, "note": row["details"]}


def _erase_content(subtopic_id: str) -> None:
    for table in ("lesson_versions", "extras", "chat_messages", "boards", "notes", "highlights", "bookmarks", "mistakes", "progress", "signals", "revision", "activity",
                  "practice_items", "feedback", "flashcards", "viva_sessions", "study_notes"):
        try:
            db.run(f"DELETE FROM {table} WHERE subtopic_id=?", (subtopic_id,))
        except Exception:  # noqa: BLE001 - a table without that column simply has nothing to remove
            continue


def delete(student_id: str, subtopic_id: str) -> bool:
    if owner_of(subtopic_id) != student_id:
        return False
    _erase_content(subtopic_id)
    db.run("DELETE FROM custom_topics WHERE id=?", (subtopic_id,))
    return True


def delete_all(student_id: str) -> None:
    for r in db.all("SELECT id FROM custom_topics WHERE student_id=?", (student_id,)):
        delete(student_id, r["id"])
