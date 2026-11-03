"""Automated second look at lessons: deterministic arithmetic checks plus a model review of every section."""
from __future__ import annotations

import json
import re
import threading
import time

from . import config, db, llm, prompts, scheduler, tools
from .logs import get

log = get("factcheck")
# "2 + 3 = 5", "0.5 \times 4 = 2", "12 / 4 = 3"  (only plain numbers on both sides)
_EQ = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?(?:\s*(?:[+\-*/×÷x]|\\times|\\div|\\cdot)\s*-?\d+(?:\.\d+)?)+)\s*=\s*(-?\d+(?:\.\d+)?)(?![\w.])")


def check_arithmetic(text: str) -> list[dict]:
    issues = []
    for m in _EQ.finditer(text.replace("$", "")):
        expr = re.sub(r"\\times|×|x|\\cdot", "*", re.sub(r"\\div|÷", "/", m.group(1)))
        try:
            value = tools.safe_eval(expr)
        except Exception:  # noqa: BLE001
            continue
        stated = float(m.group(2))
        if abs(value - stated) > max(0.01 * abs(value), 0.011):
            issues.append({"claim": m.group(0), "problem": f"{m.group(1).strip()} is {round(value, 6)}, not {m.group(2)}", "severity": "high", "source": "arithmetic"})
    return issues


def review(sections: list[dict], topic: dict) -> dict:
    """-> {"issues": [{section, title, claim, problem, severity, source}], "model", "checked_at"}"""
    found = []
    for i, s in enumerate(sections):
        for issue in check_arithmetic(s["display"]):
            found.append({"section": i, "title": s["title"], **issue})
    if not config.MOCK:
        # one call for the whole lesson: the checking model takes the GPU from the everyday model once, not twelve times
        text = "\n\n".join(f"### Section {i}: {s['title']}\n{s['display']}" for i, s in enumerate(sections))[:14000]
        user = f"Subject: {topic['subject_name']}, Grade {topic['grade']}, topic: {topic['title']}\n\nLESSON:\n{text}"
        try:
            with scheduler.slot(scheduler.BATCH):
                data = llm.provider().structured(prompts.FACTCHECK_SYSTEM, user, prompts.FACTCHECK_SCHEMA, "medium", max_tokens=2500, role="factcheck")
        except Exception as exc:  # noqa: BLE001 - a failed check is recorded, not fatal
            log.warning(f"fact-check failed: {exc}")
            data = {"issues": []}
        for issue in data.get("issues", [])[:12]:
            i = issue.get("section") if isinstance(issue.get("section"), int) and 0 <= issue.get("section", -1) < len(sections) else 0
            found.append({**issue, "section": i, "title": sections[i]["title"], "source": "model"})
    return {"issues": found, "model": config.role_model("factcheck"), "checked_at": time.time()}


def run_for_version(version_id: int) -> None:
    row = db.one("SELECT subtopic_id, sections FROM lesson_versions WHERE id=?", (version_id,))
    if not row:
        return
    from . import curriculum
    topic = curriculum.get_subtopic(row["subtopic_id"])
    if not topic:
        return
    result = review(json.loads(row["sections"])["sections"], topic)
    db.run("UPDATE lesson_versions SET factcheck=? WHERE id=?", (json.dumps(result, ensure_ascii=False), version_id))
    if any(i["severity"] == "high" for i in result["issues"]):
        log.warning(f"lesson version {version_id} has high-severity fact-check issues")


def run_async(version_id: int) -> None:
    from . import prefetch
    if prefetch.enabled():  # queued behind the other background work, and run when the model has been quiet for a while
        prefetch.factcheck_later(version_id, run_for_version)
        return
    threading.Thread(target=run_for_version, args=(version_id,), daemon=True, name=f"factcheck-{version_id}").start()
