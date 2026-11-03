"""Prepared study notes: a lesson boiled down to short bullet points with a small diagram per part. Kept per student in SQLite; downloadable."""
from __future__ import annotations

import base64
import html
import json
import re
import time

from . import config, curriculum, db, diagrams, extras, lesson, prompts


def _var(student: dict) -> str:
    return lesson.variant(student["language"], student["level"], student["board"])


def get(student: dict, subtopic_id: str) -> dict | None:
    row = db.one("SELECT * FROM study_notes WHERE student_id=? AND subtopic_id=? AND variant=?", (student["id"], subtopic_id, _var(student)))
    if not row:
        return None
    return {**json.loads(row["body"]), "title": row["title"], "subtopic_id": subtopic_id, "created_at": row["created_at"], "updated_at": row["updated_at"], "model": row["model"]}


def list_for(student_id: str) -> list[dict]:
    """Every set of notes the student has prepared (newest first), without the diagrams."""
    out = []
    for r in db.all("SELECT subtopic_id, variant, title, body, updated_at FROM study_notes WHERE student_id=? ORDER BY updated_at DESC", (student_id,)):
        topic = curriculum.get_subtopic(r["subtopic_id"], student_id)
        if topic:
            out.append({"subtopic_id": r["subtopic_id"], "title": r["title"], "topic": topic["title"], "subject_name": topic["subject_name"], "grade": topic["grade"],
                        "updated_at": r["updated_at"], "parts": len(json.loads(r["body"])["sections"])})
    return out


def delete(student: dict, subtopic_id: str) -> None:
    db.run("DELETE FROM study_notes WHERE student_id=? AND subtopic_id=? AND variant=?", (student["id"], subtopic_id, _var(student)))


def _clean_bullets(items) -> list[str]:
    out = []
    for b in items or []:
        b = re.sub(r"^(?:[-•·]|\*(?!\*))\s+", "", " ".join(str(b or "").split()))
        if b.count("**") % 2:  # a bold marker the model opened but never closed (or the reverse) would show as stray asterisks
            b = b.replace("**", "")
        if b.count("$") % 2:
            b = b.replace("$", "")
        if b:
            out.append(b[:220])
    return out[:6]


def prepare(student: dict, subtopic_id: str, topic: dict) -> dict:
    """Write (or rewrite) the notes from the lesson the student has open. Needs the full lesson to exist."""
    language = student["language"]
    var = _var(student)
    v = lesson.active_version(subtopic_id, var)
    if not v:
        raise ValueError("Open the full lesson first - the notes are made from it.")
    secs = v["sections"]
    if config.MOCK:
        data = {"title": topic["title"], "summary": f"Short notes on {topic['title']}.", "remember": [secs[-1]["title"]],
                "sections": [{"heading": s["title"], "bullets": [ln.strip("-*# ") for ln in s["display"].splitlines() if ln.strip()][:3] or [s["title"]]} for s in secs[:5]]}
    else:
        text = "\n\n".join(f"## {s['title']}\n{s['display']}" for s in secs)[:12000]
        user = (f"{extras._brief(topic)}\nLevel: {config.LEVELS[student['level']]}\nLanguage: {config.LANGUAGES[language]['name']}\n\nFULL LESSON:\n{text}")
        data = extras._structured(prompts.NOTES_SYSTEM, user, prompts.NOTES_SCHEMA, language, "medium", 4500, "summary")
    sections = []
    for s in data.get("sections", []):
        bullets = _clean_bullets(s.get("bullets"))
        heading = diagrams.plain(s.get("heading"))[:80]
        if not heading or len(bullets) < 1:
            continue
        svg = diagrams.render(s.get("diagram") or {}, language)
        if not svg:  # the model's description was unusable: draw one from the bullets themselves
            fb = diagrams.fallback_spec(heading, "\n".join(f"- {b}" for b in bullets), "idea")
            svg = diagrams.render(fb, language) if fb else None
        sections.append({"heading": heading, "bullets": bullets, "svg": svg})
    if len(sections) < 3:
        raise RuntimeError("Could not write the notes right now. Please try again.")
    summary = (_clean_bullets([str(data.get("summary") or "")[:300]]) or [""])[0]
    note = {"title": diagrams.plain(data.get("title") or topic["title"])[:120], "summary": summary,
            "remember": _clean_bullets(data.get("remember"))[:4], "sections": sections, "language": language, "topic": topic["title"],
            "subject_name": topic["subject_name"], "grade": topic["grade"],
            "curious": [{"teaser": f["teaser"], "fact": f["fact"]} for f in (extras.did_you_know(subtopic_id, language, student["level"], student["board"], cached_only=True) or [])]}
    now = time.time()
    first = db.one("SELECT created_at FROM study_notes WHERE student_id=? AND subtopic_id=? AND variant=?", (student["id"], subtopic_id, var))
    db.run("INSERT OR REPLACE INTO study_notes (student_id, subtopic_id, variant, version_id, title, body, model, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
           (student["id"], subtopic_id, var, v["id"], note["title"], json.dumps(note, ensure_ascii=False), config.role_model("summary"), first["created_at"] if first else now, now))
    return get(student, subtopic_id)


# ---- download formats ---------------------------------------------------------------------------------------------------
def _inline(text: str) -> str:
    """Bullet text for a standalone page: escape it, keep **bold**, and write $maths$ out as plain symbols (the page has no maths renderer)."""
    safe = html.escape(text)
    safe = re.sub(r"\$([^$]{1,120})\$", lambda m: f"<i>{html.escape(diagrams.plain(html.unescape(m.group(1))))}</i>", safe)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)


_CSS = """body{font:16px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,'Noto Sans',sans-serif;color:#1f2937;max-width:780px;margin:24px auto;padding:0 16px}
h1{font-size:1.7rem;margin:.2em 0}h2{font-size:1.2rem;margin:1.4em 0 .4em;border-bottom:2px solid #dbeafe;padding-bottom:.2em}.meta{color:#4b5563;font-size:.9rem}
.summary{background:#eef2ff;border-radius:10px;padding:10px 14px}.remember{background:#fef3c7;border-radius:10px;padding:8px 14px}li{margin:.25em 0}
figure{margin:.6em 0;text-align:center;break-inside:avoid}figure svg{max-width:100%;height:auto;max-height:520px}section{break-inside:avoid-page}
footer{margin-top:2em;color:#6b7280;font-size:.8rem}@media print{body{margin:0;max-width:none}}"""


def to_html(note: dict) -> str:
    parts = []
    for s in note["sections"]:
        fig = f"<figure>{s['svg']}</figure>" if s.get("svg") else ""
        parts.append(f"<section><h2>{html.escape(s['heading'])}</h2><ul>{''.join(f'<li>{_inline(b)}</li>' for b in s['bullets'])}</ul>{fig}</section>")
    remember = f"<div class=\"remember\"><b>Remember</b><ul>{''.join(f'<li>{_inline(b)}</li>' for b in note['remember'])}</ul></div>" if note.get("remember") else ""
    summary = f"<p class=\"summary\">{_inline(note['summary'])}</p>" if note.get("summary") else ""
    curious = ("<div class=\"remember\"><b>Did you know?</b><ul>" + "".join(f"<li><b>{html.escape(c['teaser'])}</b> {html.escape(c['fact'])}</li>" for c in note["curious"]) + "</ul></div>") if note.get("curious") else ""
    return (f"<!doctype html><html lang=\"{html.escape(note.get('language', 'en'))}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(note['title'])}</title><style>{_CSS}</style></head><body><p class=\"meta\">{html.escape(note.get('subject_name', ''))} · Grade {note.get('grade', '')}</p>"
            f"<h1>{html.escape(note['title'])}</h1>{summary}{''.join(parts)}{remember}{curious}"
            f"<footer>Study notes prepared by AIVidya (AI). Check them against your textbook.</footer></body></html>")


def to_markdown(note: dict) -> str:
    out = [f"# {note['title']}", f"*{note.get('subject_name', '')} · Grade {note.get('grade', '')}*", ""]
    if note.get("summary"):
        out += [f"> {note['summary']}", ""]
    for s in note["sections"]:
        out += [f"## {s['heading']}", ""] + [f"- {b}" for b in s["bullets"]] + [""]
        if s.get("svg"):
            out += [f"![{s['heading']}](data:image/svg+xml;base64,{base64.b64encode(s['svg'].encode()).decode()})", ""]
    if note.get("remember"):
        out += ["## Remember", ""] + [f"- {b}" for b in note["remember"]] + [""]
    if note.get("curious"):
        out += ["## Did you know?", ""] + [f"- **{c['teaser']}** {c['fact']}" for c in note["curious"]] + [""]
    out += ["---", "Study notes prepared by AIVidya (AI). Check them against your textbook.", ""]
    return "\n".join(out)
