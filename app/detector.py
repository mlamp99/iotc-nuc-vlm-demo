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
        return canonicalize(dets)


# Open-vocab synonyms -> the canonical class the safety logic keys off. Lets the
# detector model carry richer prompts (helmet, reflective vest, ...) for better
# recall while keeping counts correct.
CANON = {
    "helmet": "hard hat",
    "safety helmet": "hard hat",
    "construction helmet": "hard hat",
    "hardhat": "hard hat",
    "reflective vest": "safety vest",
    "hi-vis vest": "safety vest",
    "high-visibility vest": "safety vest",
    "hi vis vest": "safety vest",
}


def canonicalize(dets: list[Detection], iou_thresh: float = 0.55) -> list[Detection]:
    """Remap synonym labels to canonical names, then drop duplicate boxes of the
    same canonical label that overlap (the same helmet detected as both
    'hard hat' and 'helmet' becomes one 'hard hat')."""
    for d in dets:
        d.label = CANON.get(d.label, d.label)
    kept: list[Detection] = []
    for d in sorted(dets, key=lambda x: x.confidence, reverse=True):
        if any(k.label == d.label and _iou(k, d) >= iou_thresh for k in kept):
            continue
        kept.append(d)
    return kept


def _iou(a: Detection, b: Detection) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    return inter / float(area_a + area_b - inter)


class Smoother:
    """Temporal smoothing so detections don't flicker on/off frame-to-frame.

    Each frame, new detections are matched to recent ones by class + IoU. A
    recent detection that isn't matched this frame is kept (its box held in
    place) for up to `ttl` frames before being dropped — so an object whose
    confidence dips below the threshold for a frame or two stays visible.
    """

    def __init__(self, ttl: int, iou_thresh: float):
        self.ttl = ttl
        self.iou_thresh = iou_thresh
        self._tracks: list[dict] = []

    def update(self, dets: list[Detection]) -> list[Detection]:
        if self.ttl <= 0:
            return dets
        for t in self._tracks:
            t["matched"] = False
        for d in dets:
            best, best_iou = None, self.iou_thresh
            for t in self._tracks:
                if t["matched"] or t["det"].label != d.label:
                    continue
                i = _iou(d, t["det"])
                if i >= best_iou:
                    best_iou, best = i, t
            if best is not None:
                best["det"], best["ttl"], best["matched"] = d, self.ttl, True
            else:
                self._tracks.append({"det": d, "ttl": self.ttl, "matched": True})
        for t in self._tracks:
            if not t["matched"]:
                t["ttl"] -= 1
        self._tracks = [t for t in self._tracks if t["ttl"] > 0]
        return [t["det"] for t in self._tracks]


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
