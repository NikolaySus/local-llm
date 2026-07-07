#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/local-llm-vllm.service"

mkdir -p "$SERVICE_DIR"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Local vLLM OpenAI-compatible API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/scripts/start-vllm.sh
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=120

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now local-llm-vllm.service

echo "Installed and started $SERVICE_FILE"
