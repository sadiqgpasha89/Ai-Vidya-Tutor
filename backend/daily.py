"""Daily 5: five short multiple-choice questions a day, picked from what the student is about to forget, got wrong, or is studying now.

The set is made once a day (the first time it is opened) and kept. Answers are marked on the server, so the key never reaches the browser before the
student has answered; finishing the set updates the learner model, the mistakes notebook, XP and the streak.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
import uuid
from datetime import date, timedelta

from . import curriculum, db, exams, learning, store

SIZE = 5
XP_PER_RIGHT, XP_DONE, XP_PERFECT = 4, 10, 5
_building: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _today() -> str:
    return date.today().isoformat()


def _real(topic_id: str) -> bool:
    return not topic_id.startswith("my-") and curriculum.get_subtopic(topic_id) is not None  # a student's own topics have no question bank or fixed syllabus


def topics_for(student: dict) -> list[str]:
    """What today's questions should be about, most useful first: due for revision, mistakes still open, fading memory, then whatever was studied last."""
    sid = student["id"]
    prog = store.progress_map(sid)
    ids = list(store.due_revisions(sid, 3))
    ids += [r["subtopic_id"] for r in db.all("SELECT subtopic_id FROM mistakes WHERE student_id=? AND resolved_at IS NULL GROUP BY subtopic_id ORDER BY MAX(times_wrong) DESC, MAX(id) DESC LIMIT 2", (sid,))]
    fading = sorted((k for k, p in prog.items() if p["status"] == "completed" and p.get("retention") is not None and p["retention"] < 0.6), key=lambda k: prog[k]["retention"])
    ids += fading[:2]
    ids += sorted(prog, key=lambda k: -(prog[k]["last"] or 0))[:3]
    out: list[str] = []
    for i in ids:
        if i not in out and _real(i):
            out.append(i)
    return out[:SIZE]


_MARKS = re.compile(r"^\s*[-*\d.)]*\s*\(?\d+(?:\.\d+)?\s*marks?\)?\s*(?:for|:|-)?\s*|\s*\(\d+(?:\.\d+)?\)\s*$", re.I | re.M)


def _explain(text: str, right: str) -> str:
    """Examiners write a marking scheme ("1 mark for ..."); a student wants the reason. Drop the marks wording and say which option is right."""
    lines = [_MARKS.sub("", ln).strip() for ln in (text or "").splitlines()]
    body = " ".join(ln[:1].upper() + ln[1:] for ln in lines if ln).strip()
    return f"The answer is {right}. {body}".strip()[:800]


def _question(q: dict, topic_id: str, source: str, **extra) -> dict:
    right = q["options"][int(q["answer_index"])]
    raw = q.get("explanation") or q.get("marking_scheme") or q.get("answer") or ""
    return {"id": uuid.uuid4().hex[:8], "subtopic_id": topic_id, "question": q["question"], "options": q["options"], "answer_index": int(q["answer_index"]),
            "explanation": raw[:800] if source == "mistake" else _explain(raw, right), "source": source, **extra}


def _build(student: dict, topic_ids: list[str]) -> list[dict]:
    sid, out = student["id"], []
    seen: set[str] = set()
    for m in db.all("SELECT * FROM mistakes WHERE student_id=? AND resolved_at IS NULL AND options<>'[]' ORDER BY times_wrong DESC, id DESC LIMIT 6", (sid,)):
        opts = json.loads(m["options"] or "[]")
        if len(out) < 2 and len(opts) == 4 and m["correct"] in opts and m["question"] not in seen and _real(m["subtopic_id"]):
            seen.add(m["question"])
            out.append(_question({"question": m["question"], "options": opts, "answer_index": opts.index(m["correct"]), "explanation": m["explanation"]}, m["subtopic_id"], "mistake", mistake_id=m["id"]))
    for t in topic_ids:  # a question a teacher approved is better than a fresh one
        if len(out) >= SIZE:
            break
        pool = [q for q in exams.bank_search(t, "mcq", True, limit=15) if q["question"] not in seen and len(q["options"]) == 4]
        if pool:
            q = random.choice(pool)
            seen.add(q["question"])
            out.append(_question({**q, "answer_index": exams._bank_idx(q), "explanation": q["solution"] or q["answer"]}, t, "bank"))
    need = SIZE - len(out)
    if need > 0:
        covered = [q["subtopic_id"] for q in out]
        wanted = sorted(topic_ids, key=lambda t: covered.count(t))  # topics with no question yet come first
        for q in exams._gen(wanted, "mcq", 1, need, student):
            if q["question"] not in seen and len(q.get("options", [])) == 4:
                seen.add(q["question"])
                out.append(_question(q, q["subtopic_id"], "new"))
    random.shuffle(out)
    return out[:SIZE]


def _row(student_id: str, day: str) -> dict | None:
    return db.one("SELECT * FROM daily_sets WHERE student_id=? AND day=?", (student_id, day))


def _lock(student_id: str) -> threading.Lock:
    with _guard:
        return _building.setdefault(student_id, threading.Lock())


def existing(student: dict) -> dict | None:
    """Today's set if it was already made: opening it needs no model work."""
    row = _row(student["id"], _today())
    return view(student, row) if row else None


def today(student: dict) -> dict:
    """Today's set (made now if this is the first look). -> the same shape as `view`."""
    day = _today()
    row = _row(student["id"], day)
    if not row:
        with _lock(student["id"]):
            row = _row(student["id"], day)
            if not row:
                topics = topics_for(student)
                if not topics:
                    raise ValueError("Study a topic first: your Daily 5 is made from what you have been learning.")
                questions = _build(student, topics)
                if len(questions) < 3:
                    raise RuntimeError("Could not build your Daily 5 right now. Please try again in a moment.")
                db.run("INSERT OR IGNORE INTO daily_sets (student_id, day, questions, created_at) VALUES (?,?,?,?)", (student["id"], day, json.dumps(questions, ensure_ascii=False), time.time()))
                row = _row(student["id"], day)
    return view(student, row)


def view(student: dict, row: dict) -> dict:
    qs, answers = json.loads(row["questions"]), json.loads(row["answers"] or "{}")
    out = []
    for q in qs:
        t = curriculum.get_subtopic(q["subtopic_id"]) or {}
        item = {"id": q["id"], "subtopic_id": q["subtopic_id"], "topic": t.get("title", ""), "question": q["question"], "options": q["options"], "source": q["source"]}
        if q["id"] in answers:
            item["answered"] = {**answers[q["id"]], "answer_index": q["answer_index"], "explanation": q["explanation"]}
        out.append(item)
    done = bool(row["completed_at"])
    return {"day": row["day"], "questions": out, "answered": len(answers), "total": len(qs), "done": done, "score": row["score"], "summary": _summary(student, row, qs, answers) if done else None}


def _summary(student: dict, row: dict, qs: list[dict], answers: dict) -> dict:
    by: dict[str, list[int]] = {}
    for q in qs:
        c = by.setdefault(q["subtopic_id"], [0, 0])
        c[1] += 1
        c[0] += 1 if answers.get(q["id"], {}).get("correct") else 0
    return {"score": row["score"], "total": len(qs), "streak": store.streak(student["id"]),
            "topics": [{"subtopic_id": k, "title": (curriculum.get_subtopic(k) or {}).get("title", ""), "correct": v[0], "total": v[1]} for k, v in by.items()]}


def answer(student: dict, question_id: str, choice: int) -> dict:
    """Mark one answer. The last answer closes the set: learner model, mistakes, XP and streak are updated once."""
    with _lock(student["id"]):  # two quick taps must not overwrite each other's answer, or finish the set twice
        row = _row(student["id"], _today())
        if not row:
            raise ValueError("Open your Daily 5 first.")
        qs, answers = json.loads(row["questions"]), json.loads(row["answers"] or "{}")
        q = next((x for x in qs if x["id"] == question_id), None)
        if q is None:
            raise ValueError("That question is not in today's set.")
        if question_id not in answers:
            if not 0 <= int(choice) < len(q["options"]):
                raise ValueError("Pick one of the options.")
            answers[question_id] = {"choice": int(choice), "correct": int(choice) == q["answer_index"]}
            db.run("UPDATE daily_sets SET answers=? WHERE id=?", (json.dumps(answers), row["id"]))
        out = {"answered": {**answers[question_id], "answer_index": q["answer_index"], "explanation": q["explanation"]}, "count": len(answers), "total": len(qs), "done": False}
        if len(answers) >= len(qs) and not row["completed_at"]:
            out["reward"] = _finish(student, row, qs, answers)
            out["done"] = True
            out["summary"] = _summary(student, _row(student["id"], row["day"]), qs, answers)
        return out


def _finish(student: dict, row: dict, qs: list[dict], answers: dict) -> dict:
    sid = student["id"]
    right = sum(1 for a in answers.values() if a["correct"])
    db.run("UPDATE daily_sets SET completed_at=?, score=? WHERE id=?", (time.time(), right, row["id"]))
    by: dict[str, list[int]] = {}
    for q in qs:
        a = answers[q["id"]]
        c = by.setdefault(q["subtopic_id"], [0, 0])
        c[1] += 1
        c[0] += 1 if a["correct"] else 0
        if a["correct"] and q.get("mistake_id"):
            learning.resolve_mistake(sid, q["mistake_id"])  # got it right this time
        elif not a["correct"]:
            learning.add_mistake(sid, q["subtopic_id"], "daily", q["question"], q["options"], q["options"][a["choice"]], q["options"][q["answer_index"]], q["explanation"])
    for topic, (got, total) in by.items():
        store.record_evidence(sid, topic, got / total, "daily", weight=1)
    points = XP_PER_RIGHT * right + XP_DONE + (XP_PERFECT if right == len(qs) else 0)
    return learning.award(sid, "daily", points, correct=right, total=len(qs))


def status(student: dict) -> dict:
    """For the home page: no model work, no new set. state: locked (nothing studied yet) / new / started / done."""
    row = _row(student["id"], _today())
    week = []
    for back in range(6, -1, -1):
        d = (date.today() - timedelta(days=back)).isoformat()
        r = row if d == _today() else _row(student["id"], d)
        week.append({"day": d, "done": bool(r and r["completed_at"]), "score": r["score"] if r and r["completed_at"] else None})
    total = db.scalar("SELECT COUNT(*) FROM daily_sets WHERE student_id=? AND completed_at IS NOT NULL", (student["id"],), 0)
    if row:
        n = len(json.loads(row["answers"] or "{}"))
        state = "done" if row["completed_at"] else "started" if n else "new"
        return {"state": state, "answered": n, "total": len(json.loads(row["questions"])), "score": row["score"], "week": week, "completed_days": total, "ready": True}
    return {"state": "new" if topics_for(student) else "locked", "answered": 0, "total": SIZE, "score": None, "week": week, "completed_days": total, "ready": False}
