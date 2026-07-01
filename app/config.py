"""Central configuration, driven entirely by environment variables.

Every tunable lives here so the same image behaves differently on the build
machine and the target device just by editing the .env file — no code changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    return _get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    # --- Camera ---------------------------------------------------------
    # Either a /dev/videoN index (e.g. "0") or a full path / RTSP URL.
    camera_source: str = _get("CAMERA_SOURCE", "0")
    frame_width: int = _get_int("FRAME_WIDTH", 1280)
    frame_height: int = _get_int("FRAME_HEIGHT", 720)

    # --- Object detection (fast path) ----------------------------------
    # Default is the YOLO-World construction model (classes baked in at export
    # time; see scripts/prepare_models.sh CONSTRUCTION_CLASSES). Point this at
    # /app/models/yolo11n_openvino_model to fall back to generic COCO classes.
    detector_model: str = _get("DETECTOR_MODEL", "/app/models/construction_openvino_model")
    # OpenVINO device for Ultralytics: intel:npu | intel:gpu | intel:cpu.
    # Default NPU keeps the detector off the iGPU so the VLM has it to itself
    # (falls back NPU->GPU->CPU if the NPU user-space/driver is unavailable).
    detector_device: str = _get("DETECTOR_DEVICE", "intel:npu")
    detector_conf: float = _get_float("DETECTOR_CONF", 0.25)
    # Temporal smoothing: hold a detection for N frames after it briefly drops,
    # so labels (e.g. hard hats near the confidence threshold) don't flicker
    # on/off. ~8 frames ≈ 0.5 s at 15 FPS. Set 0 to disable.
    detector_smooth_ttl: int = _get_int("DETECTOR_SMOOTH_TTL", 8)
    detector_smooth_iou: float = _get_float("DETECTOR_SMOOTH_IOU", 0.3)
    # Person↔machinery proximity margin for the danger-zone flag, as a fraction
    # of frame size (0.05 = 5%).
    danger_margin: float = _get_float("DANGER_MARGIN", 0.05)

    # --- Vision-language model (slow path) -----------------------------
    vlm_model: str = _get("VLM_MODEL", "/app/models/qwen2-vl-2b-int4")
    # Friendly aliases for the `set-vlm` cloud command (e.g. set-vlm 7b).
    vlm_model_2b: str = _get("VLM_MODEL_2B", "/app/models/qwen2-vl-2b-int4")
    vlm_model_7b: str = _get("VLM_MODEL_7B", "/app/models/qwen2.5-vl-7b-int4")
    # OpenVINO device for GenAI: GPU | NPU | CPU | AUTO
    vlm_device: str = _get("VLM_DEVICE", "GPU")
    vlm_max_new_tokens: int = _get_int("VLM_MAX_NEW_TOKENS", 150)
    # Downscale the frame sent to the VLM so its longest side is <= this (px).
    # The VLM's cost scales with pixel count; the detector still uses full res.
    vlm_max_side: int = _get_int("VLM_MAX_SIDE", 1024)
    # Auto-run the VLM on the live scene every N seconds (0 = on-demand only).
    # The VLM and detector share the iGPU, so a longer interval keeps detection
    # FPS smooth between safety checks.
    vlm_interval_s: float = _get_float("VLM_INTERVAL_S", 15.0)
    # The default prompt is a structured safety check: the first line is parsed
    # into the hazard_detected telemetry flag.
    vlm_default_prompt: str = _get(
        "VLM_DEFAULT_PROMPT",
        "You are the safety monitor for a construction site with smart machines. "
        "Reply with a first line that is exactly 'HAZARD: YES' or 'HAZARD: NO', then "
        "one sentence describing the scene and any people, missing PPE (hard hats or "
        "safety vests), or workers too close to machinery.",
    )

    # --- IOTCONNECT -----------------------------------------------------
    # Drop any device's files into this folder; the config json, cert and key
    # are auto-detected (see app/credentials.py). Set the explicit paths below
    # only to override discovery.
    iotc_credentials_dir: str = _get("IOTC_CREDENTIALS_DIR", "/app/credentials")
    iotc_config_json: str = _get("IOTC_CONFIG_JSON", "")
    iotc_cert: str = _get("IOTC_CERT", "")
    iotc_pkey: str = _get("IOTC_PKEY", "")
    iotc_enabled: bool = _get_bool("IOTC_ENABLED", True)
    # Transport for telemetry/commands:
    #   "lite"       - standalone: X.509 direct MQTT via iotconnect-sdk-lite
    #                  (the default; used by the standalone Docker demo).
    #   "greengrass" - through the Greengrass Nucleus over IPC. Set by the
    #                  Greengrass component (see greengrass/). Requires the
    #                  greengrass extras baked into the image.
    iotc_transport: str = _get("IOTC_TRANSPORT", "lite").strip().lower()
    telemetry_interval_s: float = _get_float("TELEMETRY_INTERVAL_S", 10.0)
    # Device location sent as an IOTCONNECT LATLONG attribute ("lat,lon"). Set
    # both for a fixed install; or enable GEO_AUTODETECT for approximate IP-based.
    device_lat: str = _get("DEVICE_LAT", "")
    device_lon: str = _get("DEVICE_LON", "")
    geo_autodetect: bool = _get_bool("GEO_AUTODETECT", False)

    # --- Viewer ---------------------------------------------------------
    # Lightweight MJPEG stream so any device on the LAN can watch in a browser.
    mjpeg_enabled: bool = _get_bool("MJPEG_ENABLED", True)
    mjpeg_port: int = _get_int("MJPEG_PORT", 8080)
    # Extra blank space (px) at the top of the viewer page — handy when embedding
    # it in a dashboard widget whose header would otherwise clip the video.
    viewer_top_pad: int = _get_int("VIEWER_TOP_PAD", 0)
    # Also pop a local OpenCV window (needs an X server / display passthrough).
    show_window: bool = _get_bool("SHOW_WINDOW", False)

    # --- Misc -----------------------------------------------------------
    log_level: str = _get("LOG_LEVEL", "INFO")


CONFIG = Config()
