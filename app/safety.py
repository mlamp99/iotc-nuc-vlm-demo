"""Turns raw detections into the construction-safety telemetry the dashboard
cares about: per-class counts, PPE compliance, machine danger-zone proximity,
and a composed safety alert.

All of this is heuristic and tuned for a demo, not a certified safety system —
the class names below must match the YOLO-World classes baked into the detector
model (see scripts/prepare_models.sh / CONSTRUCTION_CLASSES).
"""
from __future__ import annotations

from app.detector import Detection

# Classes treated as heavy machinery for danger-zone proximity.
EQUIPMENT_CLASSES = {
    "excavator", "dump truck", "wheel loader", "bulldozer", "loader", "machinery",
}


def _boxes_near(p: Detection, e: Detection, mx: float, my: float) -> bool:
    """True if person box p intersects equipment box e expanded by (mx,my)."""
    ex1, ey1, ex2, ey2 = e.x1 - mx, e.y1 - my, e.x2 + mx, e.y2 + my
    return p.x1 < ex2 and p.x2 > ex1 and p.y1 < ey2 and p.y2 > ey1


def analyze(dets: list[Detection], frame_w: int, frame_h: int, danger_margin: float) -> dict:
    counts: dict[str, int] = {}
    persons: list[Detection] = []
    equipment: list[Detection] = []
    for d in dets:
        counts[d.label] = counts.get(d.label, 0) + 1
        if d.label == "person":
            persons.append(d)
        if d.label in EQUIPMENT_CLASSES:
            equipment.append(d)

    person_count = len(persons)
    hardhat_count = counts.get("hard hat", 0)
    vest_count = counts.get("safety vest", 0)
    cone_count = counts.get("traffic cone", 0)
    # Any heavy machinery counts (excavator, dump truck, wheel loader, ...) —
    # the attribute keeps its historical name so existing /IOTCONNECT templates
    # and dashboards don't need to change.
    excavator_present = len(equipment) > 0
    # Heuristic: workers not matched to a hard hat.
    no_hardhat_count = max(0, person_count - hardhat_count)
    ppe_compliant = person_count == 0 or hardhat_count >= person_count

    mx = danger_margin * frame_w
    my = danger_margin * frame_h
    person_in_danger_zone = any(
        _boxes_near(p, e, mx, my) for p in persons for e in equipment
    )

    alerts: list[str] = []
    if no_hardhat_count > 0:
        alerts.append(f"{no_hardhat_count} worker(s) without hard hat")
    if person_in_danger_zone:
        alerts.append("worker in machine danger zone")
    safety_alert = "; ".join(alerts) if alerts else "clear"

    return {
        "object_count": len(dets),
        "class_counts": counts,
        "person_count": person_count,
        "person_present": person_count > 0,
        "hardhat_count": hardhat_count,
        "no_hardhat_count": no_hardhat_count,
        "vest_count": vest_count,
        "cone_count": cone_count,
        "excavator_present": excavator_present,
        "ppe_compliant": ppe_compliant,
        "person_in_danger_zone": person_in_danger_zone,
        "safety_alert": safety_alert,
    }


EMPTY = {
    "object_count": 0, "class_counts": {}, "person_count": 0, "person_present": False,
    "hardhat_count": 0, "no_hardhat_count": 0, "vest_count": 0, "cone_count": 0,
    "excavator_present": False, "ppe_compliant": True, "person_in_danger_zone": False,
    "safety_alert": "clear",
}
