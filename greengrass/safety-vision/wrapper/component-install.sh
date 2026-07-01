#!/bin/bash
# Greengrass install lifecycle: make the container image available on the device.
#
# The AI workload ships as a prebuilt image (Intel OpenVINO runtime + YOLO/VLM
# models baked in) — far too large and hardware-specific to pip-install into a
# bare venv like the pure-Python reference components. Greengrass only manages
# the lifecycle; the image lives in GHCR.
set -e
set -x

cd "$(dirname "$0")"

# The GHCR package is public, so no docker login is needed.
docker compose -f docker-compose.gg.yml pull

echo "Safety Vision image pull complete."
