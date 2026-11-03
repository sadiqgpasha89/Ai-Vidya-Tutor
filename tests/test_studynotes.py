"""Prepared study notes: made from the lesson, kept per student in SQLite, downloadable as HTML or Markdown, private and erased with the account."""
import pytest

from backend import config, db, lesson, studynotes

SUB = "phy-9-motion.3"


@pytest.fixture()
def mock_lesson(student, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    list(lesson.stream_lesson(SUB, "en", "standard", "CBSE"))
    from backend import curriculum
    return student, curriculum.get_subtopic(SUB)


def test_notes_need_the_lesson_then_are_saved_and_replaced(student, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    from backend import curriculum
    topic = curriculum.get_subtopic("phy-9-motion.5")
    with pytest.raises(ValueError):
        studynotes.prepare(student, "phy-9-motion.5", topic)
    list(lesson.stream_lesson("phy-9-motion.5", "en", "standard", "CBSE"))
    assert studynotes.get(student, "phy-9-motion.5") is None
    note = studynotes.prepare(student, "phy-9-motion.5", topic)
    assert len(note["sections"]) >= 3 and all(s["bullets"] and s["svg"].startswith("<svg") for s in note["sections"])
    assert studynotes.get(student, "phy-9-motion.5")["title"] == note["title"]  # persisted
    again = studynotes.prepare(student, "phy-9-motion.5", topic)
    assert again["created_at"] == note["created_at"] and again["updated_at"] >= note["updated_at"]
    assert db.one("SELECT COUNT(*) AS n FROM study_notes WHERE student_id=?", (student["id"],))["n"] == 1
    assert [i["subtopic_id"] for i in studynotes.list_for(student["id"])] == ["phy-9-motion.5"]
    studynotes.delete(student, "phy-9-motion.5")
    assert studynotes.get(student, "phy-9-motion.5") is None


def test_downloads_are_self_contained(mock_lesson):
    student, topic = mock_lesson
    note = studynotes.prepare(student, SUB, topic)
    page = studynotes.to_html(note)
    assert page.startswith("<!doctype html>") and "<svg" in page and "<ul>" in page and "<script" not in page and "http" not in page.split("<footer>")[0].replace("http://www.w3.org/2000/svg", "")
    md = studynotes.to_markdown(note)
    assert md.startswith("# ") and "\n- " in md and "data:image/svg+xml;base64," in md


def test_html_download_escapes_text_and_writes_maths_out():
    note = {"title": "A <b>&", "summary": "", "remember": ["Speed $v = \\frac{d}{t}$ is **key**"], "language": "en", "sections": [{"heading": "<script>x</script>", "bullets": ["**bold** & <i>"], "svg": None}]}
    page = studynotes.to_html(note)
    assert "<script>x" not in page and "&lt;script&gt;" in page and "<b>bold</b> &amp; &lt;i&gt;" in page and "d/t" in page and "$" not in page.split("<body>")[1]


def test_malformed_model_notes_are_rejected_or_repaired(student, monkeypatch):
    from backend import curriculum, extras
    monkeypatch.setattr(config, "MOCK", True)
    list(lesson.stream_lesson(SUB, "en", "standard", "CBSE"))
    monkeypatch.setattr(config, "MOCK", False)
    topic = curriculum.get_subtopic(SUB)
    monkeypatch.setattr(extras, "_structured", lambda *a, **k: {"title": "t", "sections": [{"heading": "only one", "bullets": ["a"]}]})
    with pytest.raises(RuntimeError):
        studynotes.prepare(student, SUB, topic)
    good = {"title": "Motion $v$", "summary": "s", "remember": ["a"], "sections": [
        {"heading": "Idea", "bullets": ["**Speed** is distance over time", "- unit is m/s"], "diagram": {"layout": "pie", "title": "x"}},  # bad diagram -> drawn from the bullets
        {"heading": "Steps", "bullets": ["Measure distance", "Measure time", "Divide the two"], "diagram": {"layout": "flow", "title": "Steps", "items": [{"label": "Distance"}, {"label": "Time"}, {"label": "Divide"}]}},
        {"heading": "Mistakes", "bullets": ["Mixing km and m", "Forgetting units", "Using the wrong time"]}]}
    monkeypatch.setattr(extras, "_structured", lambda *a, **k: good)
    note = studynotes.prepare(student, SUB, topic)
    assert len(note["sections"]) == 3 and note["sections"][0]["bullets"][1] == "unit is m/s" and note["sections"][1]["svg"] and "$" not in note["title"]
    assert note["sections"][2]["svg"] is None or note["sections"][2]["svg"].startswith("<svg")


def test_stray_markdown_markers_are_removed():
    assert studynotes._clean_bullets(["Zero** is the input", "**Speed** is $v", "- **ok** and $x$"]) == ["Zero is the input", "**Speed** is v", "**ok** and $x$"]
