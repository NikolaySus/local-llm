#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_PATH="${SERVICE_PATH:-$HOME/.config/systemd/user/local-llm-tunnel.service}"

mkdir -p "$(dirname "$SERVICE_PATH")"
cat > "$SERVICE_PATH" <<UNIT
[Unit]
Description=Local LLM reverse SSH tunnel
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/scripts/start-tunnel.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now local-llm-tunnel.service
systemctl --user status --no-pager local-llm-tunnel.service
