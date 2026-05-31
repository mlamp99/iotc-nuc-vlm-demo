"""Fast-path object detection via Ultralytics YOLO on an OpenVINO-exported model.

Runs every frame at real-time rates. Falls back from the configured Intel
device (GPU/NPU) to CPU so the demo never hard-fails on a driver mismatch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("detector")


@dataclass
class Detection:
    label: str
    confidence: float
    # xyxy pixel coordinates
    x1: int
    y1: int
    x2: int
    y2: int


class Detector:
    def __init__(self, model_path: str, device: str, conf: float):
        # Imported lazily so `--help` / selftest can probe without heavy deps.
        from ultralytics import YOLO

        self.conf = conf
        self.model = YOLO(model_path, task="detect")
        self.device = self._pick_device(device)
        self.names = self.model.names
        log.info("Detector ready: model=%s device=%s", model_path, self.device)

    def _pick_device(self, preferred: str) -> str:
        """Probe the preferred Intel device; fall back NPU->GPU->CPU on error."""
        candidates = [preferred] + [
            d for d in ("intel:gpu", "intel:cpu") if d != preferred
        ]
        dummy = np.zeros((64, 64, 3), dtype=np.uint8)
        for dev in candidates:
            try:
                self.model.predict(dummy, device=dev, verbose=False, conf=0.99)
                if dev != preferred:
                    log.warning("Detector device %s unavailable; using %s", preferred, dev)
                return dev
            except Exception as e:  # noqa: BLE001 - we genuinely want any failure
                log.warning("Detector device %s failed (%s); trying next", dev, e)
        log.error("No working detector device; defaulting to intel:cpu")
        return "intel:cpu"

    def infer(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(
            frame, device=self.device, verbose=False, conf=self.conf
        )
        dets: list[Detection] = []
        if not results:
            return dets
        r = results[0]
        if r.boxes is None:
            return dets
        for box in r.boxes:
            cls_id = int(box.cls[0])
            xyxy = box.xyxy[0].tolist()
            dets.append(
                Detection(
                    label=self.names.get(cls_id, str(cls_id)),
                    confidence=float(box.conf[0]),
                    x1=int(xyxy[0]),
                    y1=int(xyxy[1]),
                    x2=int(xyxy[2]),
                    y2=int(xyxy[3]),
                )
            )
        return dets


def summarize(dets: list[Detection]) -> dict:
    """Compact, telemetry-friendly summary: counts per class + person flag."""
    counts: dict[str, int] = {}
    for d in dets:
        counts[d.label] = counts.get(d.label, 0) + 1
    return {
        "object_count": len(dets),
        "class_counts": counts,
        "person_present": counts.get("person", 0) > 0,
    }
