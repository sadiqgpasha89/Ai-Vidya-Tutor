"""Canned responses for TEACHER_MOCK=1, so the UI and plumbing can be tried without an API key."""
from __future__ import annotations

import time
from typing import Iterator

_KINDS = [
    ("hook", "Why should I care?"), ("idea", "The big idea"), ("how", "How it works"), ("example", "Worked example"),
    ("edge", "Edge cases & exceptions"), ("proscons", "Advantages & limitations"), ("uses", "Where is this used?"),
    ("mistakes", "Common mistakes & myths"), ("tryit", "Try it yourself"), ("exam", "Exam corner"),
    ("connect", "How it connects"), ("recap", "Quick recap"),
]


def lesson_chunks(topic: dict, language: str) -> Iterator[str]:
    title = topic["title"]
    for kind, heading in _KINDS:
        text = (
            f"=== SECTION: {kind} | {heading} ===\n[DISPLAY]\n**{title}** - demo content for *{heading}*.\n\n"
            "- A key idea written in simple words\n- Another point with a formula $v = u + at$\n\n"
            "$$F = m a$$\n\n[SPEECH]\n"
            f"This is the demo voice for {heading} of {title}. In the real version, your teacher explains this section in simple words, "
            "with everyday examples from India. Press the play button to hear each section.\n\n"
        )
        for i in range(0, len(text), 60):
            time.sleep(0.01)
            yield text[i:i + 60]
        time.sleep(0.15)
    yield "=== END ===\n"


def chat_events(history: list[dict], ctx) -> Iterator[dict]:
    q = history[-1]["content"] if history else ""
    reply = (f"Good question, {ctx.student['name']}! You asked: \"{q[:80]}\". "
             "In demo mode I can't think for real, but here is how it will work: I explain in a few simple sentences, "
             "put the formula on the board, and ask you one quick question to check you got it. Look at the board!")
    yield {"type": "tool", "name": "show_on_board"}
    ctx.events.append({"type": "board", "title": "Demo board",
                       "markdown": "**Newton's second law**\n\n$$F = m a$$\n\nIf $m = 2\\,\\text{kg}$ and $a = 3\\,\\text{m/s}^2$ then $F = 6\\,\\text{N}$.",
                       "svg": '<svg viewBox="0 0 600 200" xmlns="http://www.w3.org/2000/svg"><rect x="200" y="60" width="120" height="80" rx="8" fill="#dbeafe" stroke="#2563eb" stroke-width="3"/><text x="260" y="108" text-anchor="middle" font-size="22" fill="#1e3a8a">m = 2 kg</text><line x1="330" y1="100" x2="460" y2="100" stroke="#dc2626" stroke-width="5"/><polygon points="460,88 488,100 460,112" fill="#dc2626"/><text x="400" y="86" text-anchor="middle" font-size="20" fill="#dc2626">F = 6 N</text></svg>'})
    yield from ctx.events
    ctx.events.clear()
    for word in reply.split(" "):
        time.sleep(0.02)
        yield {"type": "text", "delta": word + " "}
    if "gravity" in q.lower() or "gravit" in q.lower():
        from . import curriculum
        yield {"type": "suggest", "topics": curriculum.search("gravitation", grade=9, limit=2)}
    yield {"type": "done"}


def quiz(topic: dict, n: int) -> dict:
    qs = []
    for i in range(n):
        qs.append({
            "question": f"Demo question {i+1} about {topic['title']}: which option is correct?",
            "options": ["Option A", "The correct answer", "Option C", "Option D"],
            "answer_index": 1, "tests": ["concept", "application", "edge-case", "misconception"][i % 4],
            "hint": "Think about the big idea from the lesson.",
            "explanation": "Because the second option follows from the idea in the lesson.",
            "wrong_option_notes": ["A common slip.", "Correct!", "Mixes up two ideas.", "Confuses the units."],
            "misconception": "Mixing up two related ideas",
        })
    return {"topic": topic, "questions": qs}


def teachback(explanation: str) -> dict:
    words = len(explanation.split())
    return {
        "score": min(95, 30 + words * 2),
        "strengths": ["You used your own words - that is the best way to learn."],
        "gaps": ["Mention an everyday example."],
        "misconceptions": [],
        "next_step": "Try the quiz to check the details.",
        "spoken_feedback": "Nice try! You explained the main idea in your own words. Add one everyday example next time.",
    }


def objectives(topic: dict) -> dict:
    return {"objectives": [f"Explain {topic['title']} in your own words", "Solve a simple problem on it", "Spot a common mistake"],
            "prerequisites": ["Basic ideas from the previous topic"], "key_terms": [topic["title"].split()[0], "formula", "unit"]}


def cheatsheet(topic: dict) -> str:
    return f"**Definition:** demo definition of {topic['title']}.\n\n**Key formula:** $F = ma$\n\n**Remember**\n- Demo point one\n- Demo point two"


def diagram(topic: dict) -> str:
    return ('<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg"><rect x="40" y="40" width="200" height="100" fill="#dbeafe" stroke="#2563eb"/>'
            f'<text x="140" y="95" text-anchor="middle" font-size="18">{topic["title"][:24]}</text></svg>')


def did_you_know(topic: dict) -> list[dict]:
    return [{"emoji": e, "teaser": f"Did you know a surprising fact about {topic['title']}? ({i + 1})", "fact": f"Demo fact {i + 1} about {topic['title']}."} for i, e in enumerate("💡🌍🚀")]


def flashcards(topic: dict) -> list[dict]:
    return [{"front": f"Demo question {i + 1} about {topic['title']}?", "back": f"Demo answer {i + 1}.", "kind": "concept"} for i in range(4)]


def practice(topic: dict) -> dict:
    return {"question": f"Demo problem on {topic['title']}: a car goes 60 km in 2 hours. Find its average speed in km/h.", "kind": "numeric", "has_numeric_answer": True,
            "numeric_answer": 30.0, "unit": "km/h", "answer": "30 km/h", "steps": ["speed = distance / time", "60 / 2 = 30", "so 30 km/h"],
            "hints": ["Which formula links distance, time and speed?", "Divide the distance by the time.", "60 divided by 2."], "concept": "average speed"}
