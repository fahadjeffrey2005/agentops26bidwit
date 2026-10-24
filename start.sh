#!/usr/bin/env bash
# Start BidWit locally: API on 127.0.0.1:8000, UI on 127.0.0.1:5174. Ctrl+C stops both.
#   ./start.sh            # first run installs what's missing (Python venv, UI packages)
# Optional: export GROQ_API_KEY=... before running, for the AI parts (without it they fall back to rules / gaps).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

PY="${PYTHON:-python3.13}"
command -v "$PY" >/dev/null || PY=python3
command -v node >/dev/null || { echo "Node.js is needed for the UI (brew install node)"; exit 1; }

if [ ! -x "$ROOT/backend/.venv/bin/python" ]; then
  echo "Creating the Python environment (first run only)..."
  "$PY" -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/python" -m pip install -q --require-hashes -r "$ROOT/backend/requirements.txt"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing the UI packages (first run only)..."
  (cd "$ROOT/frontend" && npm ci --silent)
fi

if [ -n "${GROQ_API_KEY:-}" ]; then echo "AI: on (Groq key set)"; else echo "AI: off (no GROQ_API_KEY): rules and flagged gaps only"; fi

KEEP_AWAKE=()
command -v caffeinate >/dev/null && KEEP_AWAKE=(caffeinate -dims)   # macOS: don't sleep mid-run

cleanup() { kill "${API_PID:-}" "${UI_PID:-}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && exec "${KEEP_AWAKE[@]}" .venv/bin/uvicorn bidwit.api:app --host 127.0.0.1 --port 8000 --log-level warning) &
API_PID=$!
(cd "$ROOT/frontend" && exec npx vite --logLevel warn) &
UI_PID=$!

for _ in $(seq 1 40); do
  curl -s -o /dev/null http://127.0.0.1:8000/api/health && curl -s -o /dev/null http://127.0.0.1:5174/ && break
  sleep 0.5
done
echo "BidWit is running: http://127.0.0.1:5174   (Ctrl+C to stop)"
[ "$(uname)" = "Darwin" ] && open "http://127.0.0.1:5174" || true
wait
