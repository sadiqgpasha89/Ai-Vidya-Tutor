#!/usr/bin/env bash
# One-shot setup on a fresh Linux/macOS machine: Python env, front-end libraries, Ollama model, first admin.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt -r requirements-voice.txt
command -v npm >/dev/null && ./scripts/vendor.sh || echo "Install Node.js and run scripts/vendor.sh to finish the offline libraries."
[ -f .env ] || cp .env.example .env
if command -v ollama >/dev/null; then ./scripts/pull_models.sh; else echo "Install Ollama from https://ollama.com, then run ./scripts/pull_models.sh"; fi
[ -f data/voices/en_GB-cori-medium.onnx ] || .venv/bin/python scripts/pull_voices.py || echo "(voices will download the first time they are used)"
read -rp "Create an administrator account now? (username, blank to skip): " admin
[ -z "$admin" ] || .venv/bin/python scripts/create_admin.py "$admin"
echo "Done. Start with ./run.sh and open http://127.0.0.1:8000"
