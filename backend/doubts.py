"""Doubt inbox: a student sends a doubt to the teacher of a class they belong to; the teacher answers; they can go back and forth until it is cleared.

status: open = waiting for the teacher, answered = waiting for the student, resolved = cleared by either of them.
The AI's reply (if the student chose to attach it) is shown to the teacher as what the AI said, not as something the school stands behind.
"""
from __future__ import annotations

import secrets
import time

from . import classes, curriculum, db, notify

MAX_OPEN = 5
MAX_TEXT = 4000


class DoubtError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _get(doubt_id: str) -> dict:
    d = db.one("SELECT * FROM doubts WHERE id=?", (doubt_id,))
    if not d:
        raise DoubtError("Doubt not found", 404)
    return d


def _is_staff(user: dict) -> bool:
    return user["role"] in ("teacher", "school_admin", "admin")


def _access(user: dict, d: dict) -> None:
    if user["role"] == "student":
        if d["student_id"] != user["id"]:
            raise DoubtError("Doubt not found", 404)
        return
    cls = classes.get_class(d["class_id"])
    if not _is_staff(user) or not cls or not classes.can_manage(user, cls):
        raise DoubtError("Doubt not found", 404)


def ask(student: dict, class_id: str, question: str, subtopic_id: str = "", ai_answer: str = "") -> dict:
    question = question.strip()
    if len(question) < 5:
        raise DoubtError("Write your doubt in a sentence or two.")
    if not db.one("SELECT 1 FROM class_members WHERE class_id=? AND student_id=?", (class_id, student["id"])):
        raise DoubtError("You are not in that class. Join it first with the class code.", 403)
    cls = classes.get_class(class_id)
    if db.scalar("SELECT COUNT(*) FROM doubts WHERE student_id=? AND status<>'resolved'", (student["id"],), 0) >= MAX_OPEN:
        raise DoubtError(f"You already have {MAX_OPEN} doubts waiting. Mark the ones you understand as cleared first.", 429)
    if subtopic_id and not curriculum.get_subtopic(subtopic_id, owner=student["id"]):
        subtopic_id = ""
    did, now = secrets.token_hex(6), time.time()
    db.run("INSERT INTO doubts (id, student_id, class_id, subtopic_id, question, ai_answer, status, created_at, updated_at, student_seen) VALUES (?,?,?,?,?,?, 'open', ?,?,?)",
           (did, student["id"], class_id, subtopic_id or None, question[:MAX_TEXT], ai_answer.strip()[:MAX_TEXT], now, now, now))
    notify.create(cls["teacher_id"], "doubt", f"New doubt from {student.get('name') or 'a student'}", question[:140], f"#/teach/doubts/{did}")
    return {"id": did}


def _summary(d: dict, viewer: dict) -> dict:
    last = db.one("SELECT role, body, created_at FROM doubt_messages WHERE doubt_id=? ORDER BY id DESC LIMIT 1", (d["id"],))
    t = curriculum.get_subtopic(d["subtopic_id"], owner=d["student_id"]) if d["subtopic_id"] else None
    cls = classes.get_class(d["class_id"]) or {}
    mine_seen = d["student_seen"] if viewer["role"] == "student" else d["teacher_seen"]
    waiting = (d["status"] == "answered") if viewer["role"] == "student" else (d["status"] == "open")
    out = {"id": d["id"], "status": d["status"], "question": d["question"][:200], "topic": (t or {}).get("title", ""), "subtopic_id": d["subtopic_id"] or "", "class_id": d["class_id"],
           "class_name": cls.get("name", ""), "updated_at": d["updated_at"], "created_at": d["created_at"], "replies": db.scalar("SELECT COUNT(*) FROM doubt_messages WHERE doubt_id=?", (d["id"],), 0),
           "last": (last["body"][:140] if last else ""), "new": waiting and d["updated_at"] > mine_seen}
    if viewer["role"] != "student":
        s = db.one("SELECT display_name FROM users WHERE id=?", (d["student_id"],)) or {}
        out["student"] = s.get("display_name", "Student")
    return out


def listing(user: dict, status: str = "", class_id: str = "") -> list[dict]:
    where, args = [], []
    if user["role"] == "student":
        where.append("student_id=?")
        args.append(user["id"])
    else:
        ids = [c["id"] for c in classes.classes_for(user)]
        if not ids:
            return []
        where.append(f"class_id IN ({','.join('?' * len(ids))})")
        args += ids
    if class_id:
        where.append("class_id=?")
        args.append(class_id)
    if status == "active":
        where.append("status<>'resolved'")
    elif status in ("open", "answered", "resolved"):
        where.append("status=?")
        args.append(status)
    rows = db.all(f"SELECT * FROM doubts WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT 200", tuple(args))
    return [_summary(d, user) for d in rows]


def thread(user: dict, doubt_id: str) -> dict:
    d = _get(doubt_id)
    _access(user, d)
    db.run(f"UPDATE doubts SET {'student_seen' if user['role'] == 'student' else 'teacher_seen'}=? WHERE id=?", (time.time(), doubt_id))
    msgs = db.all("SELECT m.id, m.role, m.body, m.created_at, u.display_name AS author FROM doubt_messages m LEFT JOIN users u ON u.id=m.author_id WHERE m.doubt_id=? ORDER BY m.id", (doubt_id,))
    s = db.one("SELECT display_name FROM users WHERE id=?", (d["student_id"],)) or {}
    return {**_summary(d, user), "question_full": d["question"], "ai_answer": d["ai_answer"], "student": s.get("display_name", "Student"), "messages": msgs}


def reply(user: dict, doubt_id: str, body: str) -> dict:
    body = body.strip()
    if not body:
        raise DoubtError("Write a reply first.")
    d = _get(doubt_id)
    _access(user, d)
    now, student_side = time.time(), user["role"] == "student"
    db.run("INSERT INTO doubt_messages (doubt_id, author_id, role, body, created_at) VALUES (?,?,?,?,?)", (doubt_id, user["id"], "student" if student_side else "teacher", body[:MAX_TEXT], now))
    db.run(f"UPDATE doubts SET status=?, updated_at=?, {'student_seen' if student_side else 'teacher_seen'}=? WHERE id=?", ("open" if student_side else "answered", now, now, doubt_id))
    if student_side:
        cls = classes.get_class(d["class_id"])
        if cls:
            notify.create(cls["teacher_id"], "doubt", "A student replied to a doubt", body[:140], f"#/teach/doubts/{doubt_id}")
    else:
        notify.create(d["student_id"], "doubt", "Your teacher answered your doubt", body[:140], f"#/doubts/{doubt_id}")
    return {"ok": True}


def resolve(user: dict, doubt_id: str, resolved: bool = True) -> dict:
    d = _get(doubt_id)
    _access(user, d)
    db.run("UPDATE doubts SET status=?, updated_at=? WHERE id=?", ("resolved" if resolved else "open", time.time(), doubt_id))
    return {"ok": True}


def waiting_for_teacher(user: dict) -> int:
    """For the teacher's menu: doubts nobody has answered yet."""
    ids = [c["id"] for c in classes.classes_for(user)]
    if not ids:
        return 0
    return db.scalar(f"SELECT COUNT(*) FROM doubts WHERE status='open' AND class_id IN ({','.join('?' * len(ids))})", tuple(ids), 0)
