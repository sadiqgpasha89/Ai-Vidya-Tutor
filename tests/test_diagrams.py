"""Concept diagrams drawn by code: every layout renders, text never overlaps, and thin or malformed descriptions are rejected."""
import re

import pytest

from backend import diagrams

FLOW = {"layout": "flow", "title": "How a cell makes energy", "items": [{"label": "Glucose enters", "note": "Food is broken into glucose"}, {"label": "Glycolysis"}, {"label": "Mitochondria", "note": "Pyruvate is used with oxygen"}, {"label": "ATP released"}]}
CYCLE = {"layout": "cycle", "title": "Water cycle", "items": [{"label": "Evaporation"}, {"label": "Condensation"}, {"label": "Precipitation"}, {"label": "Collection", "note": "Rivers carry it to the sea"}]}
COMPARE = {"layout": "compare", "title": "Plant vs animal cell", "columns": [{"heading": "Plant", "points": ["Cell wall", "Chloroplasts for photosynthesis"]}, {"heading": "Animal", "points": ["No cell wall", "No chloroplasts"]}]}
MAP = {"layout": "map", "title": "Parts of a cell", "items": [{"label": "Cell"}, {"label": "Nucleus", "note": "Holds DNA"}, {"label": "Mitochondria"}, {"label": "Membrane"}, {"label": "Cytoplasm"}]}


@pytest.mark.parametrize("spec", [FLOW, CYCLE, COMPARE, MAP])
def test_every_layout_renders_safe_svg(spec):
    svg = diagrams.render(spec)
    assert svg and svg.startswith("<svg") and "<script" not in svg
    assert len(re.findall(r"<text\b", svg)) >= 5


def test_text_is_escaped_and_long_text_is_wrapped():
    spec = {**FLOW, "title": "A < B & C", "items": [{"label": "word " * 30, "note": "x" * 400}] * 3}
    svg = diagrams.render(spec)
    assert svg and "A &lt; B &amp; C" in svg and "<B" not in svg


def test_other_scripts_and_right_to_left():
    hindi = {**FLOW, "title": "कोशिका ऊर्जा कैसे बनाती है", "items": [{"label": "ग्लूकोज़ प्रवेश करता है", "note": "भोजन टूटकर ग्लूकोज़ बनता है"}] * 3}
    assert "कोशिका" in diagrams.render(hindi, "hi")
    chinese = {**COMPARE, "columns": [{"heading": "植物细胞", "points": ["细胞壁" * 20]}, {"heading": "动物细胞", "points": ["没有细胞壁"]}]}
    assert diagrams.render(chinese, "zh")
    assert 'text-anchor="end"' in diagrams.render(COMPARE, "ar")


def test_a_crowded_ring_falls_back_to_a_list():
    ring = {"layout": "cycle", "title": "t", "items": [{"label": "A fairly long label here", "note": "and a note that wraps over lines"}] * 6}
    assert diagrams.render(ring)


@pytest.mark.parametrize("bad", [None, "x", {}, {"layout": "pie", "title": "t"}, {"layout": "flow", "title": ""}, {"layout": "flow", "title": "t", "items": [{"label": "a"}]},
                                 {"layout": "compare", "title": "t", "columns": [{"heading": "h", "points": ["p"]}]}, {"layout": "map", "title": "t", "items": [{"label": "a"}, {"label": "b"}]}])
def test_thin_or_malformed_descriptions_are_rejected(bad):
    assert diagrams.render(bad) is None


def test_maths_in_labels_is_written_out():
    svg = diagrams.render({"layout": "flow", "title": "Speed $v = \\frac{d}{t}$", "items": [{"label": "**Find** $d \\times 2$", "note": "x^2"}] * 3})
    assert svg and "$" not in svg and "\\" not in svg and "**" not in svg and "d/t" in svg and "×" in svg and "²" in svg


def test_a_plain_diagram_can_be_built_from_the_text_itself():
    text = "Cells are **fundamental units**. A cell has:\n- a nucleus that controls it\n- cytoplasm where reactions happen\n- a membrane at the edge\n"
    for kind, layout in (("how", "flow"), ("idea", "map")):
        spec = diagrams.fallback_spec("The cell", text, kind)
        assert spec["layout"] == layout and len(spec["items"]) >= 3 and diagrams.render(spec)
    assert diagrams.fallback_spec("t", "Too short.") is None


def test_model_failure_still_gives_a_picture(monkeypatch):
    """When the model's description is unusable (twice) a plain diagram is drawn from the section's text."""
    from backend import config, extras
    monkeypatch.setattr(config, "MOCK", False)
    monkeypatch.setattr(extras, "_structured", lambda *a, **k: {"layout": "pie"})
    topic = {"subject_name": "Biology", "grade": 9, "chapter": "Cells", "title": "Cell"}
    out = extras.concept_diagram(topic, "The cell", "**Nucleus**, **cytoplasm** and **membrane** are parts of a cell.\n- Nucleus controls\n- Membrane protects", "idea", "en")
    assert out and out["svg"].startswith("<svg")
    monkeypatch.setattr(extras, "_structured", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model down")))
    assert extras.concept_diagram(topic, "The cell", "- one thing here\n- another thing here\n- a third thing here", "idea", "en")
    assert extras.concept_diagram(topic, "x", "No usable structure.", "idea", "en") is None
