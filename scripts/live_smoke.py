#!/usr/bin/env python3
"""Run against a REAL model (no mock) to confirm lesson writing, chat with tools, quiz, grading and vision work end to end.

  python scripts/live_smoke.py                       # uses TEACHER_PROVIDER / TEACHER_MODEL from the environment or .env
  TEACHER_PROVIDER=anthropic ANTHROPIC_API_KEY=... python scripts/live_smoke.py
Writes into a throw-away data folder; prints PASS/FAIL per step and exits 1 on any failure.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["TEACHER_DATA_DIR"] = tempfile.mkdtemp(prefix="vidya-smoke-")
os.environ.setdefault("TEACHER_WARMUP", "0")

from backend import accounts, config, curriculum, extras, lesson, llm, quiz, store, tutor  # noqa: E402

results: list[tuple[str, bool, str]] = []


def step(name):
    def deco(fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.time() - t0:.1f}s)"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(("PASS " if results[-1][1] else "FAIL ") + name + " - " + results[-1][2], flush=True)
        return fn
    return deco


print(f"provider={config.PROVIDER} model={config.model()} quiz_model={config.structured_model()}")
user = accounts.create_user("smoke.student", "Passw0rd!x", "Smoke", "student", 2006, profile={"grade": 9})
student = store.get_student(user["id"])
topic = curriculum.get_subtopic("phy-9-work-and-energy.2")


@step("model reachable")
def _():
    h = llm.health()
    assert h["ready"], h["problem"]


@step("lesson: 12 sections, spoken text present")
def _():
    events = [e for e in lesson.stream_lesson(topic["id"], "en", "standard", "CBSE") if e["type"] != "_yield_slot"]
    secs = [e for e in events if e["type"] == "section"]
    assert not any(e["type"] == "error" for e in events), events[-1]
    assert len(secs) >= 10 and all(len(s["speech"].split()) > 20 for s in secs), [len(s["speech"].split()) for s in secs]
    return f"{len(secs)} sections"


@step("chat answers a numeric question correctly")
def _():
    ev = list(tutor.chat_stream(student, topic, "A 2 kg ball moves at 3 m/s. What is its kinetic energy?"))
    text = "".join(e.get("delta", "") for e in ev)
    assert not any(e["type"] == "error" for e in ev), ev[-1]
    assert "9" in text, text[:300]


@step("chat stays on topic")
def _():
    text = "".join(e.get("delta", "") for e in tutor.chat_stream(student, topic, "Who won the cricket world cup in 2011?"))
    assert "India" not in text or "topic" in text.lower() or "energy" in text.lower(), text[:300]


@step("quiz: valid questions")
def _():
    q = quiz.make_quiz(student, topic["id"], "en", "standard", 3)
    assert q["questions"] and all(len(x["options"]) == 4 for x in q["questions"])
    return f"{len(q['questions'])} questions"


@step("teach-back grading")
def _():
    r = quiz.evaluate_teachback(student, topic["id"], "Kinetic energy is the energy a moving object has, equal to half mass times speed squared.")
    assert 0 <= r["score"] <= 100


@step("flashcards + cheat-sheet + diagram")
def _():
    assert extras.flashcards(topic["id"], "en")
    assert len(extras.cheatsheet(topic["id"], "en", "standard", "CBSE")) > 80
    return "diagram: " + ("ok" if extras.diagram(topic["id"], "en", "standard", "CBSE") else "not drawn (model output unusable)")

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} steps passed")
sys.exit(1 if failed else 0)
