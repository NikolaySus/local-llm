#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_HOST="${REMOTE_HOST:-109.73.203.55}"
REMOTE_SSH_PORT="${REMOTE_SSH_PORT:-22}"
REMOTE_BIND_HOST="${REMOTE_BIND_HOST:-127.0.0.1}"
REMOTE_BIND_PORT="${REMOTE_BIND_PORT:-18000}"
LOCAL_HOST="${LOCAL_HOST:-127.0.0.1}"
LOCAL_PORT="${LOCAL_PORT:-8000}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/local_llm_proxy_ed25519}"

exec autossh -M 0 -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=accept-new \
  -i "$SSH_KEY" \
  -p "$REMOTE_SSH_PORT" \
  -R "${REMOTE_BIND_HOST}:${REMOTE_BIND_PORT}:${LOCAL_HOST}:${LOCAL_PORT}" \
  "${REMOTE_USER}@${REMOTE_HOST}"
