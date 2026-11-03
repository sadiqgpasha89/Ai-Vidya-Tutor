"""Teacher classes, joining by code, assignments with due dates, and class-safe leaderboards."""
from __future__ import annotations

import secrets
import time

from . import accounts, curriculum, db, notify

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _code(n: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


def create_class(teacher: dict, name: str, grade: int | None) -> dict:
    cid = accounts.new_id("c")
    db.run("INSERT INTO classes (id, school_id, teacher_id, name, grade, join_code, created_at) VALUES (?,?,?,?,?,?,?)",
           (cid, teacher.get("school_id"), teacher["id"], name.strip()[:60], grade, _code(), time.time()))
    return get_class(cid)


def get_class(class_id: str) -> dict | None:
    return db.one("SELECT * FROM classes WHERE id=?", (class_id,))


def classes_for(user: dict) -> list[dict]:
    if user["role"] == "admin":
        rows = db.all("SELECT * FROM classes ORDER BY created_at DESC")
    elif user["role"] == "school_admin" and user.get("school_id"):
        rows = db.all("SELECT * FROM classes WHERE school_id=? ORDER BY created_at DESC", (user["school_id"],))
    elif user["role"] == "teacher":
        rows = db.all("SELECT * FROM classes WHERE teacher_id=? ORDER BY created_at DESC", (user["id"],))
    else:  # student: the classes they joined
        rows = db.all("SELECT c.* FROM classes c JOIN class_members m ON m.class_id=c.id WHERE m.student_id=?", (user["id"],))
    for r in rows:
        r["members"] = db.scalar("SELECT COUNT(*) FROM class_members WHERE class_id=?", (r["id"],), 0)
    return rows


def can_manage(user: dict, cls: dict) -> bool:
    return bool(user["role"] == "admin" or cls["teacher_id"] == user["id"]
                or (user["role"] == "school_admin" and user.get("school_id") and cls["school_id"] == user["school_id"]))


def join(student: dict, code: str, nickname: str, share_leaderboard: bool) -> dict:
    cls = db.one("SELECT * FROM classes WHERE join_code=?", (code.strip().upper(),))
    if not cls:
        raise accounts.AccountError("Class code not found.", 404)
    db.run("INSERT INTO class_members (class_id, student_id, nickname, share_leaderboard, joined_at) VALUES (?,?,?,?,?) ON CONFLICT DO UPDATE SET nickname=?, share_leaderboard=?",
           (cls["id"], student["id"], nickname.strip()[:20] or "Student", int(share_leaderboard), time.time(), nickname.strip()[:20] or "Student", int(share_leaderboard)))
    return cls


def leave(student_id: str, class_id: str) -> None:
    db.run("DELETE FROM class_members WHERE class_id=? AND student_id=?", (class_id, student_id))


def roster(class_id: str) -> list[dict]:
    return db.all("SELECT u.id, u.display_name, u.username, m.nickname, m.share_leaderboard, s.grade FROM class_members m JOIN users u ON u.id=m.student_id "
                  "LEFT JOIN students s ON s.id=u.id WHERE m.class_id=? ORDER BY u.display_name", (class_id,))


def remove_member(class_id: str, student_id: str) -> None:
    leave(student_id, class_id)


# ---- assignments -------------------------------------------------------------------------------
def assign(teacher: dict, class_id: str, kind: str, subtopic_id: str | None, title: str, note: str, due_at: float | None) -> dict:
    cls = get_class(class_id)
    if not cls or not can_manage(teacher, cls):
        raise accounts.AccountError("Not allowed.", 403)
    if kind not in ("lesson", "quiz", "practice", "test"):
        raise accounts.AccountError("Unknown assignment type.")
    if subtopic_id and not curriculum.get_subtopic(subtopic_id, owner=""):
        raise accounts.AccountError("Unknown topic.", 404)
    aid = accounts.new_id("a")
    topic = curriculum.get_subtopic(subtopic_id) if subtopic_id else None
    db.run("INSERT INTO assignments (id, class_id, kind, subtopic_id, title, note, due_at, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
           (aid, class_id, kind, subtopic_id, title.strip()[:120] or (topic["title"] if topic else "Assignment"), note[:500], due_at, teacher["id"], time.time()))
    for m in roster(class_id):
        db.run("INSERT OR IGNORE INTO assignment_status (assignment_id, student_id, status) VALUES (?,?, 'todo')", (aid, m["id"]))
        notify.create(m["id"], "assignment", f"New {kind}: {title.strip()[:60]}", note[:200], "/#/assignments")
    return db.one("SELECT * FROM assignments WHERE id=?", (aid,))


def assignments_for_student(student_id: str) -> list[dict]:
    rows = db.all("""SELECT a.*, s.status, s.score, s.completed_at, c.name AS class_name FROM assignments a JOIN class_members m ON m.class_id=a.class_id
                     JOIN classes c ON c.id=a.class_id LEFT JOIN assignment_status s ON s.assignment_id=a.id AND s.student_id=m.student_id
                     WHERE m.student_id=? ORDER BY (s.status='done'), a.due_at IS NULL, a.due_at""", (student_id,))
    for r in rows:
        r["status"] = r["status"] or "todo"
        r["topic"] = (curriculum.get_subtopic(r["subtopic_id"]) or {}).get("title") if r["subtopic_id"] else None
        r["overdue"] = bool(r["due_at"] and r["due_at"] < time.time() and r["status"] != "done")
    return rows


def complete_assignment(student_id: str, assignment_id: str, score: float | None = None) -> None:
    db.run("INSERT INTO assignment_status (assignment_id, student_id, status, score, completed_at) VALUES (?,?, 'done', ?, ?) ON CONFLICT DO UPDATE SET status='done', score=?, completed_at=?",
           (assignment_id, student_id, score, time.time(), score, time.time()))


def auto_complete(student_id: str, subtopic_id: str, kind: str, score: float | None = None) -> int:
    """When a student finishes a lesson/quiz/practice, tick off any matching open assignment."""
    rows = db.all("""SELECT a.id FROM assignments a JOIN class_members m ON m.class_id=a.class_id LEFT JOIN assignment_status s ON s.assignment_id=a.id AND s.student_id=m.student_id
                     WHERE m.student_id=? AND a.subtopic_id=? AND a.kind=? AND COALESCE(s.status,'todo')!='done'""", (student_id, subtopic_id, kind))
    for r in rows:
        complete_assignment(student_id, r["id"], score)
    return len(rows)


def assignment_progress(assignment_id: str) -> list[dict]:
    return db.all("""SELECT u.id, u.display_name, COALESCE(s.status,'todo') AS status, s.score, s.completed_at FROM assignments a JOIN class_members m ON m.class_id=a.class_id
                     JOIN users u ON u.id=m.student_id LEFT JOIN assignment_status s ON s.assignment_id=a.id AND s.student_id=u.id WHERE a.id=? ORDER BY u.display_name""", (assignment_id,))


def leaderboard(class_id: str, days: int = 7) -> list[dict]:
    """Opt-in only, nickname only, weekly XP: designed to motivate without exposing names or marks."""
    since = time.time() - days * 86400
    rows = db.all("""SELECT m.nickname, m.student_id, COALESCE(SUM(x.points),0) AS xp FROM class_members m LEFT JOIN xp_events x ON x.student_id=m.student_id AND x.created_at>=?
                     WHERE m.class_id=? AND m.share_leaderboard=1 GROUP BY m.student_id ORDER BY xp DESC LIMIT 20""", (since, class_id))
    return [{"rank": i + 1, "nickname": r["nickname"], "xp": r["xp"], "student_id": r["student_id"]} for i, r in enumerate(rows)]
