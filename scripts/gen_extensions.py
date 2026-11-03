#!/usr/bin/env python3
"""Draft the Challenge-level extension chapters (backend/curriculum_data/levels/challenge.txt) with the local model.

For each subject and class it asks gpt-oss for three chapters that go beyond the board syllabus (olympiad, JEE/NEET foundation, programming contests),
shows the model the chapters the class already has so nothing is repeated, and writes them in the overlay format. They are AI drafts, NOT checked by a teacher:
the student page says so, and teachers can hide or rename any of them in the curriculum editor.

  python scripts/gen_extensions.py                  # all subjects, classes 8-12 (about 20 minutes)
  python scripts/gen_extensions.py physics 9 10     # one subject, some classes
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import config, curriculum  # noqa: E402

OUT = ROOT / "backend/curriculum_data/levels/challenge.txt"
MODEL = config.role_model("figure", "ollama")  # gpt-oss: the stronger local model
SUBJECTS = ["physics", "chemistry", "biology", "maths", "computers"]
AIMS = {"physics": "Physics Olympiad (NSEP/INPhO) and JEE foundation", "chemistry": "Chemistry Olympiad (NSEC) and JEE/NEET foundation", "biology": "Biology Olympiad (NSEB) and NEET foundation",
        "maths": "Mathematics Olympiad (RMO/IOQM) and JEE foundation", "computers": "programming contests (USACO/IOI style) and computational thinking"}
SCHEMA = {"type": "object", "properties": {"chapters": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
    "title": {"type": "string"}, "subtopics": {"type": "array", "minItems": 4, "maxItems": 6, "items": {"type": "string"}}}, "required": ["title", "subtopics"]}}}, "required": ["chapters"]}


def ask(subject: str, grade: int, have: list[str], later: list[str]) -> list[dict]:
    prompt = (f"You are a senior teacher in India preparing extension material for strong Class {grade} students of {subject}, aiming at {AIMS[subject]}.\n"
              f"Class {grade} already studies these chapters: {'; '.join(have)}.\n"
              f"Later classes (9-12) will study these, so do NOT use them: {'; '.join(later[:60])}.\n"
              "Propose exactly 3 NEW chapters of enrichment that a strong Class {g} student can follow. Rules: (1) use only the mathematics a Class {g} student has (no calculus, no vectors, "
              "no trigonometry beyond what Class {g} covers); (2) go DEEPER or more problem-solving on ideas near this class's syllabus, or add genuinely new but elementary ideas; "
              "never pull in a chapter from a later class; (3) each has 4 to 6 specific subtopics, short titles, no numbering; (4) real, standard olympiad material; no fluff.").replace("{g}", str(grade))
    payload = {"model": MODEL, "stream": False, "think": "low", "format": SCHEMA, "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0.3, "num_ctx": 8192, "num_predict": 3000}}
    req = urllib.request.Request(config.OLLAMA_HOST.rstrip("/") + "/api/chat", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.load(r)["message"]["content"])["chapters"]


def clean(s: str) -> str:
    return re.sub(r"[|;\n]+", ",", s).strip(" .")


def main() -> None:
    args = sys.argv[1:]
    subjects = [a for a in args if a in SUBJECTS] or SUBJECTS
    grades = [int(a) for a in args if a.isdigit()] or [8, 9, 10, 11, 12]
    lines = ["# Challenge extensions: chapters beyond the board syllabus, shown only to students who choose the Challenge level.",
             "# Drafted by the local model (scripts/gen_extensions.py) and NOT checked by a teacher. Hide or rename chapters in the curriculum editor, or edit this file.", ""]
    for subject in SUBJECTS:
        sec = []
        for grade in range(8, 13):
            if subject not in subjects or grade not in grades:
                continue
            have = sorted({c.title for c in curriculum.chapters(subject, grade) if not c.level})
            later = sorted({c.title for g in range(grade + 1, 13) for c in curriculum.chapters(subject, g) if not c.level})
            if not have or (subject in ("physics", "chemistry", "biology") and grade < 11):  # science drafts for classes 8-10 overreached; see levels/challenge-core.txt
                continue
            t0 = time.time()
            try:
                chs = ask(subject, grade, have, later)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {subject} {grade}: {exc}", flush=True)
                continue
            keep = [c for c in chs if clean(c["title"]).lower() not in {h.lower() for h in have} and len(c["subtopics"]) >= 3]
            sec.append((grade, keep))
            print(f"{subject} {grade}: {len(keep)} chapters in {time.time() - t0:.0f}s", flush=True)
        if sec:
            lines.append(f"@subject {subject}")
            for grade, keep in sec:
                lines.append(f"@grade {grade}")
                lines += [f"+ {clean(c['title'])} | {'; '.join(clean(s) for s in c['subtopics'])}" for c in keep]
            lines.append("")
    if len(sys.argv) > 1 and OUT.exists():  # a partial run merges into the existing file by replacing only what it regenerated
        print("Partial run: review the printed chapters and merge them into", OUT)
        print("\n".join(lines))
        return
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
