#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"
API_KEY="${API_KEY:-}"

headers=(-H "Content-Type: application/json")
if [[ -n "$API_KEY" ]]; then
  headers+=(-H "Authorization: Bearer $API_KEY")
fi

curl --noproxy '*' -fsS "$BASE_URL/embeddings" \
  "${headers[@]}" \
  --data-binary @- <<'JSON'
{
  "model": "giga-embeddings-instruct",
  "input": "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: What is the capital of Russia?"
}
JSON
