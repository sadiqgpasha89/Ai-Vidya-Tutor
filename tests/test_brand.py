"""The product is called AIVidya everywhere a person can read it: screens, emails, the tutor's own name, downloads, documents, and in every language."""
import json
import re
from pathlib import Path

from backend import server_text

ROOT = Path(__file__).resolve().parent.parent
BARE = re.compile(r"(?<![A-Za-z])Vidya(?![A-Za-z])")  # "Vidya" on its own; AIVidya and identifiers such as vidya_session do not match
SKIP = {".venv", "node_modules", "data", "vendor", ".git", "__pycache__", "uv.lock"}


def _files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP) and p.suffix in {".py", ".js", ".html", ".json", ".md", ".txt", ".webmanifest", ".yml", ".sh", ".toml", ".example"} | {""}:
            yield p


def test_no_file_calls_the_product_just_vidya():
    bad = {}
    for p in _files():
        if p.name in ("test_brand.py", "migrations.py"):  # (the migration that renames old text has to spell the old name)
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = [m.start() for m in BARE.finditer(text)]
        if hits:
            bad[str(p.relative_to(ROOT))] = len(hits)
    assert not bad, f"still says plain 'Vidya': {bad}"


def test_every_translation_keeps_the_name_exactly():
    en = json.loads((ROOT / "frontend/locales/en.json").read_text(encoding="utf-8"))
    branded = [k for k, v in en.items() if "AIVidya" in v]
    assert len(branded) > 20
    for f in (ROOT / "frontend/locales").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        missing = [k for k in branded if k in d and "AIVidya" not in d[k]]
        assert not missing, f"{f.name}: {missing[:5]}"
    table = json.loads((ROOT / "backend/server_text.json").read_text(encoding="utf-8"))
    for key in (k for k, v in server_text.ENGLISH.items() if "AIVidya" in v):
        for lang, strings in table.items():
            assert key not in strings or "AIVidya" in strings[key], f"{lang}.{key}"


def test_the_tutor_introduces_itself_with_the_new_name():
    from backend import prompts
    assert "You are AIVidya" in prompts.TUTOR_SYSTEM
    assert "AIVidya" in server_text.get("refuse", "en") and "AIVidya" in server_text.get("support.1", "en") + server_text.get("refuse", "en")
    assert '"name": "AIVidya' in (ROOT / "frontend/manifest.webmanifest").read_text(encoding="utf-8")
    assert "<title>AIVidya" in (ROOT / "frontend/index.html").read_text(encoding="utf-8")


def test_old_stored_text_is_renamed_once_and_never_doubled(tmp_path):
    import sqlite3

    from backend import migrations
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE chat_messages (id INTEGER, content TEXT)")
    c.executemany("INSERT INTO chat_messages VALUES (?,?)", [(1, "I'm Vidya, your teacher. Ask Vidya anything."), (2, "Ask AIVidya anything."), (3, "Mix: Vidya and AIVidya."), (4, "No name here."), (5, "Vidya-Server and Vidyarthi")])
    c.executescript("\n".join(line for line in migrations.RENAME_BRAND.splitlines() if line.startswith("UPDATE chat_messages")))
    got = dict(c.execute("SELECT id, content FROM chat_messages"))
    assert got[1] == "I'm AIVidya, your teacher. Ask AIVidya anything." and got[2] == "Ask AIVidya anything."
    assert got[3] == "Mix: AIVidya and AIVidya." and got[4] == "No name here." and "AIAIVidya" not in "".join(got.values())
    assert got[5] == "AIVidya-Server and AIVidyarthi"  # (a word that merely starts with the name would be caught too; none exists in this product's own text)
