"""Progress reports for students, parents, teachers, schools and administrators."""
from __future__ import annotations

import time

from . import curriculum, db, learning, store


def _subject_rows(student_id: str) -> list[dict]:
    st = store.get_student(student_id) or {}
    prog = store.progress_map(student_id)
    out = []
    for sid in curriculum.subjects_for(st.get("grade", 9), st.get("stream") or "", st.get("track") or ""):
        pool = [s for c in curriculum.chapters(sid, st.get("grade", 9), (st.get("track") or "CS") if st.get("grade", 9) >= 11 else "", st.get("board") or "") for s in c.subtopics]
        done = [s for s in pool if prog.get(s.id, {}).get("status") == "completed"]
        ms = [prog[s.id]["mastery"] for s in done if prog[s.id]["mastery"]]
        out.append({"subject": sid, "name": curriculum.SUBJECTS[sid]["name"], "icon": curriculum.SUBJECTS[sid]["icon"], "total": len(pool), "completed": len(done),
                    "avg_mastery": round(sum(ms) / len(ms), 2) if ms else None})
    return out


def student_overview(student_id: str) -> dict:
    st = store.get_student(student_id) or {}
    user = db.one("SELECT display_name, username, last_login FROM users WHERE id=?", (student_id,)) or {}
    prog = store.progress_map(student_id)
    weak, strong = [], []
    for tid, p in prog.items():
        t = curriculum.get_subtopic(tid, owner="")  # a student's own topics are private: never in a teacher's or parent's report
        if not t or p["status"] != "completed":
            continue
        row = {"id": tid, "title": t["title"], "subject_name": t["subject_name"], "grade": t["grade"], "mastery": p["mastery"], "retention": p["retention"]}
        (weak if (p["retention"] or p["mastery"]) < 0.55 else strong if p["mastery"] >= 0.75 else []).append(row) if True else None
    weak.sort(key=lambda r: r["retention"] or r["mastery"])
    strong.sort(key=lambda r: -r["mastery"])
    tests = [t for t in db.all("SELECT title, submitted_at, result FROM tests WHERE student_id=? AND submitted_at IS NOT NULL ORDER BY submitted_at DESC LIMIT 5", (student_id,))]
    import json
    return {
        "id": student_id, "name": user.get("display_name") or st.get("name"), "grade": st.get("grade"), "level": st.get("level"), "goal": st.get("goal"),
        "last_login": user.get("last_login"), "streak": store.streak(student_id), "active_days_30": len(store.active_days(student_id, 30)),
        "subjects": _subject_rows(student_id), "weak": weak[:8], "strong": strong[:5],
        "xp": learning.total_xp(student_id), "level_info": learning.level_for(learning.total_xp(student_id)),
        "open_mistakes": db.scalar("SELECT COUNT(*) FROM mistakes WHERE student_id=? AND resolved_at IS NULL", (student_id,), 0),
        "due_revisions": len(store.due_revisions(student_id, 50)),
        "tests": [{"title": t["title"], "at": t["submitted_at"], "percent": json.loads(t["result"])["percent"]} for t in tests],
        "topics_completed": sum(1 for p in prog.values() if p["status"] == "completed"),
    }


def weekly_summary(student_id: str) -> dict:
    since = time.time() - 7 * 86400
    user = db.one("SELECT display_name FROM users WHERE id=?", (student_id,)) or {}
    done = db.scalar("SELECT COUNT(*) FROM progress WHERE student_id=? AND status='completed' AND last_studied>=?", (student_id, since), 0)
    xp = db.scalar("SELECT SUM(points) FROM xp_events WHERE student_id=? AND created_at>=?", (student_id, since), 0)
    days = len(store.active_days(student_id, 7))
    tests = db.all("SELECT result FROM tests WHERE student_id=? AND submitted_at>=?", (student_id, since))
    import json
    pcts = [json.loads(t["result"])["percent"] for t in tests if t["result"]]
    ov = student_overview(student_id)
    lines = [f"{user.get('display_name', 'Your child')} studied on {days} of the last 7 days, worked on {done} topic(s) and earned {xp} XP."]
    if pcts:
        lines.append(f"Test average this week: {round(sum(pcts) / len(pcts))}%.")
    if ov["weak"]:
        lines.append("Worth revising: " + ", ".join(w["title"] for w in ov["weak"][:3]) + ".")
    lines.append(f"Current streak: {ov['streak']} day(s).")
    return {"name": user.get("display_name", "Your child"), "days_active": days, "topics": done, "xp": xp, "test_average": round(sum(pcts) / len(pcts)) if pcts else None,
            "weak": [w["title"] for w in ov["weak"][:3]], "text": " ".join(lines)}


def class_report(class_id: str, subject: str | None = None) -> dict:
    cls = db.one("SELECT * FROM classes WHERE id=?", (class_id,)) or {}
    members = db.all("SELECT u.id, u.display_name FROM class_members m JOIN users u ON u.id=m.student_id WHERE m.class_id=? ORDER BY u.display_name", (class_id,))
    grade = cls.get("grade") or 9
    subject = subject or "maths"
    chapters = curriculum.chapters(subject, grade, "CS" if grade >= 11 else "", "")
    cols = [{"id": c.id, "title": c.title} for c in chapters]
    rows, topic_scores = [], {}
    for m in members:
        prog = store.progress_map(m["id"])
        cells = []
        for c in chapters:
            ms = [prog[s.id]["mastery"] for s in c.subtopics if s.id in prog and prog[s.id]["status"] == "completed" and prog[s.id]["mastery"]]
            started = any(s.id in prog for s in c.subtopics)
            cells.append(round(sum(ms) / len(ms), 2) if ms else (0.0 if started else None))
            for s in c.subtopics:
                if s.id in prog and prog[s.id]["status"] == "completed":
                    topic_scores.setdefault(s.id, []).append(prog[s.id]["mastery"])
        rows.append({"id": m["id"], "name": m["display_name"], "cells": cells, "streak": store.streak(m["id"]), "xp": learning.total_xp(m["id"])})
    weak = []
    for tid, vals in topic_scores.items():
        if len(vals) >= max(2, len(members) // 3) and sum(vals) / len(vals) < 0.55:
            t = curriculum.get_subtopic(tid)
            weak.append({"id": tid, "title": t["title"], "chapter": t["chapter"], "avg": round(sum(vals) / len(vals), 2), "students": len(vals)})
    weak.sort(key=lambda r: r["avg"])
    return {"class": cls, "subject": subject, "chapters": cols, "students": rows, "weak_topics": weak[:10], "size": len(members)}


# ---- admin analytics ---------------------------------------------------------------------------
def analytics(days: int = 14) -> dict:
    since = time.time() - days * 86400
    day = lambda col: f"strftime('%Y-%m-%d', {col}, 'unixepoch', 'localtime')"  # noqa: E731
    active = db.all(f"SELECT {day('ts')} AS day, COUNT(DISTINCT user_id) AS users, COUNT(*) AS events FROM events WHERE ts>=? GROUP BY day ORDER BY day", (since,))
    calls = db.all(f"SELECT {day('ts')} AS day, kind, COUNT(*) AS calls, SUM(input_tokens) AS tin, SUM(output_tokens) AS tout, AVG(latency_ms) AS ms, SUM(1-ok) AS errors "
                   f"FROM usage WHERE ts>=? GROUP BY day, kind ORDER BY day", (since,))
    return {
        "days": days, "active_by_day": active, "model_by_day": calls,
        "users": {"students": db.scalar("SELECT COUNT(*) FROM users WHERE role='student'", (), 0), "teachers": db.scalar("SELECT COUNT(*) FROM users WHERE role='teacher'", (), 0),
                  "parents": db.scalar("SELECT COUNT(*) FROM users WHERE role='parent'", (), 0), "pending_consent": db.scalar("SELECT COUNT(*) FROM users WHERE consent='pending'", (), 0)},
        "active_7d": db.scalar("SELECT COUNT(DISTINCT user_id) FROM events WHERE ts>=?", (time.time() - 7 * 86400,), 0),
        "active_30d": db.scalar("SELECT COUNT(DISTINCT user_id) FROM events WHERE ts>=?", (time.time() - 30 * 86400,), 0),
        "lessons": {"generated": db.scalar("SELECT COUNT(*) FROM lesson_versions", (), 0), "approved": db.scalar("SELECT COUNT(*) FROM lesson_versions WHERE status='approved' AND is_active=1", (), 0),
                    "drafts": db.scalar("SELECT COUNT(*) FROM lesson_versions WHERE status='draft' AND is_active=1", (), 0)},
        "reports_open": db.scalar("SELECT COUNT(*) FROM reports WHERE status='open'", (), 0),
        "tokens": {"input": db.scalar("SELECT SUM(input_tokens) FROM usage WHERE ts>=?", (since,), 0), "output": db.scalar("SELECT SUM(output_tokens) FROM usage WHERE ts>=?", (since,), 0)},
        "learning": {"avg_mastery": round(db.scalar("SELECT AVG(mastery) FROM progress WHERE status='completed' AND mastery>0", (), 0) or 0, 2),
                     "topics_completed": db.scalar("SELECT COUNT(*) FROM progress WHERE status='completed'", (), 0),
                     "avg_test_percent": _avg_test_percent()},
        "feedback": {"up": db.scalar("SELECT COUNT(*) FROM feedback WHERE rating>0", (), 0), "down": db.scalar("SELECT COUNT(*) FROM feedback WHERE rating<0", (), 0)},
    }


def _avg_test_percent() -> float | None:
    import json
    vals = [json.loads(r["result"])["percent"] for r in db.all("SELECT result FROM tests WHERE result IS NOT NULL ORDER BY submitted_at DESC LIMIT 500")]
    return round(sum(vals) / len(vals)) if vals else None
