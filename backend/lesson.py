"""Lessons: streamed section by section, stored as reviewable versions (draft -> approved), with textbook grounding."""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Iterator

from . import config, curriculum, db, factcheck, llm, mock, prompts, rag, server_text
from .logs import get

log = get("lesson")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

HEADER_RE = re.compile(r"^=== SECTION:\s*([\w-]+)\s*\|\s*(.+?)\s*===\s*$", re.M)
END_RE = re.compile(r"^=== END ===\s*$", re.M)


def board_group(board: str | None) -> str:
    return "icse" if (board or "").lower().startswith("icse") else "cbse"


def variant(language: str, level: str, board: str | None = "CBSE") -> str:
    return f"{language}:{level}:{board_group(board)}"


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


# ---- parsing -----------------------------------------------------------------------------------
def _speakable(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"\$+[^$]*\$+", " ", text)
    text = re.sub(r"[*_`#>|-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:900]


def _parse_body(kind: str, title: str, body: str) -> dict:
    """Split a section body into display + speech. Tolerates missing/oddly-cased markers (small local models)."""
    body = re.sub(r"^\s*```(?:markdown|md)?\s*|\s*```\s*$", "", body.strip())
    parts = re.split(r"\[\s*SPEECH\s*\]\s*:?", body, maxsplit=1, flags=re.I)
    display = re.sub(r"^\s*\[\s*DISPLAY\s*\]\s*:?", "", parts[0], flags=re.I).strip()
    speech = parts[1].strip() if len(parts) > 1 else ""
    return {"kind": kind, "title": title, "display": display, "speech": speech or _speakable(display)}


def parse_sections(text: str) -> list[dict]:
    """Parse every complete section in `text`; the last section counts only if followed by another header or END."""
    headers = list(HEADER_RE.finditer(text))
    end = END_RE.search(text)
    sections = []
    for i, h in enumerate(headers):
        if i + 1 < len(headers):
            stop = headers[i + 1].start()
        elif end:
            stop = end.start()
        else:
            continue
        sections.append(_parse_body(h.group(1), h.group(2), text[h.end():stop]))
    return sections


# ---- versions ----------------------------------------------------------------------------------
def _row_to_version(row: dict | None) -> dict | None:
    if not row:
        return None
    payload = json.loads(row["sections"])
    reviewer = db.one("SELECT display_name FROM users WHERE id=?", (row["reviewer_id"],)) if row["reviewer_id"] else None
    return {
        "id": row["id"], "version": row["version"], "status": row["status"], "model": row["model"], "source": row["source"],
        "reviewer": reviewer["display_name"] if reviewer else None, "review_note": row["review_note"], "reviewed_at": row["reviewed_at"],
        "created_at": row["created_at"], "is_active": bool(row["is_active"]), "sections": payload["sections"], "sources": payload.get("sources", []),
        "factcheck": json.loads(row["factcheck"]) if row["factcheck"] else None, "subtopic_id": row["subtopic_id"], "variant": row["variant"],
    }


def active_version(subtopic_id: str, var: str) -> dict | None:
    return _row_to_version(db.one("SELECT * FROM lesson_versions WHERE subtopic_id=? AND variant=? AND is_active=1 ORDER BY id DESC", (subtopic_id, var)))


def get_version(version_id: int) -> dict | None:
    return _row_to_version(db.one("SELECT * FROM lesson_versions WHERE id=?", (version_id,)))


def list_versions(subtopic_id: str, var: str | None = None) -> list[dict]:
    rows = db.all("SELECT * FROM lesson_versions WHERE subtopic_id=?" + (" AND variant=?" if var else "") + " ORDER BY id DESC", (subtopic_id, var) if var else (subtopic_id,))
    return [{k: v for k, v in _row_to_version(r).items() if k != "sections"} for r in rows]


def save_version(subtopic_id: str, var: str, sections: list[dict], sources: list[dict], model: str, source: str = "ai",
                 status: str = "draft", reviewer_id: str | None = None, activate: bool = True) -> int:
    nxt = (db.scalar("SELECT MAX(version) FROM lesson_versions WHERE subtopic_id=? AND variant=?", (subtopic_id, var), 0)) + 1
    if activate:
        db.run("UPDATE lesson_versions SET is_active=0 WHERE subtopic_id=? AND variant=?", (subtopic_id, var))
    return db.run(
        "INSERT INTO lesson_versions (subtopic_id, variant, version, model, source, status, sections, reviewer_id, reviewed_at, is_active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (subtopic_id, var, nxt, model, source, status, json.dumps({"sections": sections, "sources": sources}, ensure_ascii=False), reviewer_id,
         time.time() if reviewer_id else None, int(activate), time.time()))


def review(version_id: int, reviewer_id: str, status: str, note: str = "") -> None:
    """Teacher/admin decision. Approving activates the version; rejecting deactivates it so a new draft can be generated."""
    row = db.one("SELECT subtopic_id, variant FROM lesson_versions WHERE id=?", (version_id,))
    if not row or status not in ("approved", "rejected", "draft"):
        raise ValueError("Unknown version or status")
    db.run("UPDATE lesson_versions SET status=?, reviewer_id=?, review_note=?, reviewed_at=? WHERE id=?", (status, reviewer_id, note[:1000], time.time(), version_id))
    if status == "approved":
        db.run("UPDATE lesson_versions SET is_active=0 WHERE subtopic_id=? AND variant=?", (row["subtopic_id"], row["variant"]))
        db.run("UPDATE lesson_versions SET is_active=1 WHERE id=?", (version_id,))
    elif status == "rejected":
        db.run("UPDATE lesson_versions SET is_active=0 WHERE id=?", (version_id,))


def activate(version_id: int) -> None:
    row = db.one("SELECT subtopic_id, variant FROM lesson_versions WHERE id=?", (version_id,))
    if row:
        db.run("UPDATE lesson_versions SET is_active=0 WHERE subtopic_id=? AND variant=?", (row["subtopic_id"], row["variant"]))
        db.run("UPDATE lesson_versions SET is_active=1 WHERE id=?", (version_id,))


def review_queue(status: str = "draft", limit: int = 100) -> list[dict]:
    rows = db.all("SELECT id, subtopic_id, variant, version, model, status, source, created_at, factcheck FROM lesson_versions WHERE status=? AND is_active=1 AND subtopic_id NOT LIKE 'my-%' ORDER BY created_at DESC LIMIT ?", (status, limit))
    out = []
    for r in rows:
        t = curriculum.get_subtopic(r["subtopic_id"]) or {}
        fc = json.loads(r["factcheck"]) if r["factcheck"] else None
        out.append({**{k: r[k] for k in ("id", "subtopic_id", "variant", "version", "model", "status", "source", "created_at")},
                    "title": t.get("title"), "subject_name": t.get("subject_name"), "grade": t.get("grade"),
                    "issues": len(fc["issues"]) if fc else None, "high_issues": sum(1 for i in fc["issues"] if i["severity"] == "high") if fc else None})
    return out


# ---- generation --------------------------------------------------------------------------------
def _sources_for(topic: dict) -> list[dict]:
    try:
        return rag.retrieve(f"{topic['chapter']} {topic['title']}", topic["subject"], topic["grade"], k=4)
    except Exception:  # noqa: BLE001 - grounding is best effort
        log.exception("textbook retrieval failed")
        return []


def foreign_script(text: str, language: str) -> bool:
    """True when `text` contains letters of a writing system the lesson language does not use (Latin letters are always fine: technical terms)."""
    allowed = set(config.LANGUAGES.get(language, config.LANGUAGES["en"])["scripts"])
    for name, block in config.SCRIPTS.items():
        if name != "latin" and name not in allowed and re.search(f"[{block}]", text):
            return True
    return False


def _per_section_chunks(topic: dict, language: str, level: str, board: str, src_text: str) -> Iterator[str]:
    """Small local models: one focused call per section, stitched into the same text protocol."""
    provider = llm.provider()
    system = prompts.section_system(language, level, topic["subject"], board)
    earlier = ""
    for kind, title, desc in prompts.LESSON_SECTIONS:
        shown = server_text.title(kind, language, title)
        yield f"=== SECTION: {kind} | {shown} ===\n"
        user = prompts.section_user(topic, title, desc, earlier, src_text, language)
        if language == "en":
            body = ""
            for piece in provider.stream_text(system, user, config.EFFORT_LESSON):
                body += piece
                yield piece
        else:  # a model sometimes slips a word in another Indian script into a section: check the whole section before showing it, once more if needed
            body = "".join(provider.stream_text(system, user, config.EFFORT_LESSON))
            if foreign_script(body, language):
                body = "".join(provider.stream_text(system, user + "\nIMPORTANT: use only the script of the lesson language (plus English technical terms in Latin letters). Do not use any other Indian script.", config.EFFORT_LESSON))
            yield body
        if kind == "idea":
            earlier = _parse_body(kind, title, body)["display"][:900]
        yield "\n\n"
        yield "\x00YIELD"  # let queued chat requests run between sections
    yield "=== END ===\n"


def _llm_chunks(topic: dict, language: str, level: str, board: str, src_text: str) -> Iterator[str]:
    if config.MOCK:
        yield from mock.lesson_chunks(topic, language)
    elif llm.provider().per_section:
        yield from _per_section_chunks(topic, language, level, board, src_text)
    else:
        yield from llm.provider().stream_text(prompts.lesson_system(language, level, topic["subject"], board), prompts.lesson_user(topic, src_text), config.EFFORT_LESSON)


def regenerate_section(subtopic_id: str, language: str, level: str, board: str, index: int, guidance: str = "") -> dict:
    """Write section `index` again (a fresh angle). Not stored; callers decide what to do with it."""
    topic = curriculum.get_subtopic(subtopic_id)
    kind, title, desc = prompts.LESSON_SECTIONS[index]
    shown = server_text.title(kind, language, title)
    if config.MOCK:
        return {"kind": kind, "title": shown, "display": f"(rewritten) **{topic['title']}** - {shown}", "speech": f"This is a rewritten demo of {shown}."}
    sources = rag.format_sources(_sources_for(topic))
    user = prompts.section_user(topic, title, desc + (f" Extra guidance from the reader: {guidance}" if guidance else " Take a clearly different approach and a new analogy than the usual one."), "", sources, language)
    body = "".join(llm.provider().stream_text(prompts.section_system(language, level, topic["subject"], board), user, config.EFFORT_LESSON))
    return _parse_body(kind, shown, body)


def load_for_student(subtopic_id: str, language: str, level: str, board: str) -> dict | None:
    return active_version(subtopic_id, variant(language, level, board))


def lesson_text_for_tutor(subtopic_id: str, language: str, level: str, board: str = "CBSE") -> str | None:
    """Compact lesson text handed to the tutor as reference (display text only)."""
    v = active_version(subtopic_id, variant(language, level, board)) or active_version(subtopic_id, variant("en", level, board))
    if not v:
        return None
    return "\n\n".join(f"## {s['title']}\n{s['display']}" for s in v["sections"])


def _flagged(v: dict) -> bool:
    """True when the automatic fact-check found a high-severity problem and no human has approved the lesson yet."""
    return bool(v["status"] != "approved" and v.get("factcheck") and any(i["severity"] == "high" for i in v["factcheck"]["issues"]))


def _meta(v: dict) -> dict:
    return {k: v[k] for k in ("id", "version", "status", "model", "source", "reviewer", "review_note", "reviewed_at", "created_at")}


def version_event(v: dict) -> dict:
    """The event that tells a page which version of a lesson it is showing (and whether an automatic check flagged it)."""
    return {"type": "version", "version": _meta(v), "sources": v["sources"], "flagged": _flagged(v)}


def stream_lesson(subtopic_id: str, language: str, level: str, board: str = "CBSE", force: bool = False, since_section: int = 0) -> Iterator[dict]:
    topic = curriculum.get_subtopic(subtopic_id)
    if topic is None:
        yield {"type": "error", "message": "Unknown topic."}
        return
    var = variant(language, level, board)
    yield {"type": "meta", "topic": topic}

    def replay(v: dict) -> Iterator[dict]:
        yield version_event(v)
        for s in v["sections"]:
            yield {"type": "section", **s}
        yield {"type": "done", "cached": True}

    cached = None if force else active_version(subtopic_id, var)
    if cached:
        yield from replay(cached)
        return

    key = f"{subtopic_id}__{var}"
    lock = _lock_for(key)
    if not lock.acquire(blocking=False):
        yield {"type": "status", "message": "Another student is already opening this lesson - waiting for it..."}
        lock.acquire()
        try:
            cached = active_version(subtopic_id, var)
        finally:
            lock.release()
        if cached:
            yield from replay(cached)
            return
        lock.acquire()  # the other attempt failed; generate it ourselves

    try:
        passages = _sources_for(topic)
        buffer, emitted, announced = "", 0, 0
        for chunk in _llm_chunks(topic, language, level, board, rag.format_sources(passages)):
            if chunk == "\x00YIELD":
                yield {"type": "_yield_slot"}
                continue
            buffer += chunk
            headers = list(HEADER_RE.finditer(buffer))
            while announced < len(headers):
                h = headers[announced]
                yield {"type": "section_start", "index": announced, "kind": h.group(1), "title": h.group(2)}
                announced += 1
            sections = parse_sections(buffer)
            while emitted < len(sections):
                yield {"type": "section", **sections[emitted]}
                emitted += 1
        sections = parse_sections(buffer)
        if len(sections) < 3:
            yield {"type": "error", "message": "The lesson could not be generated. Please try again."}
            return
        sources = [{"n": i, "title": p["title"], "page": p["page"]} for i, p in enumerate(passages, start=1)]
        vid = save_version(subtopic_id, var, sections, sources, config.model() if not config.MOCK else "mock")
        if not config.MOCK:
            factcheck.run_async(vid)
        v = get_version(vid)
        yield {"type": "version", "version": _meta(v), "sources": sources, "flagged": False}
        yield {"type": "done", "cached": False}
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        log.exception("lesson generation failed")
        yield {"type": "error", "message": llm.friendly_error(exc)}
    finally:
        lock.release()
