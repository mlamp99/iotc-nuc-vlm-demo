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
> — see [section 4](#4-ubuntu-core--whats-different).

---

## Contents
1. [Requirements](#1-requirements)
2. [Repository layout](#2-repository-layout)
3. [Step-by-step setup (Ubuntu Desktop / Server)](#3-step-by-step-setup-ubuntu-desktop--server)
4. [Ubuntu Core — what's different](#4-ubuntu-core--whats-different)
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
- **Ubuntu 26.04 LTS Desktop or Server** (Resolute Raccoon) — *section 3*, **or**
  **Ubuntu Core 24** — *section 4*.
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
iotc-template/       importable /IOTCONNECT device template (attributes + commands)
dashboards/          importable /IOTCONNECT dashboard(s)
credentials/         drop your device cert/key/iotcDeviceConfig.json here (git-ignored)
Dockerfile, docker-compose.yml, .env.example, requirements.txt
IOTCONNECT-TEMPLATE.md   full telemetry + command reference (build your template from this)
```

---

## 3. Step-by-step setup (Ubuntu Desktop / Server)

Nothing is assumed — do every step in order, on the NUC. *(For Ubuntu Core, do
section 4 instead.) Tested on NUC16 Panther Lake, Ubuntu 26.04 Desktop.*

### Before you start, make sure you have:
- An Intel NUC (Core Ultra) with **Ubuntu 26.04 Desktop or Server** installed and
  powered on.
- A **USB camera** plugged into the NUC.
- The NUC **connected to the internet** (Ethernet or Wi-Fi).
- Either use the NUC's own browser, or a laptop/phone on the **same network** to
  view the video.

### Step 1 — Open a terminal
On Desktop press **Ctrl + Alt + T**. On Server, log in at the console.

### Step 2 — Install git and download the project
```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/mlamp99/iotc-nuc-vlm-demo.git
cd iotc-nuc-vlm-demo
```
Every command after this is run from inside the `iotc-nuc-vlm-demo` folder.

### Step 3 — Install Docker
```bash
sudo bash scripts/install-docker.sh
newgrp docker                  # turns on Docker for this terminal (or log out/in once)
docker run --rm hello-world    # should print "Hello from Docker!"
```

### Step 4 — Install the Intel GPU / NPU drivers
```bash
sudo bash scripts/host-setup.sh
```
**Write down** the two numbers it prints at the end — you need them in Step 5:
```
RENDER_GID=...
VIDEO_GID=...
```

### Step 5 — Create and edit your settings file
```bash
cp .env.example .env
nano .env
```
Change these lines, then save with **Ctrl+O, Enter, Ctrl+X**:
- `RENDER_GID=` → the RENDER_GID number from Step 4
- `VIDEO_GID=` → the VIDEO_GID number from Step 4
- `CAMERA_SOURCE=0` → leave as `0`; try `1` or `2` if you have more than one camera
- *(optional, for the map)* set `DEVICE_LAT=` and `DEVICE_LON=` to exact
  coordinates, **or** set `GEO_AUTODETECT=1` for an approximate IP-based location
- *(optional, no cloud)* set `IOTC_ENABLED=0` to run with no /IOTCONNECT at all,
  and skip Steps 7–8

### Step 6 — Get the app image — pick ONE
**6a — Pull the prebuilt image (fastest, recommended):**
```bash
docker pull ghcr.io/mlamp99/physical-ai-demo:latest
docker tag  ghcr.io/mlamp99/physical-ai-demo:latest physical-ai-demo:latest
```
**6b — OR build it yourself** (downloads + converts the AI models; ~20–40 min,
needs ~30 GB free disk):
```bash
bash scripts/prepare_models.sh     # add BUILD_VLM_7B=0 in front to skip the large 7B model
docker compose build
```

### Step 7 — Create your device in /IOTCONNECT
*(Skip this and Step 8 if you set `IOTC_ENABLED=0` in Step 5.)*

1. **Create an /IOTCONNECT account** if you don't have one:
   https://avnet-iotconnect.github.io/ → *Create an /IOTCONNECT Account*.
2. **Create the device template — easiest is to import it:** in the web UI go to
   **Devices → Templates → Import Template** and choose
   [`iotc-template/Intel-NUC-VLM-template.json`](iotc-template/Intel-NUC-VLM-template.json).
   It defines all telemetry attributes and commands for you.
   *(Prefer to build it by hand? Create Template → Authentication Type =
   Self-Signed Certificate → add every attribute and command from the tables in
   [section 6](#6-telemetry--commands); names are case-sensitive.)*
3. **Create the device:** **Devices → Create Device**. Enter a **Unique ID**
   (e.g. `nuc-vlm-01`), select the template you just made, and choose
   **Self-Signed Certificate**.
4. **Get a certificate + key.** Either let /IOTCONNECT generate them for you to
   download, **or** make your own in the terminal and upload the `.crt`:
   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
     -keyout nuc-vlm-01.pem -out nuc-vlm-01.crt -subj "/CN=nuc-vlm-01"
   ```
5. **Download `iotcDeviceConfig.json`** from the device's **Info / Connection**
   panel.

### Step 8 — Put the credentials on the NUC
Copy the **three** files into the `credentials/` folder (the filenames don't
matter — they're detected automatically):
```bash
cp /path/to/iotcDeviceConfig.json  credentials/
cp /path/to/nuc-vlm-01.crt         credentials/
cp /path/to/nuc-vlm-01.pem         credentials/
```
> Each physical NUC needs its **own** /IOTCONNECT device + its own certificate.
> Don't reuse one device's credentials on another unit.

### Step 9 — Run the pre-flight check
```bash
docker compose run --rm physical-ai python3 -m app.selftest
```
You want the critical checks **green**: OpenVINO `GPU` (and `NPU`) present, the
models found, and the camera capturing. Credential lines will warn if you skipped
the cloud — that's fine.

### Step 10 — Start the demo
```bash
docker compose up -d
```

### Step 11 — Open the viewer
Find the NUC's IP address:
```bash
hostname -I        # e.g. 192.168.1.50
```
- On the NUC itself: open **http://localhost:8080**
- From another device on the network: open **http://<that-IP>:8080**

You should see the live camera with detection boxes, a safety banner, and an
"ask a question" box.

### Step 12 — Confirm cloud data (if you set up /IOTCONNECT)
```bash
docker compose logs -f      # look for the line: "IOTCONNECT connected." — Ctrl+C to stop watching
```
Then in /IOTCONNECT, open your device's **Live Data** to see the telemetry arriving.

### Step 13 — Import the dashboard (optional)
In /IOTCONNECT: **Dashboards → Create Dashboard → Import**, choose
[`dashboards/nuc-vlm-dashboard.json`](dashboards/), bind it to your device, and set
the **On Device View** widget URL to `http://<NUC-IP>:8080/`. Details:
[`dashboards/README.md`](dashboards/README.md).

### Everyday commands
```bash
docker compose logs -f     # watch detections / VLM answers / telemetry
docker compose down        # stop the demo
docker compose up -d       # start it again (auto-starts on boot too)
```

---

## 4. Ubuntu Core — what's different

Ubuntu Core is the immutable, snap-based edition (good for locked-down appliances
and OTA updates). The **app image is identical** — only the host setup changes.
Full notes: [`core/CORE-NOTES.md`](core/CORE-NOTES.md).

Do the **same steps as section 3**, with these substitutions:

| Section 3 step | On Ubuntu Core, do this instead |
|---|---|
| Step 3 — Install Docker (`install-docker.sh`) | `sudo bash core/core-setup.sh` (installs the **docker snap**, connects interfaces, creates `~/physical-ai`) |
| Step 4 — Install drivers (`host-setup.sh`) | **not needed** — drivers come from the Core **kernel snap**. First run `bash core/core-readiness.sh` and confirm it reports **GPU present** (this is the key prerequisite). |
| Step 5 — `.env` | put `.env` at `~/physical-ai/.env` |
| Step 8 — credentials | put them in `~/physical-ai/credentials/` |
| Step 10 — Run | `CORE_WORKDIR=$HOME/physical-ai docker compose -f docker-compose.yml -f core/docker-compose.core.yml up -d` |

Steps 2, 6, 7, 9, 11–13 are the same. If `core/core-readiness.sh` does **not**
report a GPU, the kernel snap is missing the Intel `xe`/`intel_vpu` drivers —
fix that first (see `core/CORE-NOTES.md`). Without the NPU the detector falls back
to the iGPU automatically.

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

The device template defines these. The fastest way to create it is to **import
[`iotc-template/Intel-NUC-VLM-template.json`](iotc-template/Intel-NUC-VLM-template.json)**
(Devices → Templates → Import Template). The tables below are the same definitions
for reference if you build it by hand — attribute **names are case-sensitive**.
Recommended dashboard gauge ranges are in
[`IOTCONNECT-TEMPLATE.md`](IOTCONNECT-TEMPLATE.md).

> **Booleans are sent as lowercase strings** `"true"`/`"false"`, so they are typed
> **STRING** (not BOOLEAN). Dashboard transforms should compare to lowercase
> `true`/`false`.

### Telemetry — detection & safety
| Attribute | Type | Example | Meaning |
|---|---|---|---|
| `fps` | DECIMAL | `15.0` | Detector frame rate |
| `object_count` | INTEGER | `4` | Total objects detected this frame |
| `person_count` | INTEGER | `2` | People detected |
| `person_present` | STRING | `true` | Any person in view |
| `hardhat_count` | INTEGER | `1` | Hard hats detected |
| `no_hardhat_count` | INTEGER | `1` | Workers without a hard hat (person_count − hats) |
| `vest_count` | INTEGER | `1` | Safety vests detected |
| `cone_count` | INTEGER | `3` | Traffic cones detected |
| `excavator_present` | STRING | `true` | Excavator in view |
| `ppe_compliant` | STRING | `false` | All workers have hard hats |
| `person_in_danger_zone` | STRING | `true` | A person is within the machine proximity margin |
| `safety_alert` | STRING | `worker in machine danger zone` | Composed alert text, or `clear` |
| `hazard_detected` | STRING | `false` | VLM safety verdict (`HAZARD: YES/NO`) |
| `class_counts` | STRING | `{"person":2,"hard hat":1}` | Per-class detection counts (raw JSON) |

### Telemetry — VLM
| Attribute | Type | Example | Meaning |
|---|---|---|---|
| `vlm_model` | STRING | `qwen2-vl-2b-int4` | Active VLM model (changes with `set-vlm`) |
| `vlm_latency_s` | DECIMAL | `10.6` | Last VLM response time (seconds) |
| `vlm_scene` | STRING | `HAZARD: NO …` | VLM description / answer to a query |
| `vlm_device` | STRING | `GPU` | Device the VLM runs on |
| `detector_device` | STRING | `intel:npu` | Device the detector runs on |

### Telemetry — hardware health & connectivity
| Attribute | Type | Example | Meaning |
|---|---|---|---|
| `cpu_percent` | DECIMAL | `12.9` | CPU utilization % |
| `mem_used_mb` | INTEGER | `18131` | RAM used (MB) — shared pool (also iGPU/NPU memory) |
| `mem_total_mb` | INTEGER | `32604` | RAM total (MB) |
| `mem_percent` | DECIMAL | `55.6` | RAM used % |
| `soc_temp_c` | DECIMAL | `65.0` | SoC package temperature °C (one die: CPU+iGPU+NPU) |
| `gpu_freq_mhz` | INTEGER | `2500` | iGPU current frequency (MHz) |
| `gpu_freq_pct` | DECIMAL | `100.0` | iGPU freq vs max — activity proxy |
| `npu_busy_pct` | DECIMAL | `23.5` | NPU utilization % (real) |
| `npu_freq_mhz` | INTEGER | `950` | NPU current frequency (MHz) |
| `npu_mem_mb` | DECIMAL | `100` | NPU-allocated memory (MB) |
| `cloud_connected` | STRING | `true` | Self-reported cloud link health |
| `location` | LATLONG | `33.4484,-112.0740` | Device location, if configured / auto-detected |

### Commands (cloud-to-device)
| Command | Param required | Effect |
|---|---|---|
| `ask-vlm` | yes — a question | Set as live prompt + run the VLM now; answer returns in `vlm_scene` |
| `set-prompt` | yes — prompt text | Change the recurring VLM prompt (no immediate run) |
| `capture` | no | Run the VLM now with the default safety prompt |
| `set-vlm` | yes — `2b` or `7b` | Hot-swap the VLM model at runtime (~10–30 s); active model in `vlm_model` |

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
