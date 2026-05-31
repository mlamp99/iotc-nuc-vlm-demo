#!/usr/bin/env bash
# Switch the VLM between the fast 2B and the sharper 7B model. Both are baked
# into the image, so this only edits .env and restarts — no rebuild.
#
#   bash scripts/use-vlm.sh 2b   # fast (~5s/answer), auto safety-check every 15s
#   bash scripts/use-vlm.sh 7b   # sharper (~20-30s/answer), spaced every 45s
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[ -f .env ] || cp .env.example .env

case "${1:-}" in
  2b) MODEL=/app/models/qwen2-vl-2b-int4;   INTERVAL=15; TOK=150;;
  7b) MODEL=/app/models/qwen2.5-vl-7b-int4; INTERVAL=45; TOK=100;;
  *)  echo "usage: $(basename "$0") 2b|7b" >&2; exit 1;;
esac

sed -i "s|^VLM_MODEL=.*|VLM_MODEL=$MODEL|"            .env
sed -i "s|^VLM_INTERVAL_S=.*|VLM_INTERVAL_S=$INTERVAL|" .env
sed -i "s|^VLM_MAX_NEW_TOKENS=.*|VLM_MAX_NEW_TOKENS=$TOK|" .env
echo ">> VLM = $MODEL  (interval=${INTERVAL}s, max_tokens=$TOK)"

if docker compose ps >/dev/null 2>&1; then
  echo ">> restarting container to apply..."
  docker compose up -d
  echo ">> done — open http://localhost:8080 (first 7B answer takes ~20-30s)"
else
  echo ">> now run:  docker compose up -d"
fi
