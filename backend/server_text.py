"""Fixed sentences the server itself says to students (lesson part titles, redirects, safety replies), in every supported language.

English lives here; the other languages are in server_text.json, written by `scripts/translate_ui.py` with a local translation model.
A language or key that is missing falls back to English.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import config

ENGLISH = {
    "title.hook": "Why should I care?", "title.idea": "The big idea", "title.how": "How it works", "title.example": "Worked example",
    "title.edge": "Edge cases & exceptions", "title.proscons": "Advantages & limits", "title.uses": "Where is this used?", "title.mistakes": "Common mistakes & myths",
    "title.tryit": "Try it yourself", "title.exam": "Exam corner", "title.connect": "How it connects", "title.recap": "Quick recap",
    "redirect": "I'm sorry, but I can only help with your studies, and that question is outside what we are learning right now ({subject}: “{topic}”). Please ask me something about {topic} or another school subject, and I will be glad to help.",
    "refuse": "I'm sorry, but I can't help with that request. I'm AIVidya, your study assistant, and I can only help with school subjects, within the law and in a way that keeps everyone safe. Please ask me a question about your lesson or another school subject, and I will be glad to help.",
    "refuse_output": "I'm sorry, but I can't share that response. I'm AIVidya, your study assistant, and I can only help with school subjects. Please ask me a question about your lesson, and I will be glad to help.",
    "support.1": "I'm really sorry you're feeling this way, and I'm glad you told me. You are not alone, and what you feel matters more than any exam or lesson.",
    "support.2": "Please talk to someone you trust right now - a parent, a teacher, an elder or a friend - and tell them how heavy things feel.",
    "support.3": "If you are in danger right now, call **112**. When you feel ready, I'm here to study with you again - but first, please look after yourself. 💛",
}
_FILE = Path(__file__).with_name("server_text.json")


@lru_cache(maxsize=1)
def _table() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reload() -> None:
    _table.cache_clear()


def get(key: str, language: str = "en", **vars) -> str:
    text = _table().get(language, {}).get(key) if language in config.LANGUAGES else None
    text = text or ENGLISH[key]
    return text.format(**vars) if vars else text


def title(kind: str, language: str, fallback: str) -> str:
    return get(f"title.{kind}", language) if language != "en" and f"title.{kind}" in ENGLISH else fallback
