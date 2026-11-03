"""The scope guard: off-topic questions are redirected without reaching the tutor; on-topic and ambiguous ones are not."""
import pytest

from backend import config, curriculum, llm, scope, tutor


class FakeProvider:
    per_section = False
    verify_quizzes = False

    def __init__(self, related):
        self.related, self.calls = related, 0

    def structured(self, system, user, schema, effort, max_tokens=4000):
        self.calls += 1
        assert "<message>" in user  # the student's words are delimited as data
        return {"related": self.related}


@pytest.fixture()
def topic():
    return curriculum.get_subtopic("phy-9-motion.3")


def test_overlap_skips_the_classifier(topic, monkeypatch):
    fake = FakeProvider(False)
    monkeypatch.setattr(llm, "provider", lambda: fake)
    assert scope.is_off_topic("Why does acceleration depend on the change in velocity so much?", topic, False) is False
    assert fake.calls == 0


def test_short_followups_and_failures_are_never_blocked(topic, monkeypatch):
    fake = FakeProvider(False)
    monkeypatch.setattr(llm, "provider", lambda: fake)
    assert scope.is_off_topic("why is that so?", topic, True) is False and fake.calls == 0
    assert scope.is_off_topic("tell me about the cooking of food", topic, True) is False  # < 8 words with history
    assert scope.is_off_topic("what is 12 times 15 plus the weather today in Delhi", topic, False) is False  # numbers: let the tutor decide
    monkeypatch.setattr(llm, "provider", lambda: (_ for _ in ()).throw(RuntimeError("model down")))
    assert scope.is_off_topic("who won the football match yesterday evening between the two teams", topic, False) is False


def test_off_topic_is_detected_and_redirect_is_translated(topic, monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: FakeProvider(False))
    assert scope.is_off_topic("who won the football match yesterday evening between the two teams", topic, False) is True
    assert "Acceleration" in scope.redirect_text(topic, "en") and "त्वरण" not in scope.redirect_text(topic, "hi") and "Acceleration" in scope.redirect_text(topic, "hi")
    monkeypatch.setattr(llm, "provider", lambda: FakeProvider(True))
    assert scope.is_off_topic("who won the football match yesterday evening between the two teams", topic, False) is False


def test_redirect_does_not_call_the_tutor_model(student, topic, monkeypatch):
    monkeypatch.setattr(config, "MOCK", False)
    monkeypatch.setattr(llm, "provider", lambda: FakeProvider(False))
    events = list(tutor.chat_stream(student, topic, "who won the football match yesterday evening between the two teams"))
    assert [e["type"] for e in events][0] == "text" and events[-1]["type"] == "done"
    assert "outside what we are learning" in events[0]["delta"] and events[0]["delta"].startswith("I'm sorry")
