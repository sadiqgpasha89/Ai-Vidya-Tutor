"""The translated interface must keep every {placeholder} and HTML tag, and stay in the language's own script."""
import json
import re
from pathlib import Path

import pytest

from backend import config, server_text

ROOT = Path(__file__).resolve().parent.parent
EN = json.loads((ROOT / "frontend/locales/en.json").read_text(encoding="utf-8"))
VARS, TAGS = re.compile(r"\{(\w+)\}"), re.compile(r"</?\w+[^>]*>")
OTHER = [c for c in config.LANGUAGES if c != "en"]


def foreign(text: str, lang: str) -> bool:
    own = set(config.LANGUAGES[lang]["scripts"])
    return any(re.search(f"[{block}]", text) for name, block in config.SCRIPTS.items() if name != "latin" and name not in own)


@pytest.mark.parametrize("lang", OTHER)
def test_interface_translation_is_well_formed(lang):
    f = ROOT / f"frontend/locales/{lang}.json"
    assert f.exists(), f"no interface translation for {lang}"
    data = json.loads(f.read_text(encoding="utf-8"))
    assert len(data) > 0.6 * len(EN), f"{lang}: only {len(data)} of {len(EN)} strings translated"
    bad = []
    for key, text in data.items():
        src = EN.get(key)
        if src is None:
            continue  # a string that no longer exists in the app
        if sorted(VARS.findall(src)) != sorted(VARS.findall(text)) or sorted(TAGS.findall(src)) != sorted(TAGS.findall(text)) or foreign(text, lang):
            bad.append(key)
    assert not bad, f"{lang}: broken placeholders/tags/script in {bad[:8]}"


@pytest.mark.parametrize("lang", OTHER)
def test_server_sentences_are_translated(lang):
    for key, english in server_text.ENGLISH.items():
        text = server_text.get(key, lang, **{v: "X" for v in VARS.findall(english)})
        assert text and not foreign(text, lang), (lang, key)
