<img src="https://avnet-iotconnect.github.io/img/logos/iotc-w-r-h.png" alt="/IOTCONNECT" width="220"/>

# Physical AI Construction VLM — Intel NUC + OpenVINO + /IOTCONNECT

A self-contained **physical-AI edge demo** for an Intel NUC (Core Ultra, Arc
iGPU + NPU) running Ubuntu. It runs two vision pipelines at once and streams the
results to Avnet **/IOTCONNECT** on AWS:

- **Construction object detection** (YOLO-World, open-vocabulary) on the **NPU** —
  detects `person, excavator, dump truck, wheel loader, hard hat, safety vest,
  traffic cone, barrier` and derives **PPE compliance, machine danger-zone
  proximity, and a safety alert**.
- **Vision-language model** (Qwen2-VL **2B** / Qwen2.5-VL **7B**, INT4) on the
  **iGPU** — a structured `HAZARD: YES/NO` safety check + scene description, and
  answers ad-hoc questions on demand. The model is **hot-swappable from the cloud**.
- **/IOTCONNECT** telemetry: per-class counts, safety flags, VLM latency, and live
  **CPU / iGPU / NPU / memory / temperature** metrics. Cloud-to-device commands.
- **Browser viewer** with an "ask a question" box (`http://<device-ip>:8080`).

Everything is **Dockerized and reproducible** — the OpenVINO runtime, the Intel
GPU/NPU user-space drivers, and the models are all baked into the image, so a
target device only needs the host kernel drivers and the camera.

> **Tested on:** Intel **NUC16** (Core Ultra "Panther Lake"), **Ubuntu 26.04 LTS
> Desktop (Resolute Raccoon)**.
> **Also supported:** Intel **NUC15** (Core Ultra "Arrow Lake") on **Ubuntu Core**
> — see [Option B](#option-b--ubuntu-core-nuc-15).

---

## Contents
1. [Requirements](#1-requirements)
2. [Repository layout](#2-repository-layout)
3. [Set up /IOTCONNECT](#3-set-up-iotconnect)
4. [Build & run the device](#4-build--run-the-device)
   - [Option A — Ubuntu Desktop / Server (recommended)](#option-a--ubuntu-desktop--server-recommended)
   - [Option B — Ubuntu Core (NUC 15)](#option-b--ubuntu-core-nuc-15)
5. [Using the demo](#5-using-the-demo)
6. [Telemetry & commands](#6-telemetry--commands)
7. [Performance](#7-performance-verified-on-hardware)
8. [Distributing the image](#8-distributing-the-image)
9. [Troubleshooting](#9-troubleshooting)
10. [Resources](#10-resources)

---

## 1. Requirements

### Hardware
- **Intel NUC** with a Core Ultra processor (Arc iGPU + NPU / "AI Boost").
  Tested on **NUC16 (Panther Lake)**; works on **NUC15 (Arrow Lake)**.
- **16 GB RAM minimum**, **32 GB recommended** (the iGPU/NPU share system RAM;
  the 7B VLM needs the headroom).
- **~30 GB free disk** for model conversion + image (less if you skip the 7B model).
- A **USB / UVC camera** (a depth camera such as Intel RealSense also works).
- Internet access **on the build machine** (to pull models + base images).

### Software
- **Ubuntu 26.04 LTS Desktop or Server** (Resolute Raccoon) — *Option A*, **or**
  **Ubuntu Core 24** — *Option B*.
- A recent kernel that exposes the GPU (`/dev/dri`) and NPU (`/dev/accel`). Modern
  Ubuntu does this out of the box for Core Ultra.
- **Docker Engine + Compose** (installed by the included script).

### /IOTCONNECT
- An **Avnet /IOTCONNECT** account (AWS). Don't have one? Start here:
  **https://avnet-iotconnect.github.io/** → *Create an /IOTCONNECT Account*.

---

## 2. Repository layout

```
app/                 the application (camera → detect+VLM → viewer → telemetry)
  main.py            orchestrator (capture/detect loop, VLM worker, telemetry)
  detector.py        YOLO-World construction detector (NPU/GPU/CPU fallback)
  safety.py          PPE / danger-zone / per-class safety analysis
  vlm.py             Qwen2-VL 2B/7B via OpenVINO GenAI; runtime hot-swap
  sysmon.py          CPU/GPU/NPU/memory/temperature metrics
  iotc.py            /IOTCONNECT lite SDK (X.509, AWS); degrades to local-only
  credentials.py     auto-detects the device cert/key/config
  viewer.py          MJPEG browser viewer + ask box
  selftest.py        pre-flight checks
scripts/             install-docker, host-setup, prepare_models, build/ship, S3
core/                Ubuntu Core notes + setup/readiness + compose override
dashboards/          importable /IOTCONNECT dashboard(s)
credentials/         drop your device cert/key/iotcDeviceConfig.json here (git-ignored)
Dockerfile, docker-compose.yml, .env.example, requirements.txt
IOTCONNECT-TEMPLATE.md   full telemetry + command reference (build your template from this)
DEVICE-SETUP.md          condensed device-side setup guide
```

---

## 3. Set up /IOTCONNECT

You can do this before or after building — the demo also runs fully offline
(`IOTC_ENABLED=0`), but to see cloud telemetry do the following once.

### 3.1 Create a device template
In the /IOTCONNECT web UI: **Devices → Device Template → Create Template**.
- **Authentication type:** *Self-Signed Certificate (X.509)*.
- **Attributes & Commands:** add the attributes and commands exactly as listed in
  [`IOTCONNECT-TEMPLATE.md`](IOTCONNECT-TEMPLATE.md) (names are case-sensitive).
  That file documents all telemetry fields (detections, safety flags, VLM latency,
  CPU/GPU/NPU/temp) and the `ask-vlm` / `set-prompt` / `capture` / `set-vlm`
  commands.

### 3.2 Create the device
**Devices → Create Device.**
- **Unique ID / Name:** e.g. `nuc-vlm-01`.
- **Template:** the one from 3.1.
- **Authentication:** Self-Signed Certificate. Either let /IOTCONNECT generate a
  key pair + certificate for you to download, or generate one yourself:
  ```bash
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout nuc-vlm-01.pem -out nuc-vlm-01.crt -subj "/CN=nuc-vlm-01"
  ```
  and upload `nuc-vlm-01.crt`.

### 3.3 Download the credentials
From the device's **Info / Connection** panel, download **`iotcDeviceConfig.json`**.
Then place these three files in the repo's `credentials/` folder (filenames don't
matter — they're auto-detected):
```
credentials/
├── iotcDeviceConfig.json
├── nuc-vlm-01.crt
└── nuc-vlm-01.pem
```
> One device = one identity. Each physical NUC needs its **own** device + certs.

### 3.4 Import the dashboard (optional, recommended)
Import [`dashboards/nuc-vlm-dashboard.json`](dashboards/) — see
[`dashboards/README.md`](dashboards/README.md). Bind it to your device and set the
**On Device View** URL to `http://<your-device-ip>:8080/`.

---

## 4. Build & run the device

### Option A — Ubuntu Desktop / Server (recommended)
*(Tested: NUC16 Panther Lake, Ubuntu 26.04 Desktop.)*

Run these on the NUC. Each script is safe to re-run.

```bash
# 0. Clone
git clone https://github.com/mlamp99/iotc-nuc-vlm-demo.git
cd iotc-nuc-vlm-demo

# 1. Install Docker (then log out/in once, or run: newgrp docker)
sudo bash scripts/install-docker.sh

# 2. Install the Intel GPU/NPU host drivers; note the printed RENDER_GID / VIDEO_GID
sudo bash scripts/host-setup.sh

# 3. Configure
cp .env.example .env
nano .env            # set RENDER_GID, VIDEO_GID, CAMERA_SOURCE (usually 0)

# 4. Download + convert the models into ./models  (one-time, online)
#    Builds: construction detector, COCO fallback, Qwen2-VL-2B, Qwen2.5-VL-7B.
#    Skip the large 7B model with:  BUILD_VLM_7B=0 bash scripts/prepare_models.sh
bash scripts/prepare_models.sh

# 5. Build the image (bakes in models + Intel GPU/NPU runtime)
docker compose build

# 6. Pre-flight check — expect GPU + NPU + camera + models all green
docker compose run --rm physical-ai python3 -m app.selftest

# 7. Run it
docker compose up -d
```
Open **`http://localhost:8080`** (or `http://<nuc-ip>:8080` from another machine).
Telemetry starts flowing to /IOTCONNECT immediately.

### Option B — Ubuntu Core (NUC 15)

Ubuntu Core is the immutable, snap-based edition (good for locked-down appliances
and OTA). The build is the same image; the host bring-up differs. **Full guide:**
[`core/CORE-NOTES.md`](core/CORE-NOTES.md).

```bash
git clone https://github.com/mlamp99/iotc-nuc-vlm-demo.git
cd iotc-nuc-vlm-demo

# 0. Confirm the kernel exposes the GPU/NPU on Core (the key prerequisite)
bash core/core-readiness.sh        # must report GPU present

# 1. Install the docker snap + connect interfaces + make the working dir
sudo bash core/core-setup.sh

# 2. Build models + image (on the device, or load a prebuilt image — see §8)
bash scripts/prepare_models.sh
docker compose build

# 3. Put credentials + .env under the Core working dir, then run with the override
mkdir -p ~/physical-ai/credentials && cp credentials/* ~/physical-ai/
CORE_WORKDIR=$HOME/physical-ai \
  docker compose -f docker-compose.yml -f core/docker-compose.core.yml up -d
```
> On Ubuntu Core the **kernel snap** must include the Intel GPU (`xe`/`i915`) and
> NPU (`intel_vpu`) drivers + firmware. `core/core-readiness.sh` checks this in one
> command — settle it first. If the NPU is absent, the detector falls back to the
> iGPU automatically.

---

## 5. Using the demo

**Browser viewer** — `http://<device-ip>:8080`:
- Live camera with detection boxes (person = red, machinery = orange), a safety
  banner, and the VLM scene text.
- An **ask box** — type a question (*"Is everyone wearing a hard hat?"*) and the
  VLM answers; the answer updates live.

**From the /IOTCONNECT dashboard** (cloud commands):
| Command | Param | Effect |
|---|---|---|
| `ask-vlm` | a question | Run the VLM now with that question |
| `set-prompt` | text | Change the recurring prompt |
| `capture` | — | Run the VLM now with the default safety prompt |
| `set-vlm` | `2b` / `7b` | **Hot-swap the VLM model** (~10–30 s); active model shown in `vlm_model` |

**Switch the VLM locally** (no cloud needed):
```bash
bash scripts/use-vlm.sh 7b     # sharper, ~20–30 s/answer
bash scripts/use-vlm.sh 2b     # fast, ~5 s/answer (default)
```

**Manage it:**
```bash
docker compose logs -f       # watch detections / VLM answers / telemetry
docker compose down          # stop
docker compose up -d         # start (resumes on the last-used model; auto-starts on boot)
```

---

## 6. Telemetry & commands

The full, authoritative list of telemetry attributes (with data types and gauge
ranges) and cloud commands is in **[`IOTCONNECT-TEMPLATE.md`](IOTCONNECT-TEMPLATE.md)**.
Build your device template from it. Highlights:

- **Detections / safety:** `person_count`, `hardhat_count`, `no_hardhat_count`,
  `vest_count`, `cone_count`, `excavator_present`, `ppe_compliant`,
  `person_in_danger_zone`, `safety_alert`, `hazard_detected`.
- **VLM:** `vlm_model`, `vlm_latency_s`, `vlm_scene`, `vlm_device`.
- **Hardware health:** `cpu_percent`, `mem_used_mb`/`mem_total_mb`/`mem_percent`,
  `soc_temp_c`, `gpu_freq_mhz`/`gpu_freq_pct`, `npu_busy_pct`/`npu_freq_mhz`/`npu_mem_mb`.

---

## 7. Performance (verified on hardware)

| Stage | Where | Result |
|---|---|---|
| Construction detector | **NPU** | ~124 FPS of headroom (8 ms/frame); frees the iGPU |
| VLM — Qwen2-VL-2B INT4 | **iGPU** | ~5 s / answer |
| VLM — Qwen2.5-VL-7B INT4 | **iGPU** | ~20–30 s / answer (sharper) |
| Live preview | camera-bound | ~15 FPS @ 720p (MJPG); compute is not the limit |

Because the detector runs on the NPU and the VLM on the iGPU, they don't contend —
detection stays smooth while the VLM thinks.

---

## 8. Distributing the image

Building on every device is fine, but for fleets you can build once and ship the
image:
- **Tarball (offline):** `bash scripts/build-and-save.sh` → `ship/physical-ai-demo.tar.gz`
  → copy to the device → `docker load < physical-ai-demo.tar.gz`.
- **S3:** `scripts/push-to-s3.sh` (build machine) + `scripts/fetch-from-s3.sh`
  (device, supports a presigned URL — no AWS creds needed on the device).
- **Registry:** `scripts/push-image.sh` → devices `docker pull`.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied ... docker.sock` | Your shell predates the Docker install — run `newgrp docker`, or log out/in. |
| Selftest shows `['CPU']` only | Host GPU driver too old/missing — re-run `host-setup.sh`; the container runtime is current. |
| `Could not open camera 0` | Try `CAMERA_SOURCE=1` in `.env`; ensure the camera is connected and not held by another process. |
| Preview blank in the browser | Hard-refresh; use the device LAN IP (not localhost) from another machine; confirm port 8080 is reachable. |
| Permission denied on `/dev/dri` | `RENDER_GID` in `.env` must match `getent group render`. |
| NPU missing in selftest | Optional — detector falls back to the iGPU. On Ubuntu Core, the kernel snap must include `intel_vpu`. |
| No data in /IOTCONNECT | Confirm the 3 files are in `credentials/`; run selftest; check `docker compose logs` for "IOTCONNECT connected". |

---

## 10. Resources

- **/IOTCONNECT Enablement Hub:** https://avnet-iotconnect.github.io/
- **/IOTCONNECT:** https://www.iotconnect.io
- **/IOTCONNECT Knowledgebase:** https://help.iotconnect.io
- **Avnet /IOTCONNECT on GitHub:** https://github.com/avnet-iotconnect
- **OpenVINO:** https://docs.openvino.ai
