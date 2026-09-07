#!/usr/bin/env bash
# Runs backend + frontend together.
#
#   ./run_dev.sh          dev mode: Flask on :5000 + Vite on :5173 (hot reload)
#   ./run_dev.sh prod     builds the frontend once, then runs Flask alone on
#                         :5000 serving the built assets (single process/port)
#
# Ctrl+C stops everything it started.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
MODE="${1:-dev}"

if [ ! -d venv ]; then
  echo "==> Creating Python virtualenv"
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install -q -r requirements.txt

if [ ! -d frontend/node_modules ]; then
  echo "==> Installing frontend dependencies"
  (cd frontend && npm install)
fi

PIDS=()
cleanup() {
  echo ""
  echo "==> Stopping"
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  # Flask's debug reloader and `npm run dev` both spawn a child process
  # that a plain `kill` on the parent PID won't reach -- clear the actual
  # ports as a safety net so nothing is left holding 5000/5173.
  for port in 5000 5173; do
    lsof -ti:"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

if [ "$MODE" = "prod" ]; then
  echo "==> Building frontend"
  (cd frontend && npm run build)
  echo "==> Serving on http://127.0.0.1:5000"
  python run.py &
  PIDS+=($!)
  wait
else
  echo "==> Backend on http://127.0.0.1:5000"
  python run.py &
  PIDS+=($!)

  echo "==> Frontend on http://localhost:5173 (proxies /api to the backend)"
  (cd frontend && npm run dev) &
  PIDS+=($!)

  wait
fi
