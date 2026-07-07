#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_HOST="${REMOTE_HOST:-109.73.203.55}"
REMOTE_SSH_PORT="${REMOTE_SSH_PORT:-22}"
REPO_URL="${REPO_URL:-https://github.com/NikolaySus/local-llm.git}"
REMOTE_DIR="${REMOTE_DIR:-/opt/local-llm}"
PUBLIC_API_KEY="${PUBLIC_API_KEY:?PUBLIC_API_KEY is required}"
UPSTREAM_BASE_URL="${UPSTREAM_BASE_URL:-http://127.0.0.1:18000}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/local_llm_proxy_ed25519}"

ssh -i "$SSH_KEY" -p "$REMOTE_SSH_PORT" -o StrictHostKeyChecking=accept-new "${REMOTE_USER}@${REMOTE_HOST}" \
  "PUBLIC_API_KEY='$PUBLIC_API_KEY' UPSTREAM_BASE_URL='$UPSTREAM_BASE_URL' REPO_URL='$REPO_URL' REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE'
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git python3 python3-venv python3-pip openssh-server
fi

mkdir -p "$(dirname "$REMOTE_DIR")"
if [ -d "$REMOTE_DIR/.git" ]; then
  git -C "$REMOTE_DIR" fetch origin
  git -C "$REMOTE_DIR" reset --hard origin/main
else
  rm -rf "$REMOTE_DIR"
  git clone "$REPO_URL" "$REMOTE_DIR"
fi

python3 -m venv "$REMOTE_DIR/.venv-proxy"
"$REMOTE_DIR/.venv-proxy/bin/pip" install --upgrade pip
"$REMOTE_DIR/.venv-proxy/bin/pip" install -r "$REMOTE_DIR/proxy_server/requirements.txt"

cat > /etc/local-llm-proxy.env <<ENV
PUBLIC_API_KEY=$PUBLIC_API_KEY
UPSTREAM_BASE_URL=$UPSTREAM_BASE_URL
HOST=0.0.0.0
PORT=8000
ENV
chmod 600 /etc/local-llm-proxy.env

if [ -f /etc/ssh/sshd_config ] && ! grep -Eq '^[[:space:]]*AllowTcpForwarding[[:space:]]+yes' /etc/ssh/sshd_config; then
  printf '\nAllowTcpForwarding yes\n' >> /etc/ssh/sshd_config
  systemctl reload ssh || systemctl reload sshd || true
fi

cat > /etc/systemd/system/local-llm-proxy.service <<UNIT
[Unit]
Description=Local LLM public OpenAI-compatible proxy
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REMOTE_DIR
EnvironmentFile=/etc/local-llm-proxy.env
ExecStart=$REMOTE_DIR/.venv-proxy/bin/uvicorn proxy_server.app:app --host \${HOST} --port \${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable local-llm-proxy.service
systemctl restart local-llm-proxy.service
systemctl status --no-pager local-llm-proxy.service
REMOTE
