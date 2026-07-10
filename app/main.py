"""Physical AI edge demo — orchestrator.

Three concurrent activities:
  * Capture+detect loop (main thread): real-time YOLO over the camera feed,
    draws overlays, publishes frames to the MJPEG viewer.
  * VLM worker (thread): runs the heavy vision-language model on the latest
    frame, either on a timer or when triggered by a cloud command. Never blocks
    detection.
  * Telemetry worker (thread): pushes detections + the latest VLM scene
    description + device/perf health to IOTCONNECT on an interval.

Cloud-to-device commands (from IOTCONNECT):
  * ask-vlm <free text question>   -> runs the VLM now with that prompt
  * set-prompt <free text>         -> changes the recurring VLM prompt
  * capture                        -> runs the VLM now with the default prompt
  * set-vlm <2b|7b|path>           -> hot-swap the VLM model at runtime
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time

import cv2

from app.config import CONFIG
from app import credentials, safety
from app.sysmon import SysMon
from app.location import Location
from app.detector import Detector, Smoother
from app.iotc import IotcClient
from app.viewer import MjpegServer
from app.vlm import VlmManager

logging.basicConfig(
    level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")


class SharedState:
    """Thread-safe bag of the latest frame, detections and VLM output."""

    def __init__(self):
        self._lock = threading.Lock()
        self.frame = None
        self.analysis: dict = dict(safety.EMPTY)
        self.vlm_text: str = "(starting up)"
        self.vlm_prompt: str = CONFIG.vlm_default_prompt
        self.hazard_detected: bool = False
        self.fps: float = 0.0
        self.vlm_latency_s: float = 0.0
        self.vlm_model_name: str = "?"
        self.requested_vlm: str | None = None
        self.vlm_trigger = threading.Event()
        self.stop = threading.Event()

    def request_vlm(self, name: str):
        with self._lock:
            self.requested_vlm = name
        self.vlm_trigger.set()

    def pop_requested_vlm(self):
        with self._lock:
            r = self.requested_vlm
            self.requested_vlm = None
            return r

    def set_frame(self, frame, analysis, fps):
        with self._lock:
            self.frame = frame
            self.analysis = analysis
            self.fps = fps

    def get_frame(self):
        with self._lock:
            return None if self.frame is None else self.frame.copy()

    def set_vlm_text(self, text: str):
        with self._lock:
            self.vlm_text = text

    def snapshot(self) -> dict:
        with self._lock:
            a = self.analysis
            return {
                "fps": round(self.fps, 1),
                "object_count": a["object_count"],
                "person_count": a["person_count"],
                "person_present": a["person_present"],
                "hardhat_count": a["hardhat_count"],
                "no_hardhat_count": a["no_hardhat_count"],
                "vest_count": a["vest_count"],
                "cone_count": a["cone_count"],
                "excavator_present": a["excavator_present"],
                "ppe_compliant": a["ppe_compliant"],
                "person_in_danger_zone": a["person_in_danger_zone"],
                "safety_alert": a["safety_alert"],
                "class_counts": dict(a["class_counts"]),
                "hazard_detected": self.hazard_detected,
                "vlm_model": self.vlm_model_name,
                "vlm_latency_s": self.vlm_latency_s,
                "vlm_scene": self.vlm_text,
            }


def _open_capture(arg):
    cap = cv2.VideoCapture(arg)
    # Request MJPG: many USB webcams only deliver high FPS in MJPG mode and drop
    # to ~5 FPS sending raw/uncompressed frames at 720p. Harmless if unsupported.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG.frame_height)
    # UVC settings are volatile (lost on camera power cycle), so re-apply the
    # configured framing on every open instead of relying on v4l2-ctl.
    if CONFIG.camera_zoom:
        cap.set(cv2.CAP_PROP_ZOOM, CONFIG.camera_zoom)
    if CONFIG.camera_pan:
        cap.set(cv2.CAP_PROP_PAN, CONFIG.camera_pan)
    if CONFIG.camera_tilt:
        cap.set(cv2.CAP_PROP_TILT, CONFIG.camera_tilt)
    return cap


def _autodetect_camera():
    """Find the first /dev/videoN that actually delivers a frame. Survives USB
    cameras whose index shifts across reboots/replugs (esp. multi-node cameras
    like the Logitech BRIO that expose several /dev/video* nodes)."""
    import glob
    indices = sorted(
        int(os.path.basename(p)[5:])
        for p in glob.glob("/dev/video*")
        if os.path.basename(p)[5:].isdigit()
    ) or list(range(10))
    for idx in indices:
        cap = _open_capture(idx)
        if cap.isOpened():
            # The first frame after the MJPG mode switch can take a moment on
            # some cameras (e.g. the BRIO) — retry briefly before rejecting the
            # node, or a single slow frame kills the app into a restart loop.
            for _ in range(10):
                ok, _ = cap.read()
                if ok:
                    log.info("Auto-selected camera at /dev/video%d", idx)
                    return cap
                time.sleep(0.2)
        cap.release()
    raise RuntimeError(f"No working camera found (scanned {indices})")


def open_camera():
    src = (CONFIG.camera_source or "").strip()
    if src.lower() in ("", "auto"):
        return _autodetect_camera()
    cap = _open_capture(int(src) if src.isdigit() else src)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera source {src!r}")
    return cap


def draw_overlay(frame, dets, analysis, fps, vlm_text):
    # OVERLAY_SCALE grows all burned-in text (banner, labels, VLM line) so the
    # stream stays readable when embedded small, e.g. in a dashboard widget.
    s = max(0.5, CONFIG.overlay_scale)
    th = max(1, round(s))
    for d in dets:
        if d.label == "person":
            color = (0, 0, 255)
        elif d.label in safety.EQUIPMENT_CLASSES:
            color = (0, 165, 255)  # orange for machinery
        else:
            color = (0, 200, 0)
        cv2.rectangle(frame, (d.x1, d.y1), (d.x2, d.y2), color, 2)
        cv2.putText(
            frame, f"{d.label} {d.confidence:.2f}", (d.x1, max(0, d.y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5 * s, color, th, cv2.LINE_AA,
        )
    alert = analysis["safety_alert"]
    danger = alert != "clear" or analysis["person_in_danger_zone"]
    banner = f"FPS {fps:4.1f} | persons {analysis['person_count']} | SAFETY: {alert.upper()}"
    bar_color = (0, 0, 200) if danger else (0, 0, 0)
    cv2.rectangle(frame, (0, 0), (frame.shape[1], int(28 * s)), bar_color, -1)
    cv2.putText(frame, banner, (8, int(20 * s)), cv2.FONT_HERSHEY_SIMPLEX,
                0.6 * s, (255, 255, 255), th, cv2.LINE_AA)
    # VLM scene text along the bottom (fewer chars fit as the font grows).
    text = (vlm_text or "")[: int(160 / s)]
    cv2.rectangle(frame, (0, frame.shape[0] - int(26 * s)), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
    cv2.putText(frame, text, (8, frame.shape[0] - int(8 * s)), cv2.FONT_HERSHEY_SIMPLEX,
                0.5 * s, (0, 255, 255), th, cv2.LINE_AA)
    return frame


def vlm_worker(state: SharedState, vlm: VlmManager):
    last_run = 0.0
    state.vlm_model_name = vlm.name
    while not state.stop.is_set():
        triggered = state.vlm_trigger.wait(timeout=0.5)
        # Handle a model hot-swap request (from the set-vlm cloud command).
        req = state.pop_requested_vlm()
        if req:
            state.set_vlm_text(f"(loading {req} model...)")
            try:
                vlm.load(req)
                state.vlm_model_name = vlm.name
                state.set_vlm_text(f"(switched to {vlm.name})")
                log.info("VLM switched to %s", vlm.name)
            except Exception:  # noqa: BLE001
                log.exception("VLM switch to %r failed", req)
                state.set_vlm_text(f"(failed to load {req}; keeping {vlm.name})")
            continue
        now = time.monotonic()
        due = CONFIG.vlm_interval_s > 0 and (now - last_run) >= CONFIG.vlm_interval_s
        if not (triggered or due):
            continue
        state.vlm_trigger.clear()
        frame = state.get_frame()
        if frame is None:
            continue
        # Downscale for the VLM (cost scales with pixels; detector keeps full res).
        m = CONFIG.vlm_max_side
        if m > 0:
            h, w = frame.shape[:2]
            if max(h, w) > m:
                s = m / float(max(h, w))
                frame = cv2.resize(frame, (int(w * s), int(h * s)))
        try:
            t0 = time.monotonic()
            text = vlm.describe(frame, state.vlm_prompt)
            latency = time.monotonic() - t0
            state.vlm_latency_s = round(latency, 2)
            log.info("VLM (%.1fs): %s", latency, text)
            state.set_vlm_text(text)
            # Only update the hazard flag when the response is a structured
            # safety check (so an ad-hoc user question doesn't clear it).
            low = text.lower()
            if "hazard:" in low:
                state.hazard_detected = "hazard: yes" in low
        except Exception:  # noqa: BLE001
            log.exception("VLM inference failed")
        last_run = time.monotonic()


def telemetry_worker(state: SharedState, iotc: IotcClient, vlm: VlmManager, det_device: str):
    sysmon = SysMon()
    location = Location(CONFIG.device_lat, CONFIG.device_lon, CONFIG.geo_autodetect)
    while not state.stop.is_set():
        data = state.snapshot()
        data["vlm_device"] = vlm.device_used
        data["detector_device"] = det_device
        data["cloud_connected"] = iotc.is_connected()
        data.update(sysmon.read())  # cpu/mem/temp/gpu/npu hardware metrics
        if location.value:
            data["location"] = location.value  # LATLONG "lat,lon"
        # /IOTCONNECT: send booleans as lowercase strings ("true"/"false") so the
        # value is deterministic for template attributes and dashboard transforms
        # (Python bools otherwise arrive capitalized as "True"/"False").
        data = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in data.items()}
        iotc.send_telemetry(data)
        state.stop.wait(CONFIG.telemetry_interval_s)


def make_command_handler(state: SharedState):
    def handle(name: str, args: list[str]) -> str:
        cmd = (name or "").strip().lower()
        arg_text = " ".join(str(a) for a in args).strip()
        if cmd == "ask-vlm":
            if arg_text:
                state.vlm_prompt = arg_text
            state.vlm_trigger.set()
            return f"running VLM with prompt: {state.vlm_prompt[:60]}"
        if cmd == "set-prompt":
            state.vlm_prompt = arg_text or state.vlm_prompt
            return "recurring VLM prompt updated"
        if cmd == "capture":
            state.vlm_prompt = CONFIG.vlm_default_prompt
            state.vlm_trigger.set()
            return "captured; running VLM"
        if cmd in ("set-vlm", "use-vlm"):
            target = (arg_text or "2b").strip()
            state.request_vlm(target)
            return f"switching VLM to {target} (takes ~10-30s)"
        return f"unknown command: {name}"

    return handle


def main():
    state = SharedState()

    def _sig(*_):
        log.info("Shutting down...")
        state.stop.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    log.info("Loading detector...")
    detector = Detector(CONFIG.detector_model, CONFIG.detector_device, CONFIG.detector_conf)
    smoother = Smoother(CONFIG.detector_smooth_ttl, CONFIG.detector_smooth_iou)
    log.info("Loading VLM (this can take a moment)...")
    vlm = VlmManager(
        CONFIG.vlm_model, CONFIG.vlm_device, CONFIG.vlm_max_new_tokens,
        aliases={"2b": CONFIG.vlm_model_2b, "7b": CONFIG.vlm_model_7b},
    )

    cfg_json, cert, pkey = credentials.resolve(
        CONFIG.iotc_credentials_dir, CONFIG.iotc_config_json, CONFIG.iotc_cert, CONFIG.iotc_pkey
    )
    iotc = IotcClient(
        config_json=cfg_json,
        cert_path=cert,
        pkey_path=pkey,
        enabled=CONFIG.iotc_enabled,
        command_handler=make_command_handler(state),
        transport=CONFIG.iotc_transport,
    )

    def web_ask(question: str):
        q = (question or "").strip()
        if q:
            state.vlm_prompt = q
            state.vlm_trigger.set()

    viewer = None
    if CONFIG.mjpeg_enabled:
        viewer = MjpegServer(CONFIG.mjpeg_port)
        viewer.start(ask_cb=web_ask, answer_cb=lambda: state.vlm_text,
                     top_pad=CONFIG.viewer_top_pad)

    threading.Thread(target=vlm_worker, args=(state, vlm), daemon=True).start()
    threading.Thread(
        target=telemetry_worker, args=(state, iotc, vlm, detector.device), daemon=True
    ).start()

    if CONFIG.hazard_actions_enabled and CONFIG.hazard_light_duid:
        from app.hazard_actions import HazardActions
        HazardActions(
            state,
            mcp_url=CONFIG.mcp_url,
            duid=CONFIG.hazard_light_duid,
            command=CONFIG.hazard_light_command,
            source=CONFIG.hazard_source,
            off_delay_s=CONFIG.hazard_off_delay_s,
            on_args=CONFIG.hazard_light_on_args,
            off_args=CONFIG.hazard_light_off_args,
        ).start()

    cap = open_camera()
    rotate = {
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }.get(CONFIG.camera_rotate % 360)
    log.info("Entering capture loop. Ctrl-C to stop.")
    prev = time.monotonic()
    fps = 0.0
    try:
        while not state.stop.is_set():
            ok, frame = cap.read()
            if not ok:
                log.warning("Camera read failed; retrying...")
                state.stop.wait(0.1)
                continue
            if rotate is not None:
                frame = cv2.rotate(frame, rotate)
            dets = detector.infer(frame)
            dets = smoother.update(dets)  # hold detections briefly to stop flicker
            analysis = safety.analyze(dets, frame.shape[1], frame.shape[0], CONFIG.danger_margin)

            now = time.monotonic()
            dt = now - prev
            prev = now
            if dt > 0:
                fps = 0.7 * fps + 0.3 * (1.0 / dt) if fps else 1.0 / dt
            state.set_frame(frame, analysis, fps)

            annotated = draw_overlay(frame.copy(), dets, analysis, fps, state.vlm_text)
            if viewer:
                viewer.publish(annotated)
            if CONFIG.show_window:
                cv2.imshow("Physical AI Demo", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        state.stop.set()
        cap.release()
        if CONFIG.show_window:
            cv2.destroyAllWindows()
        if viewer:
            viewer.stop()
        iotc.disconnect()
        log.info("Stopped.")


if __name__ == "__main__":
    main()
