# Local Gemma and Giga Embeddings Endpoint

This repository contains a mutually exclusive pair of local GPU services and a public proxy:

- vLLM serving Gemma 4 12B chat completions;
- a Transformers/FlashAttention 2 server serving Giga Embeddings;
- a Python proxy on the VPS forwarding OpenAI-compatible requests through a reverse SSH tunnel.

Only one GPU model runs at a time. Both use local port `8000`, so the tunnel and public URL do not change when switching models.

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

No Docker is used. The vLLM and embedding environments are independent because they require different Torch and Transformers versions.

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
GPU_MEMORY_UTILIZATION=0.94
MAX_NUM_SEQS=1
KV_CACHE_DTYPE=auto
```

The `MAX_NUM_SEQS=1` default prioritizes one very long request over concurrency. `GPU_MEMORY_UTILIZATION=0.94` leaves runtime headroom on the RTX 4500 Ada while still fitting the full `262144` token context. FlashInfer top-p/top-k sampling is disabled by default to avoid local CUDA kernel compilation.

To install vLLM as a user systemd service:

```bash
./scripts/install-local-vllm-service.sh
```

The service is named:

```text
local-llm-vllm.service
```

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

## Giga Embeddings Setup

The embedding server uses `ai-sage/Giga-Embeddings-instruct` at pinned revision:

```text
2cf0fdc97194aaedf10ac0e6bf798834acd31042
```

Install its isolated environment and user service:

```bash
./scripts/install-local-embedding-service.sh
```

The dependency project is under `embedding_server/`. It pins Python 3.12, Torch 2.9.1 with CUDA 12.9, Transformers 4.51.0, and the official prebuilt FlashAttention 2.8.3 Linux wheel. Installation uses `uv --no-build`; it fails instead of compiling FlashAttention locally.

The service is named `local-llm-embeddings.service` and serves:

```text
POST /v1/embeddings
model: giga-embeddings-instruct
dimensions: 2048
maximum input: 4096 tokens
```

Inputs longer than 4096 tokens are rejected rather than truncated. Query instructions are explicit in the input:

```text
Instruct: Given a web search query, retrieve relevant passages that answer the query
Query: What is the capital of Russia?
```

Documents are passed without an instruction. Run a local smoke test with:

```bash
./scripts/test-openai-embeddings.sh
```

On the RTX 4500 Ada, measured warm batch-one latency with BF16 and FlashAttention 2 was approximately 31 ms at 32-128 tokens, 48 ms at 512, 205 ms at 2048, and 469 ms at 4096. Full-model `torch.compile` is available through `GIGA_TORCH_COMPILE=1`, but remains disabled because it regressed the shortest-input latency and did not improve every tested length by the required 10%.

## Model and Stack Control

The services remain disabled at boot and login. Use one command to select a model and start the complete local/tunnel/VPS stack:

```bash
./scripts/model-service.sh switch gemma
./scripts/model-service.sh switch embeddings
```

The switch waits for local model readiness, restarts and verifies the reverse tunnel, starts the remote proxy, and checks the routed model list. Other operations:

```bash
./scripts/model-service.sh status
./scripts/model-service.sh stop
```

## Public Proxy Architecture

Traffic flow:

```text
client -> http://109.73.203.55:8000/v1/... -> VPS Python proxy -> 127.0.0.1:18000 on VPS -> reverse SSH tunnel -> selected local model on 127.0.0.1:8000/v1/...
```

The VPS proxy is plain HTTP and requires:

```text
Authorization: Bearer <PUBLIC_API_KEY>
```

## First-Time SSH Key Setup

Create and install a dedicated SSH key for the reverse tunnel:

```bash
VPS_PASSWORD='<password>' ./scripts/install-vps-ssh-key.py
```

The private key stays on this machine at:

```text
~/.ssh/local_llm_proxy_ed25519
```

## Deploy VPS Proxy

Generate a strong API key locally and deploy the remote service:

```bash
PUBLIC_API_KEY="$(openssl rand -hex 32)" ./scripts/deploy-remote-proxy.sh
```

The deploy script clones this repository to:

```text
/opt/local-llm
```

It installs and starts:

```text
local-llm-proxy.service
```

Remote proxy health:

```bash
curl http://109.73.203.55:8000/health
```

Authenticated model list:

```bash
curl http://109.73.203.55:8000/v1/models \
  -H "Authorization: Bearer $PUBLIC_API_KEY"
```

## Start Reverse SSH Tunnel

After local vLLM is running, start the reverse tunnel:

```bash
./scripts/start-tunnel.sh
```

To install the tunnel as a user systemd service:

```bash
./scripts/install-local-tunnel-service.sh
```

The tunnel publishes local vLLM to the VPS loopback only:

```text
127.0.0.1:18000 on VPS -> 127.0.0.1:8000 on this machine
```

The public port is owned by the Python proxy, not by SSH.
