#!/usr/bin/env bash
# Installs the Intel GPU + NPU *host* drivers needed for accelerated inference,
# then prints the device group IDs you must put in .env.
# Run on BOTH machines:  sudo bash scripts/host-setup.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo bash scripts/host-setup.sh" >&2
  exit 1
fi

echo ">> Installing Intel GPU user-space + firmware..."
apt-get update
apt-get install -y \
  intel-opencl-icd \
  intel-media-va-driver-non-free \
  libze1 \
  clinfo || echo "WARN: some GPU packages unavailable on this release; check Intel docs."

echo
echo ">> Intel NPU (AI Boost) note:"
echo "   The NPU *user-space* driver is bundled INSIDE the container image, so you"
echo "   don't install it here. The host only needs the kernel 'intel_vpu' driver"
echo "   (present on recent Ubuntu) exposing /dev/accel. If /dev/accel is missing,"
echo "   update the kernel. The demo falls back NPU->GPU->CPU if it's absent."
echo

echo ">> Device check:"
if [[ -e /dev/dri/renderD128 ]]; then
  echo "   GPU  /dev/dri/renderD128  present ✓"
else
  echo "   GPU  /dev/dri/renderD128  MISSING ✗"
fi
if ls /dev/accel/accel* >/dev/null 2>&1; then
  echo "   NPU  $(ls /dev/accel/accel*)  present ✓"
else
  echo "   NPU  /dev/accel/accel0   MISSING (GPU/CPU fallback will be used)"
fi

echo
echo ">> Put these GIDs in your .env:"
render_gid="$(getent group render | cut -d: -f3 || true)"
video_gid="$(getent group video | cut -d: -f3 || true)"
echo "   RENDER_GID=${render_gid:-<not found>}"
echo "   VIDEO_GID=${video_gid:-44}"
echo
echo ">> Done. Re-run after a reboot if you just installed the NPU driver."
