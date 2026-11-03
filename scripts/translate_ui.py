#!/usr/bin/env python3
"""Translate the interface (frontend/locales/*.json) and the server's fixed sentences (backend/server_text.json) into all supported languages,
with a local model through Ollama. Safe to stop and run again: strings that already have a translation are kept.

  python scripts/translate_ui.py                 # every language (about 1 hour on a laptop GPU)
  python scripts/translate_ui.py ta gu --limit 40  # just these, and only 40 new strings each (a quick try)

TranslateGemma (55 languages) does the work; it does not know Odia, so Gemma 4 translates that one. These are machine translations:
have a native speaker review them before a wide release.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import config, server_text  # noqa: E402

OLLAMA = config.OLLAMA_HOST.rstrip("/") + "/api/chat"
TRANSLATOR, FALLBACK = "translategemma:4b", "gemma4:e4b"
USE_FALLBACK = {"or"}
ORDER = [k for k, v in config.LANGUAGES.items() if v["group"] == "india"] + [k for k, v in config.LANGUAGES.items() if v["group"] == "world" and k != "en"]
VARS = re.compile(r"\{(\w+)\}")
TAGS = re.compile(r"</?\w+[^>]*>")


def chat(model: str, prompt: str) -> str:
    payload = {"model": model, "stream": False, "keep_alive": "30m", "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 3000}}
    if "gemma4" in model:
        payload["think"] = False
    req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["message"]["content"]


def prompt_for(lang: str, text: str) -> str:
    name, code = config.LANGUAGES[lang]["name"], lang
    if lang in USE_FALLBACK:
        return (f"Translate the following English user-interface text for school students into {name} ({config.LANGUAGES[lang]['native']}), written in {name} script. "
                "Keep tokens like {A} and {B} and HTML tags exactly as they are. Reply with only the numbered translations, one per line, same numbering as the input.\n\n" + text)
    return (f"You are a professional English (en) to {name} ({code}) translator. Your goal is to accurately convey the meaning and nuances of the original English text while adhering to {name} grammar, "
            f"vocabulary, and cultural sensitivities. Produce only the {name} translation, without any additional explanations or commentary. Please translate the following English text into {name} ({code}):\n\n\n" + text)


BRAND = "AIVidya"  # the product name: kept exactly as written, in Latin letters, in every language


def protect(s: str) -> tuple[str, dict]:
    names = list(dict.fromkeys(VARS.findall(s)))
    mapping = {f"{{{chr(65 + i)}}}": f"{{{n}}}" for i, n in enumerate(names)}
    if BRAND in s:
        mapping["{Z}"] = BRAND
    for tok, orig in mapping.items():
        s = s.replace(orig, tok)
    return s, mapping


def restore(s: str, mapping: dict) -> str:
    for tok, orig in mapping.items():
        s = s.replace(tok, orig)
    return s


def valid(src: str, out: str, lang: str) -> bool:
    if not out.strip() or len(out) > max(40, len(src) * 5):
        return False
    if (BRAND in src) != (BRAND in out):  # the name must come through untouched (not translated, transliterated or dropped)
        return False
    if sorted(VARS.findall(src)) != sorted(VARS.findall(out)) or sorted(TAGS.findall(src)) != sorted(TAGS.findall(out)):
        return False
    own = set(config.LANGUAGES[lang]["scripts"])
    for name, block in config.SCRIPTS.items():
        if name != "latin" and name not in own and re.search(f"[{block}]", out):
            return False
    if "latin" not in own:
        words = re.findall(r"[A-Za-z]{4,}", re.sub(r"\{\w+\}|<[^>]+>|https?://\S+", "", out).replace(BRAND, ""))  # the name, {placeholders} and tags are not "English words"
        if len(words) > 2 and re.search(r"[A-Za-z]", src):
            return False  # a "translation" that is mostly English words
    return True


def translate_batch(lang: str, items: list[tuple[str, str]]) -> dict[str, str]:
    prepared = [(k, *protect(v)) for k, v in items]
    text = "\n".join(f"[{i + 1}] {p}" for i, (_, p, _) in enumerate(prepared))
    model = FALLBACK if lang in USE_FALLBACK else TRANSLATOR
    out: dict[str, str] = {}
    try:
        raw = chat(model, prompt_for(lang, text))
    except Exception as exc:  # noqa: BLE001
        print(f"   ! {exc}", flush=True)
        return out
    got = {int(m.group(1)): m.group(2).strip() for m in re.finditer(r"^\s*\[?(\d+)[\].]\s*(.+?)\s*$", raw, re.M)}
    for i, (key, p, mapping) in enumerate(prepared):
        cand = restore(got.get(i + 1, ""), mapping)
        if valid(dict(items)[key], cand, lang):
            out[key] = cand
    return out


def translate_set(lang: str, strings: dict[str, str], done: dict[str, str], limit: int | None, save) -> int:
    todo = [(k, v) for k, v in strings.items() if k not in done and re.search(r"[A-Za-z]", v)]
    if limit:
        todo = todo[:limit]
    n = 0
    for i in range(0, len(todo), 16):
        chunk = todo[i:i + 16]
        got = translate_batch(lang, chunk)
        for k, v in chunk:  # whatever the batch got wrong is tried one by one
            if k not in got:
                got.update(translate_batch(lang, [(k, v)]))
        done.update(got); n += len(got); save()
        print(f"   {lang}: {n}/{len(todo)}", flush=True)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("langs", nargs="*")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    en = json.loads((ROOT / "frontend/locales/en.json").read_text(encoding="utf-8"))
    srv_file = ROOT / "backend/server_text.json"
    for lang in args.langs or ORDER:
        t0 = time.time()
        print(f"== {lang} {config.LANGUAGES[lang]['name']}", flush=True)
        f = ROOT / f"frontend/locales/{lang}.json"
        ui = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        mine = (json.loads(srv_file.read_text(encoding="utf-8")) if srv_file.exists() else {}).get(lang, {})

        def save_server(lang=lang, mine=mine) -> None:  # several copies of this script may run at once, each on its own languages: merge, do not overwrite
            everything = json.loads(srv_file.read_text(encoding="utf-8")) if srv_file.exists() else {}
            everything[lang] = mine
            srv_file.write_text(json.dumps(everything, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

        translate_set(lang, server_text.ENGLISH, mine, args.limit, save_server)
        translate_set(lang, en, ui, args.limit, lambda f=f, ui=ui: f.write_text(json.dumps(ui, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"))
        print(f"   done in {time.time() - t0:.0f}s: {len(ui)}/{len(en)} interface strings", flush=True)


if __name__ == "__main__":
    main()
