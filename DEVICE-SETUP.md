# Device setup guide — Ubuntu Desktop / Server

> **Scope:** this guide is for **classic Ubuntu** (Desktop or Server) on the
> device. It uses `apt` and plain `docker compose`. **For Ubuntu Core** (the
> immutable, snap-based edition) the steps are different — follow
> [`core/CORE-NOTES.md`](core/CORE-NOTES.md) instead, not this file.

Run this on the **target device** (an Intel NUC / Core Ultra mini-PC with Ubuntu).
You should have received: `physical-ai-demo.tar.gz` (the app image),
`docker-compose.yml`, `.env.example`, a `scripts/` folder, and — separately —
your IOTCONNECT credential files. Total setup time ~15 minutes.

> The demo runs a real-time construction-object detector **plus** a
> vision-language model on the device's Intel GPU, viewable in a browser, with
> safety telemetry streaming to IOTCONNECT.

## 1. Install Docker (skip if already installed)

```bash
sudo bash scripts/install-docker.sh
# then log out and back in, or:  newgrp docker
```

## 2. Install Intel GPU/NPU drivers

```bash
sudo bash scripts/host-setup.sh
```
Note the two lines it prints at the end:
```
RENDER_GID=...
VIDEO_GID=...
```
If it says the NPU driver is missing, that's fine — the demo uses the GPU.

## 3. Load the app image

**Option A — local tarball:**
```bash
docker load < physical-ai-demo.tar.gz
```

**Option B — fetch from S3** (good when you don't want to copy a 7 GB file by
hand). On the build machine: `S3_URI=s3://your-bucket/physical-ai/ PRESIGN=1 bash
scripts/push-to-s3.sh`. Then on the device:
```bash
# no AWS creds needed — use the presigned URL it printed:
S3_URL='https://your-bucket.s3...' bash scripts/fetch-from-s3.sh
# or, if the device has AWS credentials:
S3_URI='s3://your-bucket/physical-ai/physical-ai-demo.tar.gz' bash scripts/fetch-from-s3.sh
```
This downloads, checksum-verifies, and `docker load`s in one step.

## 4. Configure

```bash
cp .env.example .env
nano .env
```
Set:
- `RENDER_GID` / `VIDEO_GID` — the values from step 2
- `CAMERA_SOURCE` — usually `0`; if you have several cameras, try `1`, `2`…

Put your IOTCONNECT credential files in a `credentials/` folder next to
`docker-compose.yml` (the config json, the device `.crt`, and the key `.pem` —
filenames don't matter, they're auto-detected):
```
.
├── docker-compose.yml
├── .env
└── credentials/
    ├── iotcDeviceConfig.json
    ├── <device>.crt
    └── <device>.pem
```
To run with no cloud at all, set `IOTC_ENABLED=0` in `.env` and skip the
credentials.

## 5. Pre-flight check (do this before the event!)

```bash
docker compose run --rm physical-ai python3 -m app.selftest
```
You want all critical checks green:
```
✓ OpenVINO devices: ['CPU','GPU'] (GPU present)
✓ VLM model / Detector model
✓ Camera capture: source 0 -> 1280x720
```
IOTCONNECT lines may warn — that's fine, the demo still runs locally.

## 6. Run it

```bash
docker compose up
```
Open **http://<this-device-ip>:8080** in a browser (find the IP with
`hostname -I`). You'll see the live feed with detection boxes, a safety banner,
and an "ask a question" box wired to the VLM.

Stop with `Ctrl-C`, or run detached with `docker compose up -d`
(logs: `docker compose logs -f`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not open camera 0` | Try `CAMERA_SOURCE=1` in `.env`; check the camera is plugged in. |
| Permission denied on `/dev/dri` | Re-check `RENDER_GID` in `.env` matches `getent group render`. |
| OpenVINO shows only `['CPU']` | The host needs a recent Intel GPU driver — re-run `host-setup.sh`; the container's runtime is already current. |
| VLM very slow | It's on CPU — GPU not available. Confirm selftest shows "GPU present". |
| Preview not showing | Use a normal browser, or the built-in frame-poll should work everywhere; confirm port 8080 isn't blocked. |
| Nothing in browser from another machine | Use the device's LAN IP (`hostname -I`), not localhost. |

## Extending it

- **Detector classes** are open-vocabulary (YOLO-World) and baked in at export
  time. Edit `CONSTRUCTION_CLASSES` in `scripts/prepare_models.sh` and rebuild to
  change what it detects.
- **Telemetry & commands** are documented in `IOTCONNECT-TEMPLATE.md`.
- The single source of truth for downstream logic (e.g. driving a robotic arm or
  excavator) is `SharedState.snapshot()` in `app/main.py`.
