#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/.venv/bin/activate"

MODEL_PATH="${MODEL_PATH:-$ROOT_DIR/models/gemma-4-12b-it-qat-w4a16-ct}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-gemma-4-12b}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-262144}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.968}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-auto}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-1}"

exec vllm serve "$MODEL_PATH" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --host "$HOST" \
  --port "$PORT" \
  --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --kv-cache-dtype "$KV_CACHE_DTYPE" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --trust-remote-code
