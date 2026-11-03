#!/usr/bin/env bash
# Start AIVidya.   ./run.sh                    local model via Ollama (see .env.example)
#                TEACHER_MOCK=1 ./run.sh     demo with sample content, no model needed
#                TEACHER_AUTH=off ./run.sh   single-person mode: no accounts or passwords
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: creating the Python environment (a few minutes)…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/pip install -q -r requirements-voice.txt || echo "(voice packages not installed - browser voices will still work)"
fi
if [ ! -f frontend/vendor/marked.min.js ]; then
  if command -v npm >/dev/null; then ./scripts/vendor.sh || echo "(could not download front-end libraries)"; else echo "npm not found: install Node.js once, or run scripts/vendor.sh later"; fi
fi
exec .venv/bin/uvicorn backend.app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" "$@"
