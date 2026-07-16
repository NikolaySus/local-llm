#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLLM_UNIT="local-llm-vllm.service"
EMBEDDING_UNIT="local-llm-embeddings.service"
TUNNEL_UNIT="local-llm-tunnel.service"
REMOTE_PROXY_UNIT="local-llm-proxy.service"
REMOTE_HOST="${REMOTE_HOST:-109.73.203.55}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_SSH_PORT="${REMOTE_SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/local_llm_proxy_ed25519}"
PUBLIC_URL="${PUBLIC_URL:-http://109.73.203.55:8000}"
START_TIMEOUT_SECONDS="${START_TIMEOUT_SECONDS:-900}"

ssh_remote() {
  ssh -i "$SSH_KEY" -p "$REMOTE_SSH_PORT" \
    -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

wait_for_local_health() {
  local deadline=$((SECONDS + START_TIMEOUT_SECONDS))
  until curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 2
  done
}

wait_for_port_release() {
  local deadline=$((SECONDS + 180))
  while ss -ltnH 'sport = :8000' | grep -q .; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for local port 8000 to be released" >&2
      return 1
    fi
    sleep 1
  done
}

show_failure() {
  local unit="$1"
  systemctl --user status --no-pager --lines=30 "$unit" >&2 || true
  journalctl --user -u "$unit" --no-pager -n 50 >&2 || true
}

switch_model() {
  local model="$1"
  local unit
  case "$model" in
    gemma) unit="$VLLM_UNIT" ;;
    embeddings) unit="$EMBEDDING_UNIT" ;;
    *) echo "Usage: $0 switch gemma|embeddings" >&2; exit 2 ;;
  esac

  systemctl --user stop "$VLLM_UNIT" "$EMBEDDING_UNIT" || true
  wait_for_port_release
  systemctl --user start "$unit"
  if ! wait_for_local_health; then
    show_failure "$unit"
    exit 1
  fi

  systemctl --user restart "$TUNNEL_UNIT"
  local tunnel_deadline=$((SECONDS + 60))
  until ssh_remote 'curl -fsS --max-time 3 http://127.0.0.1:18000/health >/dev/null' 2>/dev/null; do
    if (( SECONDS >= tunnel_deadline )); then
      echo "Reverse SSH tunnel did not become ready" >&2
      systemctl --user status --no-pager --lines=30 "$TUNNEL_UNIT" >&2 || true
      exit 1
    fi
    sleep 2
  done
  ssh_remote "systemctl start $REMOTE_PROXY_UNIT"

  local deadline=$((SECONDS + 60))
  until curl --noproxy '*' -fsS --max-time 5 "$PUBLIC_URL/health" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Public proxy did not become reachable" >&2
      exit 1
    fi
    sleep 2
  done

  ssh_remote 'set -a; . /etc/local-llm-proxy.env; curl -fsS --max-time 10 -H "Authorization: Bearer $PUBLIC_API_KEY" http://127.0.0.1:8000/v1/models >/dev/null'
  echo "Active model: $model"
  echo "Public API: $PUBLIC_URL/v1"
}

stop_stack() {
  systemctl --user stop "$VLLM_UNIT" "$EMBEDDING_UNIT" "$TUNNEL_UNIT" || true
  ssh_remote "systemctl stop $REMOTE_PROXY_UNIT"
  systemctl --user reset-failed "$VLLM_UNIT" "$EMBEDDING_UNIT" "$TUNNEL_UNIT" >/dev/null 2>&1 || true
  echo "Local model services, tunnel, and remote proxy are stopped"
}

show_status() {
  echo "Local services:"
  systemctl --user is-active "$VLLM_UNIT" "$EMBEDDING_UNIT" "$TUNNEL_UNIT" || true
  echo "Local enablement:"
  systemctl --user is-enabled "$VLLM_UNIT" "$EMBEDDING_UNIT" "$TUNNEL_UNIT" || true
  echo "Remote proxy:"
  ssh_remote "systemctl is-active $REMOTE_PROXY_UNIT || true; systemctl is-enabled $REMOTE_PROXY_UNIT || true"
  if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:8000/v1/models 2>/dev/null; then
    echo
  fi
}

case "${1:-}" in
  switch)
    [[ $# -eq 2 ]] || { echo "Usage: $0 switch gemma|embeddings" >&2; exit 2; }
    switch_model "$2"
    ;;
  stop)
    [[ $# -eq 1 ]] || { echo "Usage: $0 stop" >&2; exit 2; }
    stop_stack
    ;;
  status)
    [[ $# -eq 1 ]] || { echo "Usage: $0 status" >&2; exit 2; }
    show_status
    ;;
  *)
    echo "Usage: $0 {switch gemma|switch embeddings|stop|status}" >&2
    exit 2
    ;;
esac
