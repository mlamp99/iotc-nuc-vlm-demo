#!/usr/bin/env bash
# Host wrapper: runs the in-container pre-flight self-test.
#   ./selftest.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
docker compose run --rm physical-ai python3 -m app.selftest
