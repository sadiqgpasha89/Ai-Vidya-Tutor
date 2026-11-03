"""Runs the real anthropic SDK code paths (streaming lesson, tool loop, structured output) against a local fake API."""
import socket
import threading
import time

import pytest
import uvicorn

from tests import fake_anthropic


@pytest.fixture(scope="module")
def fake_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(fake_anthropic.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    import os
    from backend import config
    from backend.providers import anthropic_provider
    os.environ["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    anthropic_provider._client = None
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "PROVIDER", "anthropic")
    yield port
    mp.undo()
    server.should_exit = True


@pytest.fixture()
def student(fake_server):
    from backend import store
    return store.upsert_student("student-test-0001", "Asha", 9, "en", "standard", "CBSE")


def test_chat_tool_loop(student, fake_server):
    from backend import curriculum, tutor
    fake_anthropic.REQUESTS.clear()
    topic = curriculum.get_subtopic("phy-9-work-and-energy.2")
    events = list(tutor.chat_stream(student, topic, "What is the KE of a 2 kg ball moving at 9.8 m/s?"))
    types = [e["type"] for e in events]
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "tool" in types and "board" in types and types[-1] == "done"
    assert "96.04 joules" in text
    assert len(fake_anthropic.REQUESTS) == 3  # a safety read of the message, then the two turns of the tool loop
    _, first, second = fake_anthropic.REQUESTS
    assert first["output_config"]["effort"] == "low"
    assert {t["name"] for t in first["tools"]} >= {"calculator", "show_on_board", "find_topics"}
    assert any(b.get("cache_control") for b in first["system"])
    # second request replays the assistant turn and answers BOTH tool calls in a single user message
    assert second["messages"][-2]["role"] == "assistant"
    results = second["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_calc", "toolu_board"]
    assert results[0]["content"] == "0.5 * 2 * 9.8 ** 2 = 96.04" and not results[0].get("is_error")


def test_lesson_streams_and_caches(student, fake_server):
    from backend import lesson
    lesson_events = list(lesson.stream_lesson("phy-9-work-and-energy.3", "en", "standard", "CBSE"))
    kinds = [e["type"] for e in lesson_events]
    assert kinds[0] == "meta" and kinds[-1] == "done" and lesson_events[-1]["cached"] is False and "version" in kinds
    assert kinds.count("section") == 4 and kinds.count("section_start") == 4
    sec = next(e for e in lesson_events if e["type"] == "section")
    assert sec["speech"] == "Spoken words for Why care." and "$a = v/t$" in sec["display"]
    import threading
    for t in threading.enumerate():  # the automatic fact-check runs in the background after a lesson is written
        if t.name.startswith("factcheck"):
            t.join(10)
    v = lesson.active_version("phy-9-work-and-energy.3", lesson.variant("en", "standard", "CBSE"))
    assert v["status"] == "draft" and v["factcheck"] is not None and v["model"]
    before = len(fake_anthropic.REQUESTS)
    again = list(lesson.stream_lesson("phy-9-work-and-energy.3", "en", "standard", "CBSE"))
    assert again[-1]["cached"] is True and len(fake_anthropic.REQUESTS) == before  # served from disk, no API call


def test_quiz_and_teachback_structured(student, fake_server):
    from backend import quiz, store
    q = quiz.make_quiz(student, "phy-9-work-and-energy.2", "en", "standard", 3)
    assert q["questions"][0]["answer_index"] == 2
    r = quiz.evaluate_teachback(student, "phy-9-work-and-energy.2", "Kinetic energy is the energy of motion.")
    assert r["score"] == 72
    sig = store.recent_signals(student["id"], "phy-9-work-and-energy.2")
    assert any("speed is acceleration" in s["note"] for s in sig)
    assert 0.4 < store.progress_map(student["id"])["phy-9-work-and-energy.2"]["mastery"] < 0.9
