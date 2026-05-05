#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

uv run python scripts/dev-server.py &
BACKEND_PID=$!

cd frontend
npm run dev -- --host 127.0.0.1
