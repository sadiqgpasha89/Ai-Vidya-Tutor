"""Student profile, per-topic progress and the learner model (knowledge tracing + forgetting curve)."""
from __future__ import annotations

import math
import re
import time
from datetime import date, datetime, timedelta, UTC

from . import config, db

ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Bayesian knowledge tracing parameters (4-option questions => guess 0.25)
P_INIT, P_LEARN, P_SLIP, P_GUESS = 0.30, 0.15, 0.10, 0.25
RETAIN_TARGET = 0.70  # schedule a revision when predicted recall drops to this


def valid_id(student_id: str) -> bool:
    return bool(ID_RE.match(student_id or ""))


# ---- profile -----------------------------------------------------------------------------------
def upsert_student(student_id: str, name: str, grade: int, language: str, level: str, board: str, **extra) -> dict:
    fields = {k: extra[k] for k in ("stream", "track", "goal", "exam_date", "daily_minutes") if k in extra and extra[k] is not None}
    db.run(
        """INSERT INTO students (id, name, grade, language, level, board, created_at) VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, grade=excluded.grade,
           language=excluded.language, level=excluded.level, board=excluded.board""",
        (student_id, name, grade, language, level, board, time.time()),
    )
    for col, val in fields.items():
        db.run(f"UPDATE students SET {col}=? WHERE id=?", (val, student_id))
    return get_student(student_id)


def get_student(student_id: str) -> dict | None:
    return db.one("SELECT * FROM students WHERE id=?", (student_id,))


def _touch_activity(student_id: str) -> None:
    db.run("INSERT OR IGNORE INTO activity VALUES (?,?)", (student_id, date.today().isoformat()))


# ---- knowledge tracing -------------------------------------------------------------------------
def bkt_update(p: float, score: float, weight: int = 1) -> float:
    """Soft Bayesian knowledge-tracing update: `score` in 0..1 is the evidence, applied `weight` times."""
    score = max(0.0, min(1.0, score))
    for _ in range(max(1, min(weight, 8))):
        right = p * (1 - P_SLIP) / (p * (1 - P_SLIP) + (1 - p) * P_GUESS)
        wrong = p * P_SLIP / (p * P_SLIP + (1 - p) * (1 - P_GUESS))
        post = score * right + (1 - score) * wrong
        p = post + (1 - post) * P_LEARN
    return min(max(p, 0.01), 0.99)


def retention(p_known: float | None, stability: float | None, last_evidence: float | None, now: float | None = None) -> float:
    """Predicted probability the student still knows it: knowledge decays exponentially with time."""
    if not p_known:
        return 0.0
    days = max(0.0, ((now or time.time()) - (last_evidence or now or time.time())) / 86400)
    return p_known * math.exp(-days / max(stability or 1.0, 0.2))


def _next_due(p_known: float, stability: float, now: float) -> float:
    if p_known <= RETAIN_TARGET + 0.02:
        return now + 86400  # weak: see it again tomorrow
    days = -math.log(RETAIN_TARGET / p_known) * stability
    return now + max(1.0, days) * 86400


def mark_started(student_id: str, subtopic_id: str) -> None:
    db.run(
        """INSERT INTO progress (student_id, subtopic_id, status, last_studied) VALUES (?,?, 'started', ?)
           ON CONFLICT DO UPDATE SET last_studied=excluded.last_studied""",
        (student_id, subtopic_id, time.time()),
    )
    _touch_activity(student_id)


def record_evidence(student_id: str, subtopic_id: str, score: float, source: str, weight: int = 3) -> float:
    """Fold a quiz / practice / teach-back / viva result (score 0..1) into mastery, stability and the revision date."""
    now = time.time()
    row = db.one("SELECT p_known, stability, status FROM progress WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id)) or {}
    p0 = row.get("p_known") or P_INIT
    stability = row.get("stability") or 1.0
    p = bkt_update(p0, score, weight)
    stability = min(365.0, stability * (1.6 + score)) if score >= 0.7 else max(0.5, stability * 0.5)
    db.run(
        """INSERT INTO progress (student_id, subtopic_id, status, mastery, p_known, stability, last_evidence, last_studied)
           VALUES (?,?, 'completed', ?,?,?,?,?)
           ON CONFLICT DO UPDATE SET status='completed', mastery=?, p_known=?, stability=?, last_evidence=?, last_studied=?""",
        (student_id, subtopic_id, p, p, stability, now, now, p, p, stability, now, now),
    )
    db.run(
        """INSERT INTO revision (student_id, subtopic_id, box, due_at) VALUES (?,?,0,?)
           ON CONFLICT DO UPDATE SET due_at=excluded.due_at""",
        (student_id, subtopic_id, _next_due(p, stability, now)),
    )
    _touch_activity(student_id)
    return p


def mark_completed(student_id: str, subtopic_id: str) -> None:
    now = time.time()
    row = db.one("SELECT p_known FROM progress WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id)) or {}
    p = row.get("p_known") or 0.45  # "I understood" without evidence: modest prior
    db.run(
        """INSERT INTO progress (student_id, subtopic_id, status, mastery, p_known, stability, last_evidence, last_studied)
           VALUES (?,?, 'completed', ?,?,1.0,?,?)
           ON CONFLICT DO UPDATE SET status='completed', mastery=COALESCE(progress.p_known, excluded.mastery), p_known=COALESCE(progress.p_known, excluded.p_known),
           last_evidence=COALESCE(progress.last_evidence, excluded.last_evidence), last_studied=excluded.last_studied""",
        (student_id, subtopic_id, p, p, now, now),
    )
    if not db.one("SELECT 1 FROM revision WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id)):
        db.run("INSERT INTO revision (student_id, subtopic_id, box, due_at) VALUES (?,?,0,?)", (student_id, subtopic_id, now + 2 * 86400))
    _touch_activity(student_id)


def set_last_section(student_id: str, subtopic_id: str, index: int) -> None:
    db.run("UPDATE progress SET last_section=? WHERE student_id=? AND subtopic_id=?", (max(0, index), student_id, subtopic_id))


def add_signal(student_id: str, subtopic_id: str, kind: str, note: str) -> None:
    db.run("INSERT INTO signals (student_id, subtopic_id, kind, note, created_at) VALUES (?,?,?,?,?)",
           (student_id, subtopic_id, kind, note[:400], time.time()))


def recent_signals(student_id: str, subtopic_id: str | None = None, limit: int = 8) -> list[dict]:
    if subtopic_id:
        return db.all("SELECT subtopic_id, kind, note FROM signals WHERE student_id=? AND subtopic_id=? ORDER BY id DESC LIMIT ?", (student_id, subtopic_id, limit))
    return db.all("SELECT subtopic_id, kind, note FROM signals WHERE student_id=? ORDER BY id DESC LIMIT ?", (student_id, limit))


def progress_map(student_id: str) -> dict[str, dict]:
    rows = db.all("SELECT subtopic_id, status, mastery, p_known, stability, last_evidence, last_studied, last_section FROM progress WHERE student_id=?", (student_id,))
    now = time.time()
    return {
        r["subtopic_id"]: {
            "status": r["status"], "mastery": round(r["mastery"] or 0, 2), "last": r["last_studied"], "last_section": r["last_section"] or 0,
            "retention": round(retention(r["p_known"], r["stability"], r["last_evidence"], now), 2) if r["p_known"] else None,
        }
        for r in rows
    }


def due_revisions(student_id: str, limit: int = 8) -> list[str]:
    rows = db.all("SELECT subtopic_id FROM revision WHERE student_id=? AND due_at<=? ORDER BY due_at LIMIT ?", (student_id, time.time(), limit))
    return [r["subtopic_id"] for r in rows]


def difficulty_for(student_id: str, subtopic_id: str) -> str:
    """'easier' / 'standard' / 'harder' from what the learner model believes about this student."""
    row = db.one("SELECT p_known FROM progress WHERE student_id=? AND subtopic_id=?", (student_id, subtopic_id))
    p = (row or {}).get("p_known")
    if p is None:
        return "standard"
    return "easier" if p < 0.4 else "harder" if p > 0.8 else "standard"


def streak(student_id: str) -> int:
    days = {r["day"] for r in db.all("SELECT day FROM activity WHERE student_id=?", (student_id,))}
    count, cursor = 0, date.today()
    if cursor.isoformat() not in days:  # a streak survives until the end of the next day
        cursor -= timedelta(days=1)
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def active_days(student_id: str, days: int = 30) -> list[str]:
    since = (date.today() - timedelta(days=days)).isoformat()
    return [r["day"] for r in db.all("SELECT day FROM activity WHERE student_id=? AND day>=? ORDER BY day", (student_id, since))]


def utc_iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts else None


def language_ok(code: str) -> bool:
    return code in config.LANGUAGES
