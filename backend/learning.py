"""Everything a student accumulates: chat history, board, notes, highlights, bookmarks, mistakes, flashcards, XP, badges, plan."""
from __future__ import annotations

import json
import math
import time
from datetime import date, datetime

from . import curriculum, db, store

# ---- chat & board persistence ------------------------------------------------------------------
def save_message(student_id: str, subtopic_id: str, role: str, content: str) -> None:
    db.run("INSERT INTO chat_messages (student_id, subtopic_id, role, content, created_at) VALUES (?,?,?,?,?)",
           (student_id, subtopic_id, role, content[:8000], time.time()))


def chat_history(student_id: str, subtopic_id: str, limit: int = 60) -> list[dict]:
    rows = db.all("SELECT role, content, created_at FROM chat_messages WHERE student_id=? AND subtopic_id=? ORDER BY id DESC LIMIT ?", (student_id, subtopic_id, limit))
    return rows[::-1]


def drop_last_exchange(student_id: str, subtopic_id: str) -> None:
    """For "regenerate answer": remove the last assistant reply and the question it answered."""
    rows = db.all("SELECT id, role FROM chat_messages WHERE student_id=? AND subtopic_id=? ORDER BY id DESC LIMIT 2", (student_id, subtopic_id))
    if rows and rows[0]["role"] == "assistant":
        db.run("DELETE FROM chat_messages WHERE id=?", (rows[0]["id"],))
        if len(rows) > 1 and rows[1]["role"] == "user":
            db.run("DELETE FROM chat_messages WHERE id=?", (rows[1]["id"],))


def clear_chat(student_id: str, subtopic_id: str) -> None:
    db.run("DELETE FROM chat_messages WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id))
    db.run("DELETE FROM boards WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id))


def save_board(student_id: str, subtopic_id: str, title: str, markdown: str, svg: str | None) -> int:
    return db.run("INSERT INTO boards (student_id, subtopic_id, title, markdown, svg, created_at) VALUES (?,?,?,?,?,?)",
                  (student_id, subtopic_id, title, markdown, svg, time.time()))


def boards(student_id: str, subtopic_id: str) -> list[dict]:
    return db.all("SELECT id, title, markdown, svg, created_at FROM boards WHERE student_id=? AND subtopic_id=? ORDER BY id DESC LIMIT 40", (student_id, subtopic_id))


# ---- notes, highlights, bookmarks --------------------------------------------------------------
def add_note(student_id: str, subtopic_id: str | None, title: str, body: str) -> int:
    now = time.time()
    return db.run("INSERT INTO notes (student_id, subtopic_id, title, body, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                  (student_id, subtopic_id, title[:120], body[:20000], now, now))


def update_note(student_id: str, note_id: int, title: str, body: str) -> None:
    db.run("UPDATE notes SET title=?, body=?, updated_at=? WHERE id=? AND student_id=?", (title[:120], body[:20000], time.time(), note_id, student_id))


def delete_note(student_id: str, note_id: int) -> None:
    db.run("DELETE FROM notes WHERE id=? AND student_id=?", (note_id, student_id))


def notes(student_id: str, subtopic_id: str | None = None) -> list[dict]:
    if subtopic_id:
        return db.all("SELECT * FROM notes WHERE student_id=? AND subtopic_id=? ORDER BY updated_at DESC", (student_id, subtopic_id))
    return db.all("SELECT * FROM notes WHERE student_id=? ORDER BY updated_at DESC LIMIT 300", (student_id,))


def add_highlight(student_id: str, subtopic_id: str, section_index: int, text: str, color: str = "yellow") -> int:
    return db.run("INSERT INTO highlights (student_id, subtopic_id, section_index, text, color, created_at) VALUES (?,?,?,?,?,?)",
                  (student_id, subtopic_id, section_index, text[:600], color if color in ("yellow", "green", "pink", "blue") else "yellow", time.time()))


def highlights(student_id: str, subtopic_id: str) -> list[dict]:
    return db.all("SELECT id, section_index, text, color FROM highlights WHERE student_id=? AND subtopic_id=? ORDER BY id", (student_id, subtopic_id))


def delete_highlight(student_id: str, hid: int) -> None:
    db.run("DELETE FROM highlights WHERE id=? AND student_id=?", (hid, student_id))


def toggle_bookmark(student_id: str, subtopic_id: str) -> bool:
    if db.one("SELECT 1 FROM bookmarks WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id)):
        db.run("DELETE FROM bookmarks WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id))
        return False
    db.run("INSERT INTO bookmarks VALUES (?,?,?)", (student_id, subtopic_id, time.time()))
    return True


def bookmarks(student_id: str) -> list[str]:
    return [r["subtopic_id"] for r in db.all("SELECT subtopic_id FROM bookmarks WHERE student_id=? ORDER BY created_at DESC", (student_id,))]


def export_notes_markdown(student_id: str) -> str:
    out = ["# My AIVidya notes\n"]
    for n in reversed(notes(student_id)):
        t = curriculum.get_subtopic(n["subtopic_id"]) if n["subtopic_id"] else None
        out.append(f"## {n['title'] or 'Note'}" + (f"  \n*{t['subject_name']} · Grade {t['grade']} · {t['title']}*" if t else ""))
        out.append(n["body"] + "\n")
    for sid in bookmarks(student_id):
        t = curriculum.get_subtopic(sid)
        if t:
            out.append(f"- ⭐ {t['subject_name']} · Grade {t['grade']} · {t['title']}")
    return "\n".join(out)


# ---- mistakes notebook -------------------------------------------------------------------------
def add_mistake(student_id: str, subtopic_id: str, source: str, question: str, options: list | None, chosen: str, correct: str,
                explanation: str = "", concept: str = "") -> int:
    existing = db.one("SELECT id FROM mistakes WHERE student_id=? AND question=? AND resolved_at IS NULL", (student_id, question))
    if existing:
        db.run("UPDATE mistakes SET times_wrong=times_wrong+1, chosen=? WHERE id=?", (chosen, existing["id"]))
        return existing["id"]
    return db.run("INSERT INTO mistakes (student_id, subtopic_id, source, question, options, chosen, correct, explanation, concept, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (student_id, subtopic_id, source, question[:2000], json.dumps(options or [], ensure_ascii=False), chosen[:500], correct[:500], explanation[:2000], concept[:200], time.time()))


def mistakes(student_id: str, include_resolved: bool = False) -> list[dict]:
    sql = "SELECT * FROM mistakes WHERE student_id=?" + ("" if include_resolved else " AND resolved_at IS NULL") + " ORDER BY times_wrong DESC, id DESC LIMIT 200"
    rows = db.all(sql, (student_id,))
    for r in rows:
        r["options"] = json.loads(r["options"] or "[]")
    return rows


def resolve_mistake(student_id: str, mistake_id: int) -> None:
    db.run("UPDATE mistakes SET resolved_at=? WHERE id=? AND student_id=?", (time.time(), mistake_id, student_id))


# ---- flashcards (SM-2) -------------------------------------------------------------------------
def store_cards(subtopic_id: str, language: str, cards: list[dict]) -> None:
    db.run("DELETE FROM flashcards WHERE subtopic_id=? AND language=?", (subtopic_id, language))
    for c in cards:
        db.run("INSERT INTO flashcards (subtopic_id, language, front, back, kind, created_at) VALUES (?,?,?,?,?,?)",
               (subtopic_id, language, c["front"][:500], c["back"][:1000], c.get("kind", "concept"), time.time()))


def cards_for(subtopic_id: str, language: str) -> list[dict]:
    return db.all("SELECT id, front, back, kind FROM flashcards WHERE subtopic_id=? AND language=? ORDER BY id", (subtopic_id, language))


def due_cards(student_id: str, limit: int = 20) -> list[dict]:
    """Cards the student has seen and that are due, plus a few new cards from topics they have completed."""
    now = time.time()
    due = db.all("""SELECT f.id, f.subtopic_id, f.front, f.back, f.kind FROM card_state s JOIN flashcards f ON f.id=s.card_id
                    WHERE s.student_id=? AND s.due_at<=? ORDER BY s.due_at LIMIT ?""", (student_id, now, limit))
    if len(due) < limit:
        fresh = db.all("""SELECT f.id, f.subtopic_id, f.front, f.back, f.kind FROM flashcards f JOIN progress p ON p.subtopic_id=f.subtopic_id AND p.student_id=?
                          WHERE f.id NOT IN (SELECT card_id FROM card_state WHERE student_id=?) ORDER BY p.last_studied DESC LIMIT ?""", (student_id, student_id, limit - len(due)))
        due += fresh
    return due


def review_card(student_id: str, card_id: int, grade: int) -> dict:
    """grade: 0 again, 1 hard, 2 good, 3 easy (SM-2 flavoured)."""
    row = db.one("SELECT * FROM card_state WHERE student_id=? AND card_id=?", (student_id, card_id)) or {"ease": 2.5, "interval_days": 0, "reps": 0, "lapses": 0}
    ease, interval, reps, lapses = row["ease"], row["interval_days"], row["reps"], row["lapses"]
    if grade == 0:
        interval, lapses, reps, ease = 0.0, lapses + 1, 0, max(1.3, ease - 0.2)
        due = time.time() + 600
    else:
        reps += 1
        ease = max(1.3, ease + (0.1 if grade == 3 else 0 if grade == 2 else -0.15))
        interval = 1.0 if reps == 1 else 3.0 if reps == 2 else interval * ease * (0.8 if grade == 1 else 1.3 if grade == 3 else 1.0)
        due = time.time() + interval * 86400
    db.run("""INSERT INTO card_state (student_id, card_id, ease, interval_days, due_at, reps, lapses) VALUES (?,?,?,?,?,?,?)
              ON CONFLICT DO UPDATE SET ease=?, interval_days=?, due_at=?, reps=?, lapses=?""",
           (student_id, card_id, ease, interval, due, reps, lapses, ease, interval, due, reps, lapses))
    return {"interval_days": round(interval, 1), "due_at": due}


def card_counts(student_id: str) -> dict:
    return {"reviewed": db.scalar("SELECT COUNT(*) FROM card_state WHERE student_id=?", (student_id,), 0),
            "due": db.scalar("SELECT COUNT(*) FROM card_state WHERE student_id=? AND due_at<=?", (student_id, time.time()), 0)}


# ---- XP, levels, badges ------------------------------------------------------------------------
BADGES = {
    "first_lesson": ("🌱", "First lesson", "Completed your first topic"),
    "streak_3": ("🔥", "3-day streak", "Studied three days in a row"),
    "streak_7": ("🔥", "7-day streak", "A whole week"),
    "streak_30": ("🏆", "30-day streak", "A whole month!"),
    "perfect_quiz": ("💯", "Perfect quiz", "All answers right"),
    "teacher": ("🗣️", "Good teacher", "Scored 80%+ on Teach it back"),
    "mistake_fixer": ("🛠️", "Mistake fixer", "Fixed 10 past mistakes"),
    "explorer": ("🧭", "Explorer", "Studied 3 different subjects"),
    "xp_500": ("⭐", "500 XP", "Earned 500 XP"),
    "xp_2000": ("🌟", "2000 XP", "Earned 2000 XP"),
    "card_master": ("🃏", "Card master", "Reviewed 50 flashcards"),
    "viva_star": ("🎤", "Viva star", "Scored 80%+ in an oral viva"),
    "daily_first": ("☀️", "Daily starter", "Finished your first Daily 5"),
    "daily_7": ("📅", "Daily habit", "Finished the Daily 5 on 7 different days"),
    "answer_ace": ("✍️", "Answer ace", "Earned full marks on a written answer"),
}


def level_for(xp: int) -> dict:
    level = int(math.sqrt(xp / 50)) + 1
    base, nxt = 50 * (level - 1) ** 2, 50 * level ** 2
    return {"level": level, "xp": xp, "into": xp - base, "needed": nxt - base}


def total_xp(student_id: str) -> int:
    return int(db.scalar("SELECT SUM(points) FROM xp_events WHERE student_id=?", (student_id,), 0))


def today_xp(student_id: str) -> int:
    start = datetime.combine(date.today(), datetime.min.time()).timestamp()
    return int(db.scalar("SELECT SUM(points) FROM xp_events WHERE student_id=? AND created_at>=?", (student_id, start), 0))


def award(student_id: str, kind: str, points: int, **ctx) -> dict:
    """Give XP and any badges that are now earned. -> {points, xp, level, new_badges}"""
    points = max(0, int(points))
    if points:
        db.run("INSERT INTO xp_events (student_id, kind, points, created_at) VALUES (?,?,?,?)", (student_id, kind, points, time.time()))
    xp = total_xp(student_id)
    earned = {r["badge"] for r in db.all("SELECT badge FROM badges WHERE student_id=?", (student_id,))}
    checks = {
        "first_lesson": db.scalar("SELECT COUNT(*) FROM progress WHERE student_id=? AND status='completed'", (student_id,), 0) >= 1,
        "streak_3": store.streak(student_id) >= 3, "streak_7": store.streak(student_id) >= 7, "streak_30": store.streak(student_id) >= 30,
        "perfect_quiz": kind == "quiz" and ctx.get("correct") == ctx.get("total") and ctx.get("total", 0) >= 3,
        "teacher": kind == "teachback" and ctx.get("score", 0) >= 80,
        "mistake_fixer": db.scalar("SELECT COUNT(*) FROM mistakes WHERE student_id=? AND resolved_at IS NOT NULL", (student_id,), 0) >= 10,
        "explorer": len({s[:3] for s in (r["subtopic_id"] for r in db.all("SELECT subtopic_id FROM progress WHERE student_id=?", (student_id,)))}) >= 3,
        "xp_500": xp >= 500, "xp_2000": xp >= 2000,
        "card_master": db.scalar("SELECT COUNT(*) FROM card_state WHERE student_id=?", (student_id,), 0) >= 50,
        "viva_star": kind == "viva" and ctx.get("score", 0) >= 80,
        "daily_first": kind == "daily",
        "daily_7": kind == "daily" and db.scalar("SELECT COUNT(*) FROM daily_sets WHERE student_id=? AND completed_at IS NOT NULL", (student_id,), 0) >= 7,
        "answer_ace": kind == "answer" and ctx.get("full", False),
    }
    new = [b for b, ok in checks.items() if ok and b not in earned]
    for b in new:
        db.run("INSERT OR IGNORE INTO badges VALUES (?,?,?)", (student_id, b, time.time()))
    return {"points": points, "xp": xp, "level": level_for(xp), "new_badges": [{"id": b, "icon": BADGES[b][0], "name": BADGES[b][1], "about": BADGES[b][2]} for b in new]}


def profile_card(student_id: str) -> dict:
    xp = total_xp(student_id)
    badges = [{"id": r["badge"], "icon": BADGES[r["badge"]][0], "name": BADGES[r["badge"]][1], "about": BADGES[r["badge"]][2]}
              for r in db.all("SELECT badge FROM badges WHERE student_id=? ORDER BY earned_at", (student_id,)) if r["badge"] in BADGES]
    st = store.get_student(student_id) or {}
    return {"xp": xp, "level": level_for(xp), "today_xp": today_xp(student_id), "daily_goal": int(st.get("daily_minutes") or 30), "badges": badges,
            "all_badges": [{"id": k, "icon": v[0], "name": v[1], "about": v[2]} for k, v in BADGES.items()], "streak": store.streak(student_id)}


# ---- feedback & reports ------------------------------------------------------------------------
def add_feedback(student_id: str, subtopic_id: str, section_index: int, rating: int, tag: str = "") -> None:
    db.run("DELETE FROM feedback WHERE student_id=? AND subtopic_id=? AND section_index=?", (student_id, subtopic_id, section_index))
    db.run("INSERT INTO feedback (student_id, subtopic_id, section_index, rating, tag, created_at) VALUES (?,?,?,?,?,?)",
           (student_id, subtopic_id, section_index, max(-1, min(1, rating)), tag[:30], time.time()))


def add_report(student_id: str | None, kind: str, subtopic_id: str, ref: str, message: str) -> int:
    return db.run("INSERT INTO reports (student_id, kind, subtopic_id, ref, message, created_at) VALUES (?,?,?,?,?,?)",
                  (student_id, kind, subtopic_id, ref[:500], message[:2000], time.time()))


# ---- tutor memory ------------------------------------------------------------------------------
def memory(student_id: str) -> str:
    return (db.one("SELECT summary FROM student_memory WHERE student_id=?", (student_id,)) or {}).get("summary", "")


def bump_memory(student_id: str, threshold: int = 8) -> bool:
    """Count a student message; True when enough new messages have accrued to refresh the summary."""
    db.run("INSERT INTO student_memory (student_id, summary, msgs_since, updated_at) VALUES (?, '', 1, ?) ON CONFLICT DO UPDATE SET msgs_since=msgs_since+1",
           (student_id, time.time()))
    return (db.scalar("SELECT msgs_since FROM student_memory WHERE student_id=?", (student_id,), 0)) >= threshold


def save_memory(student_id: str, summary: str) -> None:
    db.run("UPDATE student_memory SET summary=?, msgs_since=0, updated_at=? WHERE student_id=?", (summary[:1500], time.time(), student_id))


# ---- study plan --------------------------------------------------------------------------------
MIN_PER_TOPIC = 12


def plan(student_id: str) -> dict:
    st = store.get_student(student_id)
    if not st:
        return {}
    subjects = curriculum.subjects_for(st["grade"], st.get("stream") or "", st.get("track") or "")
    prog = store.progress_map(student_id)
    pool = [s for sid in subjects for c in curriculum.chapters(sid, st["grade"], st.get("track") or "") for s in c.subtopics]
    total, done = len(pool), sum(1 for s in pool if prog.get(s.id, {}).get("status") == "completed")
    weak = [s for s in pool if (p := prog.get(s.id)) and p["status"] == "completed" and (p.get("retention") or 0) < 0.55]
    todo = [s for s in pool if s.id not in prog or prog[s.id]["status"] != "completed"]
    minutes = int(st.get("daily_minutes") or 30)
    slots = max(1, minutes // MIN_PER_TOPIC)
    out = {"minutes": minutes, "goal": st.get("goal") or "boards", "exam_date": st.get("exam_date") or "", "total": total, "done": done}
    days_left = None
    if out["exam_date"]:
        try:
            days_left = (date.fromisoformat(out["exam_date"]) - date.today()).days
        except ValueError:
            days_left = None
    out["days_left"] = days_left
    if days_left and days_left > 0:
        remaining = len(todo)
        out["topics_per_week"] = round(remaining / max(1, days_left) * 7, 1)
        out["on_track"] = remaining / days_left <= slots * 0.9
    tasks = []
    due = store.due_revisions(student_id, 3)
    for sid in due:
        t = curriculum.get_subtopic(sid)
        if t:
            tasks.append({"kind": "revise", "topic": _brief(t), "minutes": 8, "why": "Due for revision so you don't forget it"})
    cards = card_counts(student_id)["due"]
    if cards:
        tasks.append({"kind": "cards", "minutes": min(10, 2 + cards // 3), "why": f"{cards} flashcards are due"})
    left = slots - len([t for t in tasks if t["kind"] == "revise"]) // 2
    for s in weak[:1]:
        t = curriculum.get_subtopic(s.id)
        if t and not any(x.get("topic", {}).get("id") == s.id for x in tasks):
            tasks.append({"kind": "strengthen", "topic": _brief(t), "minutes": MIN_PER_TOPIC, "why": "Your recall of this is fading"})
            left -= 1
    for s in todo[:max(1, left)]:
        t = curriculum.get_subtopic(s.id)
        if t:
            tasks.append({"kind": "learn", "topic": _brief(t), "minutes": MIN_PER_TOPIC, "why": "Next topic in your syllabus"})
    if db.scalar("SELECT COUNT(*) FROM mistakes WHERE student_id=? AND resolved_at IS NULL", (student_id,), 0):
        tasks.append({"kind": "mistakes", "minutes": 6, "why": "Fix questions you got wrong before"})
    out["tasks"] = tasks
    return out


def _brief(t: dict) -> dict:
    return {k: t[k] for k in ("id", "title", "chapter", "subject", "subject_name", "grade")}
