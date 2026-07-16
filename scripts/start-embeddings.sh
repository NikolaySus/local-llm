#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

exec "$ROOT_DIR/embedding_server/.venv/bin/uvicorn" embedding_server.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  --no-access-log

