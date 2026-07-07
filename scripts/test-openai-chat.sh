#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"
MODEL="${MODEL:-gemma-4-12b}"

curl --noproxy '*' -sS "$BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{
  "model": "$MODEL",
  "messages": [
    {
      "role": "user",
      "content": "Reply with exactly: local endpoint ok"
    }
  ],
  "max_tokens": 16,
  "temperature": 0
}
JSON
