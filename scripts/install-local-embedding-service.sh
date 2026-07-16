#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/embedding_server"
SERVICE_DIR="$HOME/.config/systemd/user"
CONFIG_DIR="$HOME/.config/local-llm"
SERVICE_FILE="$SERVICE_DIR/local-llm-embeddings.service"
ENV_FILE="$CONFIG_DIR/embeddings.env"
MODEL_ID="ai-sage/Giga-Embeddings-instruct"
MODEL_REVISION="2cf0fdc97194aaedf10ac0e6bf798834acd31042"

mkdir -p "$SERVICE_DIR" "$CONFIG_DIR"

env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  UV_NO_BUILD=1 uv sync --project "$PROJECT_DIR" --frozen --no-build

MODEL_PATH="$(env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  ROOT_DIR="$ROOT_DIR" "$PROJECT_DIR/.venv/bin/python" - <<PY
import os
import shutil

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

try:
    path = snapshot_download(
        repo_id="$MODEL_ID",
        revision="$MODEL_REVISION",
        local_files_only=True,
    )
except LocalEntryNotFoundError:
    free_bytes = shutil.disk_usage(os.environ["ROOT_DIR"]).free
    required_bytes = 16 * 1024**3
    if free_bytes < required_bytes:
        raise SystemExit(
            f"The model is not cached and requires at least 16 GiB free; "
            f"only {free_bytes / 1024**3:.1f} GiB is available"
        )
    path = snapshot_download(repo_id="$MODEL_ID", revision="$MODEL_REVISION")

print(path)
PY
)"

"$PROJECT_DIR/.venv/bin/python" - <<'PY'
import flash_attn
import torch

assert torch.cuda.is_available(), "CUDA is unavailable"
assert torch.compiled_with_cxx11_abi(), "The pinned FlashAttention wheel requires CXX11 ABI"
print(f"Verified flash-attn {flash_attn.__version__} with torch {torch.__version__}")
PY

cat >"$ENV_FILE" <<EOF
GIGA_MODEL_PATH=$MODEL_PATH
GIGA_TORCH_COMPILE=0
GIGA_WARMUP_TOKENS=32,128,512,2048,4096
CUDA_MODULE_LOADING=LAZY
TOKENIZERS_PARALLELISM=false
EOF
chmod 600 "$ENV_FILE"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Local Giga Embeddings OpenAI-compatible API
After=network-online.target
Wants=network-online.target
Conflicts=local-llm-vllm.service

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$ROOT_DIR/scripts/start-embeddings.sh
Restart=on-failure
RestartSec=10
TimeoutStopSec=120

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user disable local-llm-embeddings.service >/dev/null 2>&1 || true

echo "Installed $SERVICE_FILE (disabled; use scripts/model-service.sh switch embeddings)"
