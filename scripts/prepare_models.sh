#!/usr/bin/env bash
# Downloads + converts the models into ./models as OpenVINO IR (INT4 VLM +
# OpenVINO-exported YOLO). Runs ENTIRELY inside a Python 3.11 container, so it
# needs no host Python/pip and is reproducible. Run ONCE on your NUC 16 (online):
#
#   newgrp docker            # if `docker` still says permission denied
#   bash scripts/prepare_models.sh
#
# The resulting ./models dir is then baked into the app image (build-and-save.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODELS="$ROOT/models"
mkdir -p "$MODELS"

VLM_ID="${VLM_ID:-Qwen/Qwen2-VL-2B-Instruct}"
VLM_DIR="qwen2-vl-2b-int4"
# Larger VLM for sharper scene reasoning (opt-in via VLM_MODEL in .env). Built
# alongside the 2B by default; set BUILD_VLM_7B=0 to skip and save ~6GB.
VLM7B_ID="${VLM7B_ID:-Qwen/Qwen2.5-VL-7B-Instruct}"
VLM7B_DIR="qwen2.5-vl-7b-int4"
BUILD_VLM_7B="${BUILD_VLM_7B:-1}"
YOLO_ID="${YOLO_ID:-yolo11n.pt}"
# Open-vocabulary construction classes baked into the YOLO-World detector at
# export time. Edit this list (or set CONSTRUCTION_CLASSES) and re-run to change
# what the detector can see. Keep "person", "hard hat", "safety vest",
# "excavator" — the safety logic in app/safety.py keys off those names.
CONSTRUCTION_CLASSES="${CONSTRUCTION_CLASSES:-person,excavator,dump truck,wheel loader,hard hat,safety vest,traffic cone,barrier}"
PREP_IMG="physical-ai-prep:latest"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: cannot reach Docker. Run 'newgrp docker' (or log out/in) first." >&2
  exit 1
fi

echo ">> Building conversion image (one-time, ~a few minutes)..."
docker build -f Dockerfile.prepare -t "$PREP_IMG" .

echo ">> Converting models inside the container -> ./models"
# Run as the current user so output files are owned by you, not root.
# HOME=/out keeps the HuggingFace download cache inside the mounted volume.
docker run --rm \
  -u "$(id -u):$(id -g)" \
  -e HOME=/out \
  -e USER=prep -e LOGNAME=prep \
  -v "$MODELS:/out" \
  "$PREP_IMG" "
    set -e
    if [ -d /out/${VLM_DIR} ]; then
      echo '   VLM already converted; skipping.'
    else
      echo '   Exporting VLM -> OpenVINO INT4: ${VLM_ID}'
      optimum-cli export openvino --model '${VLM_ID}' --weight-format int4 --trust-remote-code /out/${VLM_DIR}
    fi
    if [ '${BUILD_VLM_7B}' = '1' ]; then
      if [ -d /out/${VLM7B_DIR} ]; then
        echo '   7B VLM already converted; skipping.'
      else
        echo '   Exporting 7B VLM -> OpenVINO INT4 (large): ${VLM7B_ID}'
        optimum-cli export openvino --model '${VLM7B_ID}' --weight-format int4 --trust-remote-code /out/${VLM7B_DIR}
      fi
    fi
    if [ -d /out/yolo11n_openvino_model ]; then
      echo '   COCO detector already exported; skipping.'
    else
      echo '   Exporting COCO fallback detector -> OpenVINO: ${YOLO_ID}'
      cd /out && yolo export model='${YOLO_ID}' format=openvino
    fi
    if [ -d /out/construction_openvino_model ]; then
      echo '   Construction (YOLO-World) detector already exported; skipping.'
    else
      echo '   Exporting YOLO-World construction detector -> OpenVINO'
      cd /out && python3 - <<'PY'
import shutil
from ultralytics import YOLOWorld
classes = [c.strip() for c in '''${CONSTRUCTION_CLASSES}'''.split(',') if c.strip()]
print('   classes:', classes)
m = YOLOWorld('yolov8s-worldv2.pt')
m.set_classes(classes)
out = m.export(format='openvino').rstrip('/')
shutil.rmtree('/out/construction_openvino_model', ignore_errors=True)
shutil.move(out, '/out/construction_openvino_model')
with open('/out/construction_openvino_model/classes.txt', 'w') as f:
    f.write('\n'.join(classes))
PY
    fi
  "

echo
echo ">> Models ready under $MODELS:"
ls -1 "$MODELS"
echo ">> Next:  bash scripts/build-and-save.sh   (or: docker compose build && ./selftest.sh)"
