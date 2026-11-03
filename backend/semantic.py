"""Semantic topic search: embeds every subtopic once, then ranks by meaning with a keyword boost."""
from __future__ import annotations

import threading

import numpy as np

from . import config, curriculum, db, embeddings
from .logs import get

log = get("semantic")
_lock = threading.Lock()
_cache: dict = {"ids": [], "mat": None, "count": -1}


def _text(t: dict) -> str:
    return f"{t['subject_name']} class {t['grade']}: {t['chapter']} - {t['title']}"


def build_index() -> int:
    """Embed any subtopics that have no vector yet. Returns how many were added."""
    if not embeddings.available():
        return 0
    have = {r["subtopic_id"] for r in db.all("SELECT subtopic_id FROM topic_embeddings WHERE model=?", (config.EMBED_MODEL,))}
    todo = [t for t in curriculum.all_subtopics() if t["id"] not in have]
    for i in range(0, len(todo), 64):
        batch = todo[i:i + 64]
        meta = [curriculum.get_subtopic(t["id"]) for t in batch]
        vecs = embeddings.embed([_text(m) for m in meta if m])
        if vecs is None:
            break
        with db.connect() as conn:
            for t, v in zip(batch, vecs):
                conn.execute("INSERT OR REPLACE INTO topic_embeddings VALUES (?,?,?)", (t["id"], config.EMBED_MODEL, embeddings.to_blob(v)))
    with _lock:
        _cache["count"] = -1
    if todo:
        log.info(f"semantic index: embedded {len(todo)} topics")
    return len(todo)


def build_async() -> None:
    threading.Thread(target=build_index, daemon=True, name="semantic-index").start()


def _matrix():
    with _lock:
        n = db.scalar("SELECT COUNT(*) FROM topic_embeddings WHERE model=?", (config.EMBED_MODEL,), 0)
        if _cache["count"] != n:
            rows = db.all("SELECT subtopic_id, vec FROM topic_embeddings WHERE model=?", (config.EMBED_MODEL,))
            _cache["ids"] = [r["subtopic_id"] for r in rows]
            _cache["mat"] = np.stack([embeddings.from_blob(r["vec"]) for r in rows]) if rows else None
            _cache["count"] = n
        return _cache["ids"], _cache["mat"]


def search(query: str, grade: int | None = None, limit: int = 12, subjects: list[str] | None = None) -> dict:
    """-> {"mode": "semantic"|"keyword", "results": [...]}"""
    keyword = {r["id"]: r for r in curriculum.search(query, limit=40)}
    ids, mat = _matrix()
    qv = embeddings.embed([query]) if mat is not None else None
    if qv is None:
        res = [r for r in keyword.values() if not subjects or r["subject"] in subjects]
        res.sort(key=lambda r: abs(r["grade"] - grade) if grade else 0)  # stable: keyword order kept within a grade distance
        return {"mode": "keyword", "results": res[:limit]}
    sims = mat @ qv[0]
    order = np.argsort(-sims)[:80]
    scored = []
    for i in order:
        t = curriculum.get_subtopic(ids[i])
        if not t or (subjects and t["subject"] not in subjects):
            continue
        # other grades stay searchable (a Grade 9 student may ask about Grade 10 ideas), but the student's own grade wins ties
        boost = (0.15 if ids[i] in keyword else 0.0) + (0.05 if grade and t["grade"] == grade else -0.01 * min(3, abs(t["grade"] - grade)) if grade else 0.0)
        scored.append((float(sims[i]) + boost, t))
    scored.sort(key=lambda x: -x[0])
    return {"mode": "semantic", "results": [{k: t[k] for k in ("id", "title", "chapter", "subject", "subject_name", "grade")} for s, t in scored[:limit] if s > 0.35]}
