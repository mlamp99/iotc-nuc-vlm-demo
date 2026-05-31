"""Pre-flight self-test. Run this the moment the unit is set up to confirm the
box is demo-ready BEFORE showtime. Prints a checklist and exits non-zero if any
critical check fails.

    python -m app.selftest         (inside the container)
    ./selftest.sh                  (host wrapper)
"""
from __future__ import annotations

import os
import sys

from app.config import CONFIG

OK = "\033[92m✓\033[0m"
WARN = "\033[93m!\033[0m"
FAIL = "\033[91m✗\033[0m"


def check(label, fn, critical=True):
    try:
        detail = fn()
        print(f"  {OK} {label}: {detail}")
        return True
    except Exception as e:  # noqa: BLE001
        mark = FAIL if critical else WARN
        print(f"  {mark} {label}: {e}")
        return not critical


def c_openvino_devices():
    import openvino as ov

    core = ov.Core()
    devs = core.available_devices
    if not devs:
        raise RuntimeError("no OpenVINO devices found")
    has_gpu = any(d.startswith("GPU") for d in devs)
    has_npu = any(d.startswith("NPU") for d in devs)
    note = "GPU " + ("present" if has_gpu else "MISSING") + ", NPU " + ("present" if has_npu else "MISSING")
    return f"{devs} ({note})"


def c_genai():
    import openvino_genai  # noqa: F401

    return "openvino_genai import ok"


def c_ultralytics():
    import ultralytics  # noqa: F401

    return f"ultralytics {ultralytics.__version__}"


def c_vlm_model():
    p = CONFIG.vlm_model
    if not os.path.isdir(p):
        raise RuntimeError(f"missing model dir {p} (run prepare_models.sh)")
    return p


def c_detector_model():
    p = CONFIG.detector_model
    if not os.path.isdir(p):
        raise RuntimeError(f"missing model dir {p} (run prepare_models.sh)")
    return p


def c_camera():
    import cv2

    src = CONFIG.camera_source
    cap = cv2.VideoCapture(int(src) if src.isdigit() else src)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"cannot open camera {src!r}")
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("camera opened but no frame")
        return f"source {src} -> {frame.shape[1]}x{frame.shape[0]}"
    finally:
        cap.release()


def c_credentials():
    from app import credentials

    cfg, cert, pkey = credentials.resolve(
        CONFIG.iotc_credentials_dir, CONFIG.iotc_config_json, CONFIG.iotc_cert, CONFIG.iotc_pkey
    )
    for label, f in (("config", cfg), ("cert", cert), ("key", pkey)):
        if not (f and os.path.isfile(f)):
            raise RuntimeError(f"no {label} found in {CONFIG.iotc_credentials_dir}")
    return f"found {os.path.basename(cfg)} + {os.path.basename(cert)} + {os.path.basename(pkey)}"


def c_iotc_sdk():
    from avnet.iotconnect.sdk.lite import Client  # noqa: F401

    return "iotconnect-sdk-lite import ok"


def main():
    print("\n=== Physical AI Demo — self-test ===\n")
    results = []
    print("Runtime:")
    results.append(check("OpenVINO devices", c_openvino_devices))
    results.append(check("OpenVINO GenAI", c_genai))
    results.append(check("Ultralytics", c_ultralytics))
    print("\nModels:")
    results.append(check("VLM model", c_vlm_model))
    results.append(check("Detector model", c_detector_model))
    print("\nCamera:")
    results.append(check("Camera capture", c_camera))
    print("\nIOTCONNECT:")
    results.append(check("Credentials", c_credentials, critical=False))
    results.append(check("Lite SDK", c_iotc_sdk, critical=False))

    print()
    if all(results):
        print(f"{OK} All critical checks passed — box is demo-ready.\n")
        sys.exit(0)
    print(f"{FAIL} One or more critical checks failed — see above.\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
