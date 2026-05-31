#!/usr/bin/env bash
# Tag and push the app image to a container registry so target devices can
# `docker pull` it (cleaner than shipping 2.5GB tarballs, and the path of least
# resistance on Ubuntu Core's docker snap). Updates become a pull.
#
#   REGISTRY=ghcr.io/youruser ./scripts/push-image.sh           # -> :latest
#   REGISTRY=ghcr.io/youruser TAG=v1 ./scripts/push-image.sh
#
# Authenticate first (e.g. `docker login ghcr.io`).
set -euo pipefail

: "${REGISTRY:?Set REGISTRY, e.g. REGISTRY=ghcr.io/youruser}"
TAG="${TAG:-latest}"
LOCAL="physical-ai-demo:latest"
REMOTE="${REGISTRY}/physical-ai-demo:${TAG}"

if ! docker image inspect "$LOCAL" >/dev/null 2>&1; then
  echo "ERROR: $LOCAL not found. Build it first (docker compose build)." >&2
  exit 1
fi

echo ">> Tagging $LOCAL -> $REMOTE"
docker tag "$LOCAL" "$REMOTE"
echo ">> Pushing..."
docker push "$REMOTE"
echo
echo ">> Done. On a device:  docker pull $REMOTE"
echo "   then set 'image: $REMOTE' in docker-compose.yml (or re-tag locally)."
