#!/usr/bin/env bash
# Push the app image to a container registry so devices can `docker compose pull`
# it (no build, no tarball). The image is named after docker-compose.yml's
# `image:` (default ghcr.io/mlamp99/physical-ai-demo:latest).
#
#   ./scripts/push-image.sh                                   # push as-is
#   REGISTRY=ghcr.io/youruser ./scripts/push-image.sh         # retag -> your registry
#   REGISTRY=ghcr.io/youruser TAG=v1 ./scripts/push-image.sh
#
# Authenticate first (e.g. `docker login ghcr.io`). Build it first with
# `docker compose build` (or scripts/build-and-save.sh).
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/mlamp99/physical-ai-demo:latest}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "ERROR: $IMAGE not found locally. Build it first: docker compose build" >&2
  exit 1
fi

if [ -n "${REGISTRY:-}" ]; then
  TARGET="${REGISTRY}/physical-ai-demo:${TAG:-latest}"
  echo ">> Tagging $IMAGE -> $TARGET"
  docker tag "$IMAGE" "$TARGET"
else
  TARGET="$IMAGE"
fi

echo ">> Pushing $TARGET ..."
docker push "$TARGET"
echo
echo ">> Done. On a device:  docker compose pull   (with image: $TARGET in docker-compose.yml)"
