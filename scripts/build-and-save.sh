#!/usr/bin/env bash
# Builds the image (with models baked in) and saves it to a tarball you can ship
# to the target device. This is the "be sure it runs" path: it loads the EXACT image you
# tested, rather than rebuilding from source.
#
#   bash scripts/build-and-save.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="physical-ai-demo:latest"
SHIP="$ROOT/ship"
mkdir -p "$SHIP"

if [[ ! -d "$ROOT/models" || -z "$(ls -A "$ROOT/models" 2>/dev/null)" ]]; then
  echo "ERROR: ./models is empty. Run scripts/prepare_models.sh first." >&2
  exit 1
fi

echo ">> Building $IMAGE ..."
docker build -t "$IMAGE" .

echo ">> Saving image tarball (this is large; it contains the models)..."
docker save "$IMAGE" | gzip > "$SHIP/physical-ai-demo.tar.gz"

echo ">> Staging the runtime files the device needs alongside the image..."
cp -f docker-compose.yml "$SHIP/"
cp -f .env.example "$SHIP/"
cp -rf scripts "$SHIP/"
cp -rf core "$SHIP/"
cp -f IOTCONNECT-TEMPLATE.md "$SHIP/"
cp -f README.md "$SHIP/README.md" 2>/dev/null || true

cat > "$SHIP/LOAD-ME.txt" <<'EOF'
1. sudo bash scripts/install-docker.sh     (if Docker isn't installed)
2. sudo bash scripts/host-setup.sh         (Intel GPU/NPU drivers; note the GIDs)
3. docker load < physical-ai-demo.tar.gz
4. cp .env.example .env  and edit RENDER_GID/VIDEO_GID/CAMERA_SOURCE
5. put the credentials folder next to docker-compose.yml
6. docker compose run --rm physical-ai python3 -m app.selftest   (pre-flight)
7. docker compose up
8. open http://<this-nuc-ip>:8080 in a browser
EOF

echo
echo ">> Done. Ship the whole ./ship folder to the target device:"
ls -lh "$SHIP"
echo
echo "   NOTE: ship/ does NOT contain credentials (by design). Send the"
echo "   credentials folder separately/securely."
