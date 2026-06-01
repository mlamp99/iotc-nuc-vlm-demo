#!/usr/bin/env bash
# Checks whether an (Ubuntu Core or classic) device is ready to run the demo with
# GPU acceleration. Run on the TARGET device:  bash core/core-readiness.sh
# Read-only; safe to run anytime. Exit 0 if GPU-ready, 1 otherwise.
set -uo pipefail

ok=0; warn=0; fail=0
pass(){ echo "  [PASS] $*"; }
note(){ echo "  [WARN] $*"; warn=$((warn+1)); }
bad(){  echo "  [FAIL] $*"; fail=$((fail+1)); }

echo "=== Core / device readiness ==="

echo "Kernel & devices:"
echo "  kernel: $(uname -r)"
if [ -e /dev/dri/renderD128 ]; then pass "GPU /dev/dri/renderD128 present"; else
  bad "no /dev/dri/renderD128 — kernel lacks Intel GPU driver (see core/CORE-NOTES.md §1)"; fi
if ls /dev/accel/accel* >/dev/null 2>&1; then pass "NPU $(ls /dev/accel/accel* 2>/dev/null) present"; else
  note "no NPU device (optional; GPU/CPU fallback used)"; fi
rg="$(getent group render | cut -d: -f3 2>/dev/null || true)"
[ -n "$rg" ] && pass "render group GID=$rg" || note "no 'render' group found"

echo "Docker:"
if command -v docker >/dev/null 2>&1; then
  pass "docker present: $(docker --version 2>/dev/null)"
  docker compose version >/dev/null 2>&1 && pass "compose plugin present" || note "no 'docker compose' plugin"
else
  bad "docker not found (Ubuntu Core: sudo snap install docker)"
fi

if snap list docker >/dev/null 2>&1; then
  echo "Snap interfaces (docker snap):"
  for iface in home removable-media; do
    if snap connections docker 2>/dev/null | grep -q ":$iface .*docker:$iface"; then
      pass "docker:$iface connected"
    else
      note "docker:$iface not connected (sudo snap connect docker:$iface)"
    fi
  done
fi

echo "GPU-in-container (if image present):"
if docker image inspect ghcr.io/mlamp99/physical-ai-demo:latest >/dev/null 2>&1; then
  devs=$(docker run --rm --device /dev/dri:/dev/dri ${rg:+--group-add $rg} \
           ghcr.io/mlamp99/physical-ai-demo:latest \
           python3 -c "import openvino as ov; print(ov.Core().available_devices)" 2>/dev/null || true)
  echo "    OpenVINO devices in container: ${devs:-<error>}"
  case "$devs" in
    *GPU*) pass "container sees the GPU" ;;
    *) bad "container sees no GPU (driver/passthrough issue)" ;;
  esac
else
  note "image ghcr.io/mlamp99/physical-ai-demo:latest not loaded yet — skipping container GPU test"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo ">> READY (warnings: $warn)"; exit 0
else
  echo ">> NOT READY: $fail blocking issue(s), $warn warning(s)"; exit 1
fi
