"""Teacher worksheet maker: pick topics, question types and difficulty; get a question paper with an answer key and marking scheme.

Built from the same pieces as students' timed papers (approved bank questions first, the rest written by the model and kept in the bank as unapproved).
Worksheets are private to the teacher who made them. Printing and downloading are done by the page.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator

from . import config, curriculum, db, exams

KINDS = {"mcq": 1, "short": 2, "long": 5, "case": 4, "numeric": 2}  # default marks when the teacher does not say
MAX_QUESTIONS = 40
LEVEL_FOR = {"easy": "foundation", "standard": "standard", "hard": "challenge"}


class WorksheetError(Exception):
    pass


def clean_plan(items: list[dict]) -> list[tuple[str, int, int]]:
    plan, total = [], 0
    for it in items:
        kind, count = str(it.get("kind", "")), int(it.get("count", 0))
        if kind not in KINDS or count < 1:
            continue
        marks = max(1, min(10, int(it.get("marks") or KINDS[kind])))
        plan.append((kind, marks, min(count, 20)))
        total += min(count, 20)
    if not plan:
        raise WorksheetError("Choose at least one type of question.")
    if total > MAX_QUESTIONS:
        raise WorksheetError(f"A worksheet can have at most {MAX_QUESTIONS} questions.")
    return plan


def make(teacher: dict, topic_ids: list[str], plan: list[tuple[str, int, int]], title: str = "", difficulty: str = "standard", language: str = "en", board: str = "CBSE",
         note: str = "", minutes: int = 0) -> Iterator[dict]:
    """Writes the sheet one section at a time. Yields {"type": "progress", ...} and finally {"type": "done", "id": ...}."""
    topic_ids = [t for t in dict.fromkeys(topic_ids) if curriculum.get_subtopic(t, owner="")][:12]
    if not topic_ids:
        raise WorksheetError("Pick at least one topic.")
    pseudo = {"board": board if board in config.BOARDS else "CBSE", "level": LEVEL_FOR.get(difficulty, "standard"), "goal": "boards", "language": language if language in config.LANGUAGES else "en"}
    sections = []
    for idx, (kind, marks, count) in enumerate(plan):
        yield {"type": "progress", "step": idx, "of": len(plan), "kind": kind, "count": count}
        sections.append(exams.build_section(pseudo, topic_ids, idx, kind, marks, count, note))
    total = sum(s["marks"] * len(s["questions"]) for s in sections)
    names = [curriculum.get_subtopic(t, owner="")["title"] for t in topic_ids]
    paper = {"title": (title.strip() or f"Worksheet: {', '.join(names[:2])}{'…' if len(names) > 2 else ''}")[:120], "total_marks": total, "minutes": minutes or max(10, round(total * 1.5)),
             "topics": topic_ids, "topic_names": names, "sections": sections, "difficulty": difficulty, "language": pseudo["language"], "board": pseudo["board"], "note": note[:500]}
    wid = uuid.uuid4().hex[:12]
    db.run("INSERT INTO worksheets (id, created_by, title, paper, settings, created_at) VALUES (?,?,?,?,?,?)", (wid, teacher["id"], paper["title"], json.dumps(paper, ensure_ascii=False),
                                                                                                         json.dumps({"plan": plan}), time.time()))
    yield {"type": "done", "id": wid}


def _own(user: dict, wid: str) -> dict:
    row = db.one("SELECT * FROM worksheets WHERE id=?", (wid,))
    if not row or (row["created_by"] != user["id"] and user["role"] != "admin"):
        raise WorksheetError("Worksheet not found")
    return row


def listing(user: dict) -> list[dict]:
    rows = db.all("SELECT id, title, paper, created_at FROM worksheets WHERE created_by=? ORDER BY created_at DESC LIMIT 100", (user["id"],))
    out = []
    for r in rows:
        p = json.loads(r["paper"])
        out.append({"id": r["id"], "title": r["title"], "created_at": r["created_at"], "total_marks": p["total_marks"], "questions": sum(len(s["questions"]) for s in p["sections"]), "topics": p.get("topic_names", [])})
    return out


def get(user: dict, wid: str) -> dict:
    row = _own(user, wid)
    return {"id": wid, "created_at": row["created_at"], **json.loads(row["paper"])}


def rename(user: dict, wid: str, title: str) -> None:
    row = _own(user, wid)
    paper = json.loads(row["paper"])
    paper["title"] = title.strip()[:120] or paper["title"]
    db.run("UPDATE worksheets SET title=?, paper=? WHERE id=?", (paper["title"], json.dumps(paper, ensure_ascii=False), wid))


def delete(user: dict, wid: str) -> None:
    _own(user, wid)
    db.run("DELETE FROM worksheets WHERE id=?", (wid,))


def replace_question(user: dict, wid: str, question_id: str) -> dict:
    """Swap one question for a fresh one of the same kind and marks (the old one stays in the bank)."""
    row = _own(user, wid)
    paper = json.loads(row["paper"])
    pseudo = {"board": paper.get("board", "CBSE"), "level": LEVEL_FOR.get(paper.get("difficulty", "standard"), "standard"), "goal": "boards", "language": paper.get("language", "en")}
    for sec in paper["sections"]:
        for i, q in enumerate(sec["questions"]):
            if q["id"] != question_id:
                continue
            used = {x["question"] for s in paper["sections"] for x in s["questions"]}
            avoid = "Do not repeat or closely copy any of these questions already on the sheet: " + " | ".join(u[:90] for u in sorted(used))[:700]
            for _attempt in range(2):
                for fresh in exams._gen(paper["topics"], sec["kind"], sec["marks"], 1, pseudo, f"{paper.get('note', '')}\n{avoid}"):
                    if fresh["question"] in used:
                        continue
                    fresh["bank_id"] = exams.bank_add(None, fresh["subtopic_id"], sec["kind"], sec["marks"], fresh["question"], fresh["answer"], fresh["marking_scheme"], fresh["options"], source="ai", approved=False)
                    fresh.update({"id": uuid.uuid4().hex[:8], "marks": sec["marks"], "kind": sec["kind"]})
                    sec["questions"][i] = fresh
                    db.run("UPDATE worksheets SET paper=? WHERE id=?", (json.dumps(paper, ensure_ascii=False), wid))
                    return {"question": fresh}
            raise WorksheetError("Could not write a different question right now. Please try again.")
    raise WorksheetError("Question not found")
