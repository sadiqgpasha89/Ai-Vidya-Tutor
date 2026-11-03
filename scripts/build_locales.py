#!/usr/bin/env python3
"""Build frontend/locales/<lang>.json from scripts/locales_table.txt (key | hi | te | ta | kn | mr | bn)."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
en = json.loads((root / "frontend/locales/en.json").read_text())
langs = ["hi", "te", "ta", "kn", "mr", "bn"]
out: dict[str, dict[str, str]] = {lang: {} for lang in langs}
for line in (root / "scripts/locales_table.txt").read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 7 or parts[0] not in en:
        print("skipped:", line[:70])
        continue
    for lang, value in zip(langs, parts[1:]):
        out[lang][parts[0]] = value
for lang in langs:
    (root / f"frontend/locales/{lang}.json").write_text(json.dumps(out[lang], ensure_ascii=False, indent=1, sort_keys=True))
print({lang: len(v) for lang, v in out.items()})
