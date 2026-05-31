#!/usr/bin/env bash
# Ubuntu Core bring-up: install the docker snap, connect the interfaces the demo
# needs, and create the working directory for credentials / .env / cache.
#
#   sudo bash core/core-setup.sh
#
# UNTESTED SCAFFOLDING — validate core/core-readiness.sh first. On classic
# Ubuntu use scripts/install-docker.sh + scripts/host-setup.sh instead.
set -euo pipefail

WORKDIR="${CORE_WORKDIR:-${SUDO_USER:+/home/$SUDO_USER}/physical-ai}"
WORKDIR="${WORKDIR:-$HOME/physical-ai}"

echo ">> Installing the docker snap..."
snap install docker || true
snap set docker docker.experimental=false || true

echo ">> Connecting interfaces..."
for iface in home removable-media network-control firewall-control; do
  snap connect "docker:$iface" 2>/dev/null \
    && echo "   connected docker:$iface" \
    || echo "   (docker:$iface not available / already connected)"
done

echo ">> Creating working directory: $WORKDIR"
mkdir -p "$WORKDIR/credentials" "$WORKDIR/.ov_cache"
echo "   Put your IOTCONNECT files in: $WORKDIR/credentials/"
echo "   (optional) copy .env.example there as .env to override defaults."

echo
echo ">> Device check:"
[ -e /dev/dri/renderD128 ] && echo "   GPU /dev/dri/renderD128 present ✓" || echo "   GPU MISSING ✗  (kernel snap lacks Intel GPU driver — see core/CORE-NOTES.md)"
ls /dev/accel/accel* >/dev/null 2>&1 && echo "   NPU present ✓" || echo "   NPU absent (GPU/CPU fallback will be used)"
echo "   render GID: $(getent group render | cut -d: -f3 2>/dev/null || echo '?')"

echo
echo ">> Next:"
echo "   docker load < physical-ai-demo.tar.gz   # or: docker pull <your-registry>/physical-ai-demo"
echo "   CORE_WORKDIR=$WORKDIR docker compose -f docker-compose.yml -f core/docker-compose.core.yml up -d"
