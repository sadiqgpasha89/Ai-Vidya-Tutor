#!/usr/bin/env bash
# Download the local models AIVidya uses (Ollama). Safe to run again: models already present are skipped.
#   ./scripts/pull_models.sh            everyday model + drawing/checking model + search model   (about 16 GB in all)
#   ./scripts/pull_models.sh --small    only the everyday model + search model                    (about 10 GB; pictures use it too)
set -euo pipefail
command -v ollama >/dev/null || { echo "Install Ollama from https://ollama.com first."; exit 1; }
have() { ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$1"; }
models=(gemma4:e4b nomic-embed-text translategemma:4b)
[ "${1:-}" = "--small" ] || models+=(gpt-oss:20b)
for m in "${models[@]}"; do
  if have "$m" || have "$m:latest"; then echo "✓ $m already installed"; else echo "↓ pulling $m"; ollama pull "$m"; fi
done
echo "Done. Everyday jobs (lessons, chat, summaries, cheat sheets, quizzes, photos) use gemma4:e4b; pictures, fact-checking and answer-key tie-breaks use gpt-oss:20b."
