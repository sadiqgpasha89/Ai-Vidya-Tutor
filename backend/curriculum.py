"""Curriculum: base text files + per-board overlays + admin edits. Source of truth: backend/curriculum_data/."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import config

DATA = Path(__file__).parent / "curriculum_data"
EDITS_FILE = config.DATA_DIR / "curriculum_edits.json"
_lock = threading.RLock()

SUBJECTS = {
    "physics": {"name": "Physics", "icon": "⚛️", "color": "#4f7cff", "tagline": "How the universe moves", "grades": [7, 8, 9, 10, 11, 12]},
    "chemistry": {"name": "Chemistry", "icon": "🧪", "color": "#14b8a6", "tagline": "What everything is made of", "grades": [7, 8, 9, 10, 11, 12]},
    "biology": {"name": "Biology", "icon": "🧬", "color": "#22c55e", "tagline": "The science of life", "grades": [7, 8, 9, 10, 11, 12]},
    "maths": {"name": "Maths", "icon": "📐", "color": "#f59e0b", "tagline": "The language of patterns", "grades": [7, 8, 9, 10, 11, 12]},
    "computers": {"name": "Computers", "icon": "💻", "color": "#a855f7", "tagline": "Think, build, code", "grades": [7, 8, 9, 10, 11, 12]},
    "english": {"name": "English", "icon": "📖", "color": "#ec4899", "tagline": "Read, write, speak well", "grades": [7, 8, 9, 10, 11, 12]},
    "social": {"name": "Social Science", "icon": "🌏", "color": "#0ea5e9", "tagline": "History, geography, civics, economics", "grades": [7, 8, 9, 10, 11, 12]},
    "commerce": {"name": "Commerce", "icon": "📊", "color": "#84cc16", "tagline": "Accounts, business, economics", "grades": [11, 12]},
}
# Subjects recommended for Grades 11-12 by stream; everything else stays reachable under "All subjects".
STREAM_SUBJECTS = {
    "pcm": ["physics", "chemistry", "maths", "computers", "english"],
    "pcb": ["physics", "chemistry", "biology", "english"],
    "pcmb": ["physics", "chemistry", "maths", "biology", "english"],
    "commerce": ["commerce", "maths", "english", "computers"],
    "humanities": ["social", "english", "maths"],
}


@dataclass
class Subtopic:
    id: str
    title: str
    chapter_id: str


@dataclass
class Chapter:
    id: str
    subject: str
    grade: int
    title: str
    track: str = ""     # "" = all students, otherwise "CS" / "IP"
    board: str = ""     # "" = all boards, otherwise "icse"
    number: int = 0
    hidden: bool = False
    level: str = ""     # "" = every level, "challenge" = extension chapters shown only to students who chose Challenge
    subtopics: list[Subtopic] = field(default_factory=list)
    removed: list[tuple[int, Subtopic]] = field(default_factory=list)  # subtopics an administrator hid: (original position, subtopic)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _parse_subs(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(";") if s.strip()]


def _load_edits() -> list[dict]:
    try:
        return json.loads(EDITS_FILE.read_text()).get("ops", [])
    except (OSError, ValueError):
        return []


_cache: tuple[list[Chapter], dict[str, tuple[Chapter, Subtopic]], dict[str, list[str]]] | None = None


def _build():
    chapters: list[Chapter] = []
    for subject in SUBJECTS:
        path = DATA / f"{subject}.txt"
        if not path.exists():
            continue
        grade, track = 0, ""
        seen: dict[str, int] = {}
        numbers: dict[int, int] = {}
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@grade"):
                grade, track = int(line.split()[1]), ""
                continue
            if line.startswith("@track"):
                track = line.split()[1].upper()
                continue
            title, _, subs = line.partition("|")
            title = title.strip()
            base = f"{subject[:3]}-{grade}-{_slug(title)}"
            seen[base] = seen.get(base, 0) + 1
            cid = base if seen[base] == 1 else f"{base}-{seen[base]}"
            numbers[grade] = numbers.get(grade, 0) + 1
            ch = Chapter(cid, subject, grade, title, track=track, number=numbers[grade])
            ch.subtopics = [Subtopic(f"{cid}.{n}", s, cid) for n, s in enumerate(_parse_subs(subs), start=1)]
            chapters.append(ch)
    # board overlays (e.g. boards/icse.txt)
    for path in sorted((DATA / "boards").glob("*.txt")):
        board, subject, grade = path.stem.lower(), "", 0
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@subject"):
                subject = line.split()[1]
            elif line.startswith("@grade"):
                grade = int(line.split()[1])
            elif line.startswith("+"):
                title, _, subs = line[1:].partition("|")
                cid = f"{subject[:3]}-{grade}-{board}-{_slug(title.strip())}"
                ch = Chapter(cid, subject, grade, title.strip(), board=board)
                ch.subtopics = [Subtopic(f"{cid}.{n}", s, cid) for n, s in enumerate(_parse_subs(subs), start=1)]
                chapters.append(ch)
            elif line.startswith("-"):
                for ch in chapters:
                    if ch.subject == subject and ch.grade == grade and ch.title.lower() == line[1:].strip().lower():
                        ch.board = f"not-{board}"
    # level overlays (levels/challenge.txt): extension chapters beyond the board syllabus, same format as the board overlays
    for path in sorted((DATA / "levels").glob("*.txt")):
        level, subject, grade = path.stem.lower().split("-")[0], "", 0
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@subject"):
                subject = line.split()[1]
            elif line.startswith("@grade"):
                grade = int(line.split()[1])
            elif line.startswith("+"):
                title, _, subs = line[1:].partition("|")
                cid = f"{subject[:3]}-{grade}-{level}-{_slug(title.strip())}"
                ch = Chapter(cid, subject, grade, title.strip(), level=level)
                ch.subtopics = [Subtopic(f"{cid}.{n}", s, cid) for n, s in enumerate(_parse_subs(subs), start=1)]
                chapters.append(ch)
    # admin edits (hide / rename / add), applied last
    by_id = {c.id: c for c in chapters}
    for op in _load_edits():
        kind = op.get("op")
        if kind == "add_chapter" and op.get("id") not in by_id:
            ch = Chapter(op["id"], op["subject"], int(op["grade"]), op["title"], track=op.get("track", ""))
            ch.subtopics = [Subtopic(f"{ch.id}.{s['key']}", s["title"], ch.id) for s in op.get("subtopics", [])]
            chapters.append(ch)
            by_id[ch.id] = ch
        elif kind == "rename_chapter" and op.get("id") in by_id:
            by_id[op["id"]].title = op["title"]
        elif kind == "hide_chapter" and op.get("id") in by_id:
            by_id[op["id"]].hidden = bool(op.get("hidden", True))
        elif kind == "add_subtopic" and op.get("chapter") in by_id:
            ch = by_id[op["chapter"]]
            if not any(s.id == f"{ch.id}.{op['key']}" for s in ch.subtopics):
                ch.subtopics.append(Subtopic(f"{ch.id}.{op['key']}", op["title"], ch.id))
        elif kind == "rename_subtopic":
            for ch in chapters:
                for s in ch.subtopics:
                    if s.id == op.get("id"):
                        s.title = op["title"]
        elif kind == "hide_subtopic":
            for ch in chapters:
                for pos, s in enumerate(ch.subtopics):
                    if s.id == op.get("id"):
                        ch.removed.append((pos, s))
                        del ch.subtopics[pos]
                        break
        elif kind == "unhide_subtopic":
            for ch in chapters:
                for pos, s in sorted(ch.removed, key=lambda r: r[0]):
                    if s.id == op.get("id"):
                        ch.removed.remove((pos, s))
                        ch.subtopics.insert(min(pos, len(ch.subtopics)), s)
    index = {s.id: (c, s) for c in chapters for s in c.subtopics}
    prereqs: dict[str, list[str]] = {}
    pfile = DATA / "prereqs.txt"
    if pfile.exists():
        for raw in pfile.read_text().splitlines():
            if "<-" in raw and not raw.strip().startswith("#"):
                left, _, right = raw.partition("<-")
                prereqs[left.strip()] = [r.strip() for r in right.split(",") if r.strip()]
    # authors may write full slugs; chapter ids are truncated, so resolve by prefix
    ids = {c.id for c in chapters}

    def resolve(cid: str) -> str:
        return cid if cid in ids else next((i for i in ids if cid.startswith(i)), cid)

    prereqs = {resolve(k): [resolve(v) for v in vs] for k, vs in prereqs.items()}
    return chapters, index, prereqs


def _load():
    global _cache
    with _lock:
        if _cache is None:
            _cache = _build()
        return _cache


def reload() -> None:
    global _cache
    with _lock:
        _cache = None


def _visible(c: Chapter, track: str | None, board: str | None, level: str | None = None) -> bool:
    if c.hidden:
        return False
    if c.level and c.level != (level or ""):
        return False
    if c.track and track and c.track != track.upper():
        return False
    b = (board or "").lower().split()[0] if board else ""
    if c.board == f"not-{b}" and b:
        return False
    if c.board and not c.board.startswith("not-") and c.board != b:
        return False
    return True


def chapters(subject: str | None = None, grade: int | None = None, track: str | None = None, board: str | None = None, level: str | None = None) -> list[Chapter]:
    """Chapters for a subject/grade. Pass `track` ('CS'/'IP') and/or `board` ('icse'...; "" = base syllabus) to resolve
    variants for one student; with neither, every non-hidden chapter of every variant is returned."""
    filtered = track is not None or board is not None or level is not None
    return [c for c in _load()[0]
            if (subject is None or c.subject == subject) and (grade is None or c.grade == grade) and not c.hidden
            and (not filtered or _visible(c, track, board, level))]


def subjects_for(grade: int, stream: str = "", track: str = "") -> list[str]:
    """Subjects recommended to this student (Grades 11-12 follow the stream)."""
    if grade >= 11 and stream in STREAM_SUBJECTS:
        return STREAM_SUBJECTS[stream]
    return [s for s, meta in SUBJECTS.items() if grade in meta["grades"] and s != "commerce"]


def chapter_tree(subject: str, grade: int, track: str | None = None, board: str | None = None, level: str | None = None) -> list[dict]:
    """The chapter list one student sees. Foundation adds "bridge" chapters from earlier classes that this class builds on;
    Challenge adds "extension" chapters beyond the syllabus. Standard is the plain syllabus for the class and board."""
    own = chapters(subject, grade, track or "", board or "", level or "")

    def node(c: Chapter, number: int, group: str = "") -> dict:
        return {"id": c.id, "number": number, "title": c.title, "track": c.track, "board": c.board if not c.board.startswith("not-") else "", "grade": c.grade, "subject": c.subject,
                "group": group, "subtopics": [{"id": s.id, "title": s.title} for s in c.subtopics]}

    base = [node(c, i, "extension" if c.level else "") for i, c in enumerate(own, start=1)]
    if (level or "") != "foundation":
        return base
    seen, bridge = {c.id for c in own}, []
    by_id = {c.id: c for c in _load()[0]}
    for c in own:
        for pid in _load()[2].get(c.id, []):
            pc = by_id.get(pid)
            if pc and pc.id not in seen and pc.grade < grade and not pc.hidden and _visible(pc, track, board, level):
                seen.add(pc.id)
                bridge.append(node(pc, 0, "bridge"))
    for i, b in enumerate(bridge, start=1):
        b["number"] = i
    return bridge + base


def get_subtopic(subtopic_id: str, owner: str | None = None) -> dict | None:
    """A syllabus topic, or a student's own topic (then only for `owner`; pass owner=None for internal use that has no student, owner="" to refuse own topics)."""
    if subtopic_id.startswith("my-"):
        from . import mytopics
        return mytopics.topic(subtopic_id, owner)
    hit = _load()[1].get(subtopic_id)
    if not hit:
        return None
    chapter, st = hit
    sibs = chapter.subtopics
    scope = [s for c in chapters(chapter.subject, chapter.grade, chapter.track or "", chapter.board if not chapter.board.startswith("not-") else "", chapter.level) for s in c.subtopics]
    gpos = next((i for i, s in enumerate(scope) if s.id == st.id), -1)
    return {
        "id": st.id, "title": st.title, "chapter_id": chapter.id, "chapter": chapter.title,
        "subject": chapter.subject, "subject_name": SUBJECTS[chapter.subject]["name"], "grade": chapter.grade,
        "track": chapter.track, "board": chapter.board,
        "chapter_subtopics": [s.title for s in sibs],
        "prev": _brief(scope[gpos - 1]) if gpos > 0 else None,
        "next": _brief(scope[gpos + 1]) if 0 <= gpos + 1 < len(scope) else None,
    }


def _brief(st: Subtopic) -> dict:
    chapter, _ = _load()[1][st.id]
    return {"id": st.id, "title": st.title, "chapter": chapter.title}


def prerequisites(subtopic_id: str) -> list[dict]:
    """Chapters (and the subtopics inside them) to know first: earlier subtopics of this chapter + the prerequisite graph."""
    hit = _load()[1].get(subtopic_id)
    if not hit:
        return []
    chapter, st = hit
    out: list[dict] = []
    for s in chapter.subtopics:
        if s.id == st.id:
            break
        out.append({"id": s.id, "title": s.title, "chapter": chapter.title, "why": "earlier in this chapter"})
    by_id = {c.id: c for c in _load()[0]}
    for pid in _load()[2].get(chapter.id, []):
        pc = by_id.get(pid)
        if pc and pc.subtopics:
            out.append({"id": pc.subtopics[0].id, "title": pc.title, "chapter": pc.title, "grade": pc.grade, "subject": pc.subject,
                        "why": f"builds on Grade {pc.grade}: {pc.title}", "subtopics": [s.id for s in pc.subtopics]})
    return out


def prerequisite_chapters(chapter_id: str) -> list[str]:
    return list(_load()[2].get(chapter_id, []))


def broken_prerequisites() -> list[str]:
    ids = {c.id for c in _load()[0]}
    return [f"{a} <- {b}" for a, bs in _load()[2].items() for b in [a, *bs] if b not in ids]  # ids that match no chapter


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[^\W_]+", text.lower()) if len(t) > 2}


def search(query: str, subject: str | None = None, grade: int | None = None, limit: int = 5, board: str | None = None, track: str | None = None) -> list[dict]:
    """Keyword-overlap search over chapter and subtopic titles (semantic search lives in backend/semantic.py)."""
    q = _tokens(query)
    if not q:
        return []
    scored = []
    for chapter in chapters(subject, grade, track, board):
        ctoks = _tokens(chapter.title)
        for st in chapter.subtopics:
            score = 2 * len(q & _tokens(st.title)) + len(q & ctoks)
            if score:
                scored.append((score, st, chapter))
    scored.sort(key=lambda x: -x[0])
    return [_hit(st, ch) for _, st, ch in scored[:limit]]


def _hit(st: Subtopic, ch: Chapter) -> dict:
    return {"id": st.id, "title": st.title, "chapter": ch.title, "subject": ch.subject,
            "subject_name": SUBJECTS[ch.subject]["name"], "grade": ch.grade}


def all_subtopics(subject: str | None = None, grade: int | None = None, board: str | None = None) -> list[dict]:
    """Every topic; with `board` only those a student of that board sees (base syllabus + that board's overlay)."""
    cs = chapters(subject, grade) if board is None else chapters(subject, grade, "", board)
    return [_hit(s, c) for c in cs for s in c.subtopics]


def stats() -> dict:
    cs = chapters()
    return {"chapters": len(cs), "subtopics": sum(len(c.subtopics) for c in cs), "subjects": len(SUBJECTS)}


# ---- admin editing -----------------------------------------------------------------------------
def apply_edit(op: dict) -> None:
    """Append an edit (add/rename/hide chapter or subtopic) and rebuild. Base files are never modified."""
    with _lock:
        ops = _load_edits()
        ops.append(op)
        EDITS_FILE.write_text(json.dumps({"ops": ops}, ensure_ascii=False, indent=1))
        reload()


def edits() -> list[dict]:
    return _load_edits()


def undo_last_edit() -> dict | None:
    """Take back the most recent administrator edit. -> the edit that was removed."""
    with _lock:
        ops = _load_edits()
        if not ops:
            return None
        last = ops.pop()
        EDITS_FILE.write_text(json.dumps({"ops": ops}, ensure_ascii=False, indent=1))
        reload()
        return last


def admin_tree(subject: str, grade: int) -> list[dict]:
    """Everything of one subject and class for the administrator, hidden items included (the students' own view leaves them out).
    Each chapter says where it comes from: "syllabus", "board" (an overlay such as ICSE), "level" (Challenge extension) or "added" (by an administrator)."""
    added = {op.get("id") for op in _load_edits() if op.get("op") == "add_chapter"}
    out = []
    for c in _load()[0]:
        if c.subject != subject or c.grade != grade:
            continue
        origin = "added" if c.id in added else "level" if c.level else "board" if c.board else "syllabus"
        subs = [{"id": s.id, "title": s.title, "hidden": False} for s in c.subtopics] + [{"id": s.id, "title": s.title, "hidden": True} for _, s in sorted(c.removed, key=lambda r: r[0])]
        out.append({"id": c.id, "title": c.title, "number": c.number, "hidden": c.hidden, "origin": origin, "track": c.track, "board": c.board, "level": c.level, "subtopics": subs})
    return out


def topic_ids(subject: str, grade: int, chapter_id: str | None = None, board: str = "CBSE", level: str = "standard") -> list[str]:
    """The topics a student of this class, board and level would see (used to write lessons in bulk)."""
    chs = chapters(subject, grade, "", "" if board == "CBSE" else board, level)
    return [s.id for c in chs if not chapter_id or c.id == chapter_id for s in c.subtopics]
