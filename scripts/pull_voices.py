#!/usr/bin/env python3
"""Download every local voice and the speech-recognition model, so nothing is fetched while a student waits.

  python scripts/pull_voices.py            # the 16 Piper voices (about 1 GB) + Whisper 'small' (about 480 MB)
  python scripts/pull_voices.py hi ta en   # only these languages
Tamil, Gujarati, Kannada and Odia voices come from `python scripts/export_mms.py` (they need PyTorch once, to convert).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import config, voice  # noqa: E402

langs = sys.argv[1:] or list(config.LANGUAGES)
for lang in langs:
    if lang in voice.PIPER_VOICES:
        if voice.installed(lang):
            print(f"✓ {lang} voice already installed")
        else:
            print(f"↓ {lang} voice …", flush=True)
            voice.install_voice(lang)
    elif lang in voice.MMS_VOICES:
        print(("✓" if voice.installed(lang) else "✗ run scripts/export_mms.py for") + f" {lang} voice")
if voice.stt_available():
    print(f"↓ speech recognition model '{config.WHISPER_MODEL}' …", flush=True)
    voice._model()
    print("✓ speech recognition ready")
