# Local Gemma 4 12B Endpoint

This project serves Gemma 4 12B locally through a vLLM OpenAI-compatible API.

The default target is the vLLM-optimized QAT checkpoint:

```text
google/gemma-4-12B-it-qat-w4a16-ct
```

It is stored locally under:

```text
models/gemma-4-12b-it-qat-w4a16-ct
```

## Setup

The current environment was created with:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -U vllm --pre \
  --extra-index-url https://wheels.vllm.ai/nightly/cu129 \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  --index-strategy unsafe-best-match
```

No Docker is used.

If Hugging Face downloads fail because `ALL_PROXY=socks://...` is set, normalize it for the command:

```bash
ALL_PROXY=http://127.0.0.1:12334/ all_proxy=http://127.0.0.1:12334/ hf download ...
```

## Start Server

```bash
./scripts/start-vllm.sh
```

Default endpoint:

```text
http://127.0.0.1:8000/v1
```

Default long-context settings:

```text
MAX_MODEL_LEN=262144
GPU_MEMORY_UTILIZATION=0.968
MAX_NUM_SEQS=1
KV_CACHE_DTYPE=auto
```

The `MAX_NUM_SEQS=1` default prioritizes one very long request over concurrency. In testing, `GPU_MEMORY_UTILIZATION=0.969` failed the vLLM startup memory guard on the RTX 4500 Ada desktop session, while `0.968` started successfully.

Useful overrides:

```bash
MAX_MODEL_LEN=16384 ./scripts/start-vllm.sh
KV_CACHE_DTYPE=fp8 ./scripts/start-vllm.sh
GPU_MEMORY_UTILIZATION=0.95 ./scripts/start-vllm.sh
MAX_NUM_SEQS=2 ./scripts/start-vllm.sh
```

## Test Endpoint

```bash
./scripts/test-openai-chat.sh
```

The test sends an OpenAI-style `/v1/chat/completions` request using the served model name `gemma-4-12b`.

If shell proxy variables are set, use `--noproxy '*'` for localhost curl calls.
