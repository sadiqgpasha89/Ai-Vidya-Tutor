#!/usr/bin/env python3
"""Collect every t('key', 'English default') call in the front-end into locales/en.json and report translation coverage.

Usage:  python scripts/i18n_extract.py            # rewrite en.json and print coverage per language
        python scripts/i18n_extract.py --strict   # exit 1 if any language misses a "core" key
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend"
CALL = re.compile(r"""\bt\(\s*(['"`])([\w.\-]+)\1\s*,\s*(['"`])((?:\\.|(?!\3).)*)\3""", re.S)
LANGS = ["hi", "te", "ta", "kn", "mr", "bn"]
CORE_PREFIXES = ("nav.", "common.", "auth.", "home.", "lesson.", "chat.", "quiz.", "set.", "voice.", "profile.", "consent.", "quick.", "board.", "tests.", "rev.")


# keys that live in data tables rather than in t() calls:  ['🧒', 'quick.simpler', 'Explain simpler', ...]
TABLE = re.compile(r"""\[\s*'[^'\w]*',\s*'([a-z]+\.[\w.]+)',\s*'((?:\\.|[^'\\])*)'""")


def extract() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(ROOT.glob("*.js")):
        text = path.read_text()
        for m in TABLE.finditer(text):
            found.setdefault(m.group(1), m.group(2).replace("\\'", "'"))
        for m in CALL.finditer(text):
            key, default = m.group(2), m.group(4).replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")
            found.setdefault(key, default)
    return found


if __name__ == "__main__":
    en = extract()
    (ROOT / "locales" / "en.json").write_text(json.dumps(en, ensure_ascii=False, indent=1, sort_keys=True))
    core = {k for k in en if k.startswith(CORE_PREFIXES)}
    print(f"{len(en)} strings ({len(core)} core)")
    bad = False
    for lang in LANGS:
        f = ROOT / "locales" / f"{lang}.json"
        have = json.loads(f.read_text()) if f.exists() else {}
        stale = [k for k in have if k not in en]
        miss_core = sorted(core - set(have))
        print(f"  {lang}: {len(set(have) & set(en))}/{len(en)} translated, core missing {len(miss_core)}, unused keys {len(stale)}")
        bad |= bool(miss_core)
    sys.exit(1 if bad and "--strict" in sys.argv else 0)
