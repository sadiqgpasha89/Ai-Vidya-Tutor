"""Cached add-ons for a topic: objectives, cheat-sheet, diagram, exam-focus briefing and flashcards."""
from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager

from . import config, curriculum, db, diagrams, learning, lesson, llm, mock, moderation, prompts, svgsafe
from .logs import get

log = get("extras")


_makers: dict[str, threading.Lock] = {}
_makers_guard = threading.Lock()


@contextmanager
def _once(subtopic_id: str, var: str, kind: str):
    """Only one request makes a given item at a time: a second one (say the page asking while the warm-up is drawing it) waits and then finds it kept."""
    key = f"{subtopic_id}|{var}|{kind}"
    with _makers_guard:
        lock = _makers.setdefault(key, threading.Lock())
    with lock:
        try:
            yield
        finally:
            with _makers_guard:
                _makers.pop(key, None)


def _get(subtopic_id: str, var: str, kind: str) -> str | None:
    row = db.one("SELECT body FROM extras WHERE subtopic_id=? AND variant=? AND kind=?", (subtopic_id, var, kind))
    return row["body"] if row else None


def _put(subtopic_id: str, var: str, kind: str, body: str) -> None:
    db.run("INSERT OR REPLACE INTO extras (subtopic_id, variant, kind, body, model, created_at) VALUES (?,?,?,?,?,?)",
           (subtopic_id, var, kind, body, config.model(), time.time()))


def _script_note(language: str) -> str:
    name = config.LANGUAGES[language]["name"]
    return f"\nIMPORTANT: write ALL of it in {name} only" + (" (plus English technical terms in Latin letters)." if "latin" not in config.LANGUAGES[language]["scripts"] else ", using Latin letters only; no Indian-script or other non-Latin text.")


def _text(system: str, user: str, language: str, effort: str, role: str) -> str:
    """Model text in the student's language; written again once if it comes back in the wrong script (a model slip)."""
    out = "".join(llm.provider().stream_text(system, user, effort, role=role)).strip()
    if lesson.foreign_script(out, language):
        out = "".join(llm.provider().stream_text(system, user + _script_note(language), effort, role=role)).strip()
    return out


def _structured(system: str, user: str, schema: dict, language: str, effort: str, max_tokens: int, role: str) -> dict:
    data = llm.provider().structured(system, user, schema, effort, max_tokens=max_tokens, role=role)
    if lesson.foreign_script(json.dumps(data, ensure_ascii=False), language):
        data = llm.provider().structured(system, user + _script_note(language), schema, effort, max_tokens=max_tokens, role=role)
    return data


def _topic(subtopic_id: str) -> dict:
    t = curriculum.get_subtopic(subtopic_id)
    if t is None:
        raise ValueError("Unknown topic")
    return t


def _brief(t: dict) -> str:
    return f"Subject: {t['subject_name']}, Grade {t['grade']}, Chapter: {t['chapter']}, Subtopic: {t['title']}"


def _lesson_ref(subtopic_id: str, language: str, level: str, board: str) -> str:
    ref = lesson.lesson_text_for_tutor(subtopic_id, language, level, board)
    return f"\n\nThe lesson the student has seen (stay consistent with it):\n{ref[:6000]}" if ref else ""


def objectives(subtopic_id: str, language: str, cached_only: bool = False) -> dict | None:
    var = f"{language}"
    hit = _get(subtopic_id, var, "objectives")
    if hit:
        return json.loads(hit)
    if cached_only:
        return None
    t = _topic(subtopic_id)
    if config.MOCK:
        data = mock.objectives(t)
    else:
        data = _structured(prompts.OBJECTIVES_SYSTEM, f"{_brief(t)}\nLanguage: {config.LANGUAGES[language]['name']}", prompts.OBJECTIVES_SCHEMA, language, "low", 700, "summary")
    _put(subtopic_id, var, "objectives", json.dumps(data, ensure_ascii=False))
    return data


def cheatsheet(subtopic_id: str, language: str, level: str, board: str) -> str:
    var = lesson.variant(language, level, board)
    hit = _get(subtopic_id, var, "cheatsheet")
    if hit:
        return hit
    with _once(subtopic_id, var, "cheatsheet"):
        hit = _get(subtopic_id, var, "cheatsheet")
        if hit:
            return hit
        t = _topic(subtopic_id)
        if config.MOCK:
            body = mock.cheatsheet(t)
        else:
            user = f"{_brief(t)}\nLevel: {config.LEVELS[level]}\nLanguage: {config.LANGUAGES[language]['name']}{_lesson_ref(subtopic_id, language, level, board)}"
            body = _text(prompts.CHEATSHEET_SYSTEM, user, language, "low", "cheatsheet")
        _put(subtopic_id, var, "cheatsheet", body)
        return body


def diagram(subtopic_id: str, language: str, level: str, board: str, what: str = "") -> str | None:
    var = lesson.variant(language, level, board)
    kind = "diagram:" + (what.strip().lower()[:60] if what else "main")
    hit = _get(subtopic_id, var, kind)
    if hit:
        return hit
    t = _topic(subtopic_id)
    if config.MOCK:
        raw = mock.diagram(t)
    else:
        user = f"{_brief(t)}\nDraw: {what or 'the single most useful diagram for understanding this subtopic'}\nLabels in: {config.LANGUAGES[language]['name']} (keep them short)."
        raw = "".join(llm.provider().stream_text(prompts.FIGURE_SYSTEM, user, "medium", role="figure"))
    svg = svgsafe.sanitize(_unlatex(raw))
    if svg:
        _put(subtopic_id, var, kind, svg)
    return svg


def exam_focus(subtopic_id: str, goal: str, level: str, language: str = "en") -> str:
    if goal not in config.GOALS:
        goal = "boards"
    var = f"{language}:{goal}"
    hit = _get(subtopic_id, var, "examfocus")
    if hit:
        return hit
    t = _topic(subtopic_id)
    if config.MOCK:
        body = f"**{config.GOALS[goal]} focus** for {t['title']} (demo)."
    else:
        user = f"{_brief(t)}\nExam goal: {config.GOALS[goal]}\nLanguage: {config.LANGUAGES[language]['name']}"
        body = _text(prompts.EXAMFOCUS_SYSTEM, user, language, "low", "summary")
    _put(subtopic_id, var, "examfocus", body)
    return body


_unlatex = diagrams.unlatex  # kept under its old name


def _worth_showing(svg: str | None) -> bool:
    """A drawing with almost nothing in it (or no words) teaches nothing: do not show it."""
    if not svg:
        return False
    shapes = len(re.findall(r"<(?:rect|circle|ellipse|line|polyline|polygon|path)\b", svg))
    labels = len(re.findall(r"<text\b", svg))
    return shapes >= 6 and labels >= 4


def concept_diagram(t: dict, title: str, display: str, kind: str, language: str) -> dict | None:
    """A concept diagram (flow / cycle / compare / map) laid out by code from a short description the everyday model writes. If the model's
    description is unusable twice, a plain diagram is built from the text itself, so a section that has anything to say always gets a picture."""
    svg = None
    if config.MOCK:
        svg = diagrams.render({"layout": "flow", "title": title[:60], "items": [{"label": f"Step {i + 1}", "note": t["title"][:40]} for i in range(3)]}, language)
    else:
        user = (f"{_brief(t)}\nSection \"{title}\" of the lesson:\n{display[:2500]}\n\n{prompts.CONCEPT_KINDS.get(kind, prompts.CONCEPT_KINDS['quick'])}\n"
                f"Language for all text: {config.LANGUAGES[language]['name']}.")
        for attempt in range(2):
            try:
                spec = _structured(prompts.CONCEPT_SYSTEM, user + ("\nGive at least 3 items (or 2 columns with 2 points each)." if attempt else ""), prompts.CONCEPT_SCHEMA, language, "low", 1200, "lesson")
            except Exception as exc:  # noqa: BLE001 - try again, then fall back
                log.warning(f"diagram description failed ({exc})")
                continue
            svg = diagrams.render(spec, language)
            if svg:
                break
    if not svg:
        fb = diagrams.fallback_spec(title, display, kind)
        svg = diagrams.render(fb, language) if fb else None
        if svg:
            log.info(f"plain diagram used for '{title}'")
    return {"svg": svg, "caption": title, "style": "diagram"} if svg else None


def figure(subtopic_id: str, language: str, level: str, board: str, section: int, mode: str = "full") -> dict | None:
    """A concept diagram for one part of a lesson, made once and kept. mode "full": a section of the full lesson; "quick": a part of the 5-minute summary.
    -> {"svg", "caption", "style"}, or None when that part has no picture."""
    var = lesson.variant(language, level, board)
    v = lesson.active_version(subtopic_id, var)
    if not v:
        raise ValueError("Open the lesson first, then its pictures can be drawn.")
    if mode == "quick":
        parts = json.loads(_get(subtopic_id, var, f"quick:v{v['id']}") or "[]")
        if not 0 <= section < len(parts):
            raise ValueError("Open the 5-minute summary first.")
        title, display, kind, key = parts[section]["title"], parts[section]["display"], "quick", f"pic:v{v['id']}:q{section}"
    else:
        if not 0 <= section < len(v["sections"]):
            raise ValueError("Open the lesson first, then its pictures can be drawn.")
        sec = v["sections"][section]
        if sec["kind"] not in prompts.CONCEPT_KINDS:
            return None
        title, display, kind, key = sec["title"], sec["display"], sec["kind"], f"pic:v{v['id']}:{section}"
    with _once(subtopic_id, var, key):
        hit = _get(subtopic_id, var, key)
        if hit:
            return json.loads(hit) if hit != "none" else None
        try:
            out = concept_diagram(_topic(subtopic_id), title, display, kind, language)
        except Exception as exc:  # noqa: BLE001 - a picture is a bonus: never fail the lesson over it
            log.warning(f"diagram for {subtopic_id} section {section} failed: {exc}")
            return {"error": True}  # not kept, so the page can offer "try again"
        if out:
            _put(subtopic_id, var, key, json.dumps(out, ensure_ascii=False))
        return out


def cached_figures(subtopic_id: str, language: str, level: str, board: str, mode: str = "full") -> dict[str, dict]:
    """Every picture already made for this lesson, in one read (never calls the model). -> {"<part number>": figure}"""
    var = lesson.variant(language, level, board)
    v = lesson.active_version(subtopic_id, var)
    if not v:
        return {}
    prefix = f"pic:v{v['id']}:"
    out = {}
    for r in db.all("SELECT kind, body FROM extras WHERE subtopic_id=? AND variant=? AND kind LIKE ?", (subtopic_id, var, prefix + "%")):
        tail = r["kind"][len(prefix):]
        if r["body"] != "none" and tail.startswith("q") == (mode == "quick") and tail.lstrip("q").isdigit():
            out[tail.lstrip("q")] = json.loads(r["body"])
    return out


def did_you_know(subtopic_id: str, language: str, level: str, board: str, cached_only: bool = False) -> list[dict] | None:
    """Three "Did you know?" facts to spark curiosity about the topic, made once per lesson and kept. cached_only: never call the model (None if not made yet)."""
    var = lesson.variant(language, level, board)
    v = lesson.active_version(subtopic_id, var)
    if not v:
        if cached_only:
            return None
        raise ValueError("Open the lesson first - the facts are chosen to go with it.")
    kind = f"dyk:v{v['id']}"
    hit = _get(subtopic_id, var, kind)
    if hit or cached_only:
        return json.loads(hit) if hit else None
    with _once(subtopic_id, var, kind):
        return _make_dyk(subtopic_id, language, level, board, var, kind)


def _make_dyk(subtopic_id: str, language: str, level: str, board: str, var: str, kind: str) -> list[dict]:
    hit = _get(subtopic_id, var, kind)
    if hit:
        return json.loads(hit)
    t = _topic(subtopic_id)
    if config.MOCK:
        facts = mock.did_you_know(t)
    else:
        user = f"{_brief(t)}\nLevel: {config.LEVELS[level]}\nLanguage: {config.LANGUAGES[language]['name']}\n\nTHE LESSON THE STUDENT JUST READ:\n{_lesson_ref(subtopic_id, language, level, board)[:5000]}"
        data = _structured(prompts.DYK_SYSTEM, user, prompts.DYK_SCHEMA, language, "medium", 1500, "summary")
        facts = [{"emoji": str(f.get("emoji") or "💡").strip()[:4] or "💡", "teaser": " ".join(str(f["teaser"]).split())[:140], "fact": " ".join(str(f["fact"]).split())[:420]}
                 for f in data.get("facts", []) if f.get("teaser") and f.get("fact")]
        facts = [f for f in facts if not moderation.check_output(f["teaser"] + " " + f["fact"])]
    if len(facts) < 2:
        raise RuntimeError("Could not think of facts right now. Please try again.")
    _put(subtopic_id, var, kind, json.dumps(facts, ensure_ascii=False))
    return facts


def quick_summary(subtopic_id: str, language: str, level: str, board: str) -> list[dict]:
    """The lesson boiled down to about five minutes: a handful of short parts, each with reading text and spoken text."""
    var = lesson.variant(language, level, board)
    v = lesson.active_version(subtopic_id, var)
    if not v:
        raise ValueError("The summary is made from the full lesson - open the full lesson first.")
    kind = f"quick:v{v['id']}"
    hit = _get(subtopic_id, var, kind)
    if hit:
        return json.loads(hit)
    with _once(subtopic_id, var, kind):
        return _make_quick(subtopic_id, language, level, v, var, kind)


def _make_quick(subtopic_id: str, language: str, level: str, v: dict, var: str, kind: str) -> list[dict]:
    hit = _get(subtopic_id, var, kind)
    if hit:
        return json.loads(hit)
    t = _topic(subtopic_id)
    if config.MOCK:
        parts = [{"title": s["title"], "display": s["display"][:400], "speech": s["speech"][:500]} for s in v["sections"][:5]]
    else:
        full = "\n\n".join(f"## {s['title']}\n{s['display']}" for s in v["sections"])[:9000]
        user = f"{_brief(t)}\nLevel: {config.LEVELS[level]}\nLanguage: {config.LANGUAGES[language]['name']}\n\nFULL LESSON:\n{full}"
        data = _structured(prompts.QUICK_SYSTEM, user, prompts.QUICK_SCHEMA, language, "medium", 3500, "summary")
        parts = [{"title": str(p["title"])[:80], "display": str(p["display"]), "speech": str(p["speech"])} for p in data.get("sections", []) if p.get("display") and p.get("speech")]
    if len(parts) < 3:
        raise RuntimeError("Could not write the summary right now. Please try again.")
    _put(subtopic_id, var, kind, json.dumps(parts, ensure_ascii=False))
    return parts


def flashcards(subtopic_id: str, language: str, level: str = "standard", board: str = "CBSE", n: int = 8) -> list[dict]:
    have = learning.cards_for(subtopic_id, language)
    if have:
        return have
    t = _topic(subtopic_id)
    if config.MOCK:
        cards = mock.flashcards(t)
    else:
        user = f"{_brief(t)}\nLevel: {config.LEVELS[level]}\nLanguage: {config.LANGUAGES[language]['name']}\nNumber of cards: {n}{_lesson_ref(subtopic_id, language, level, board)}"
        cards = _structured(prompts.FLASHCARDS_SYSTEM, user, prompts.FLASHCARDS_SCHEMA, language, "low", 2500, "quiz").get("cards", [])
    cards = [c for c in cards if c.get("front") and c.get("back")][:12]
    if not cards:
        raise RuntimeError("Could not create flashcards right now.")
    learning.store_cards(subtopic_id, language, cards)
    return learning.cards_for(subtopic_id, language)
