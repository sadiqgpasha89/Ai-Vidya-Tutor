"""Exercises OllamaProvider (the local-model path) against a fake Ollama server."""
import socket
import threading
import time

import pytest
import uvicorn

from tests import fake_ollama


@pytest.fixture(scope="module")
def ollama_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(fake_ollama.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    from backend import config
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "PROVIDER", "ollama")
    mp.setattr(config, "OLLAMA_HOST", f"http://127.0.0.1:{port}")
    yield port
    mp.undo()
    server.should_exit = True


@pytest.fixture()
def student(ollama_server):
    from backend import store
    return store.upsert_student("student-local-0001", "Asha", 9, "en", "standard", "CBSE")


def test_health(ollama_server, monkeypatch):
    from backend import config, llm
    assert llm.health() == {"ready": True, "problem": None}
    monkeypatch.setenv("TEACHER_MODEL", "missing-model")
    h = llm.health()
    assert not h["ready"] and "ollama pull missing-model" in h["problem"]
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:9")
    assert "Cannot reach Ollama" in llm.health()["problem"]


def test_chat_tool_loop_local(student):
    from backend import curriculum, tutor
    fake_ollama.REQUESTS.clear()
    topic = curriculum.get_subtopic("phy-9-work-and-energy.2")
    events = list(tutor.chat_stream(student, topic, "KE of 2 kg at 9.8 m/s?"))
    types = [e["type"] for e in events]
    assert "board" in types and types[-1] == "done"
    assert "".join(e["delta"] for e in events if e["type"] == "text") == "Let me work that out. It is 96.04 joules."
    safety, first, second = fake_ollama.REQUESTS  # the first call is the safety read of the student's message
    assert "<message>" in safety["messages"][-1]["content"]
    assert first["messages"][0]["role"] == "system" and "LOCAL-MODEL RULES" in first["messages"][0]["content"]
    assert "get_student_profile" not in {t["function"]["name"] for t in first["tools"]}  # small models get a shorter tool menu
    assert {t["function"]["name"] for t in first["tools"]} >= {"calculator", "show_on_board"}
    tool_msgs = [m for m in second["messages"] if m["role"] == "tool"]
    assert [m["tool_name"] for m in tool_msgs] == ["calculator", "show_on_board"] and tool_msgs[0]["content"] == "0.5 * 2 * 9.8 ** 2 = 96.04"
    assert first["options"]["num_ctx"] >= 8192


def test_lesson_per_section(student):
    from backend import lesson
    events = list(lesson.stream_lesson("phy-9-work-and-energy.4", "en", "standard", "CBSE"))
    secs = [e for e in events if e["type"] == "section"]
    assert len(secs) == 12 and events[-1]["type"] in ("done",) and any(e["type"] == "_yield_slot" for e in events)
    assert secs[0]["speech"] == "Spoken words." and secs[0]["display"] == "Body with $a=b$."
    hi = [e for e in lesson.stream_lesson("phy-9-work-and-energy.1", "hi", "standard", "CBSE") if e["type"] == "section"]
    assert hi[0]["title"] == "मुझे यह क्यों जानना चाहिए?"


def test_quiz_repairs_latex_verifies_keys_and_strips_letters(student):
    from backend import quiz
    q = quiz.make_quiz(student, "phy-9-work-and-energy.2", "en", "standard", 3)
    texts = [x["question"] for x in q["questions"]]
    assert texts == ["Compute $\\frac{1}{2} \\times 4$", "Second"]  # control characters repaired; the wrongly keyed one dropped
    assert q["questions"][0]["options"] == ["1", "2", "4", "8"]


def test_teachback_local(student):
    from backend import quiz
    assert quiz.evaluate_teachback(student, "phy-9-work-and-energy.2", "Energy of motion, like a moving cricket ball.")["score"] == 64


def test_friendly_error_when_ollama_down(student, monkeypatch):
    from backend import config, curriculum, tutor
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:9")
    topic = curriculum.get_subtopic("phy-9-work-and-energy.2")
    last = list(tutor.chat_stream(student, topic, "hi"))[-1]
    assert last["type"] == "error" and "ollama serve" in last["message"]


def test_each_job_has_a_model_and_missing_ones_fall_back(ollama_server, monkeypatch):
    """Only llama3.1:8b is installed on the fake server: every job must still get a usable model; a pinned missing model is reported."""
    from backend import config, llm
    prov = llm.provider()
    prov._tags = (0.0, set())
    for role in config.MODEL_ROLES:
        assert prov.resolve(role) == "llama3.1:8b", (role, config.is_pinned(role), config.role_model(role, "ollama"))
    monkeypatch.setenv("TEACHER_MODEL_FIGURE", "gpt-oss:20b")
    assert prov.resolve("figure") == "gpt-oss:20b"  # explicit choice is respected, so a typo is visible rather than silently replaced
    monkeypatch.delenv("TEACHER_MODEL_FIGURE")
    assert config.role_model("figure", "ollama") == "gpt-oss:20b" and config.role_model("lesson", "ollama") == "gemma4:e4b"
    monkeypatch.setenv("TEACHER_MODEL", "llama3.1:8b")
    assert config.role_model("chat", "ollama") == "llama3.1:8b" and config.role_model("figure", "ollama") == "gpt-oss:20b"


def test_bad_json_in_a_tool_call_is_retried(student):
    """gemma sometimes writes \\frac inside a tool call; Ollama rejects the reply. The tutor must ask again and still answer."""
    from backend import curriculum, tutor
    fake_ollama.REQUESTS.clear()
    topic = curriculum.get_subtopic("phy-9-work-and-energy.2")
    events = list(tutor.chat_stream(student, topic, "BACKSLASH-FAIL KE of 2 kg at 9.8 m/s?"))
    text = "".join(e.get("delta", "") for e in events if e["type"] == "text")
    assert "96.04" in text and not any(e["type"] == "error" for e in events)
    assert any("JSON: write every backslash" in str(r["messages"]) for r in fake_ollama.REQUESTS)
