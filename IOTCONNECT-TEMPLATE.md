# IOTCONNECT device template — NUC Physical AI

Reference for setting up the device template in the IOTCONNECT (AWS) console so
telemetry charts and commands work. Device: `<your-device-id>`, auth: self-signed X.509
(`at:3`), env `poc`.

## Template basics
- **Template code / name:** e.g. `nucvlm` / "NUC Physical AI"
- **Authentication type:** Self-signed certificate (X.509) — matches the cert/key
  shipped with the device.
- After creating the template, associate your device with it.

## Telemetry attributes

The device publishes one flat JSON object per `TELEMETRY_INTERVAL_S` (default 10s).
Attribute names are **case-sensitive** and must match exactly.

> **Booleans are sent as lowercase strings** `"true"`/`"false"` (template type **STRING**), so dashboard transforms should compare to `true`/`false` (lowercase).


| Attribute name           | Data Type          | Example          | Meaning                                          |
|--------------------------|--------------------|------------------|--------------------------------------------------|
| `fps`                    | NUMBER             | `21.9`           | Detector frame rate                              |
| `object_count`           | NUMBER             | `4`              | Total objects detected this frame                |
| `person_count`           | NUMBER             | `2`              | People detected (chartable)                      |
| `person_present`         | STRING             | `true`           | Any person in view                               |
| `hardhat_count`          | NUMBER             | `1`              | Hard hats detected                               |
| `no_hardhat_count`       | NUMBER             | `1`              | Workers without a hard hat (person_count − hats) |
| `vest_count`             | NUMBER             | `1`              | Safety vests detected                            |
| `cone_count`             | NUMBER             | `3`              | Traffic cones detected                           |
| `excavator_present`      | STRING             | `true`           | Excavator in view                                |
| `ppe_compliant`          | STRING             | `false`          | All workers have hard hats                       |
| `person_in_danger_zone`  | STRING             | `true`           | A person is within the machine proximity margin  |
| `safety_alert`           | STRING             | `"worker in machine danger zone"` | Composed alert text, or `"clear"`|
| `hazard_detected`        | STRING             | `false`          | VLM safety verdict (`HAZARD: YES/NO`)            |
| `vlm_model`              | STRING             | `qwen2-vl-2b-int4` | Active VLM model (changes with `set-vlm`)      |
| `vlm_latency_s`          | NUMBER             | `10.6`           | Last VLM response time (seconds)                |
| `class_counts`           | STRING (or OBJECT) | `{"person":2}`   | Per-class detection counts (raw JSON)            |
| `vlm_scene`              | STRING             | `"HAZARD: NO ..."`| VLM description / answer to a query             |
| `vlm_device`             | STRING             | `"GPU"`          | Device the VLM runs on                           |
| `detector_device`        | STRING             | `"intel:gpu"`    | Device the detector runs on                      |
| `cloud_connected`        | STRING             | `true`           | Self-reported cloud link health                  |
| `location`               | LATLONG            | `33.4484,-112.0740` | Device location, if configured (DEVICE_LAT/LON) or IP-auto-detected |

Live payload reference:
```json
{"fps":14.4,"object_count":4,"person_count":2,"person_present":true,"hardhat_count":1,
 "no_hardhat_count":1,"vest_count":1,"cone_count":0,"excavator_present":true,
 "ppe_compliant":false,"person_in_danger_zone":true,"safety_alert":"worker in machine danger zone",
 "class_counts":{"person":2,"excavator":1,"hard hat":1},"hazard_detected":true,
 "vlm_scene":"HAZARD: YES A worker stands within the excavator swing radius...",
 "vlm_device":"GPU","detector_device":"intel:gpu","cloud_connected":true}
```

### Performance / hardware-health attributes

Sampled every telemetry interval from `/proc` and `/sys` (no privileged container).
All NUMBER.

| Attribute        | Example  | Meaning                                                        |
|------------------|----------|----------------------------------------------------------------|
| `cpu_percent`    | `12.9`   | CPU utilization %                                              |
| `mem_used_mb`    | `18131`  | RAM used (MB) — shared pool, also covers iGPU/NPU memory       |
| `mem_total_mb`   | `32604`  | RAM total (MB)                                                 |
| `mem_percent`    | `55.6`   | RAM used %                                                     |
| `soc_temp_c`     | `65.0`   | SoC package temperature °C (one die — covers CPU + iGPU + NPU) |
| `gpu_freq_mhz`   | `2500`   | iGPU current frequency (MHz)                                  |
| `gpu_freq_pct`   | `100.0`  | iGPU freq vs max — **activity proxy** (no busy-% counter in sysfs) |
| `npu_busy_pct`   | `23.5`   | NPU utilization % — **real**, from the busy-time counter       |
| `npu_freq_mhz`   | `950`    | NPU current frequency (MHz)                                    |
| `npu_mem_mb`     | `100`    | NPU-allocated memory (MB)                                      |

Notes: On this integrated SoC the CPU, iGPU and NPU are one chip, so there's a
single **package** temperature, not separate GPU/NPU sensors. The iGPU (xe
driver) exposes frequency but no per-engine busy counter — `gpu_freq_pct` is the
proxy; true GPU % needs `intel_gpu_top` (PMU access), which isn't enabled here.
The **NPU busy-%** is genuine (cumulative busy-time delta).

**`class_counts` note:** keys are dynamic (any detected class), so it can't use a
fixed OBJECT schema — use `STRING` to store/display the raw JSON. The chartable
per-class numbers (`person_count`, `hardhat_count`, etc.) are already broken out
as their own NUMBER attributes above.

**Detector classes** are open-vocabulary (YOLO-World) and baked in at model-export
time. Defaults: `person, excavator, dump truck, wheel loader, hard hat,
safety vest, traffic cone, barrier`. Change them by editing `CONSTRUCTION_CLASSES`
and re-running `scripts/prepare_models.sh` (keep `person`, `hard hat`,
`safety vest`, `excavator` — the safety logic keys off those names).

## Commands (cloud-to-device)

Command names are matched case-insensitively by the device.

| Command name | Parameter            | Effect                                                        |
|--------------|----------------------|---------------------------------------------------------------|
| `ask-vlm`    | text (the question)  | Set as live prompt + run VLM now; answer returns in `vlm_scene`|
| `set-prompt` | text (the prompt)    | Change the recurring VLM prompt (no immediate run)            |
| `capture`    | *(none)*             | Run the VLM now with the default prompt                       |
| `set-vlm`    | `2b` or `7b` (or a model path) | Hot-swap the VLM model at runtime (~10-30s); active model reported in `vlm_model` telemetry |

Example execution from the console: `ask-vlm How many people are near the machine?`
The SDK takes the first token as the command name and passes the remainder as the
argument; the device rejoins it into the full question.

## Provisioning a new device (one per physical unit)

A device certificate is a single identity — **every physical NUC needs its own
IOTCONNECT device and its own certs.** Don't copy one device's `credentials/`
folder to another unit. To add a unit:

1. **Console → Devices → Device → Create Device.** Give it a unique ID (e.g.
   `site-nuc-01`) and select the template above (auth: Self-Signed Certificate).
2. **Certificate.** Either let IOTCONNECT generate a key pair + certificate for
   you to download, or generate a self-signed pair yourself and upload the public
   cert, e.g.:
   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
     -keyout site-nuc-01.pem -out site-nuc-01.crt -subj "/CN=site-nuc-01"
   ```
   Upload `site-nuc-01.crt` to the device's certificate field.
3. **Download `iotcDeviceConfig.json`** from the device's Info / Connection panel
   (it carries the CPID, environment, unique ID, platform, and discovery URL).
4. **Drop all three files** — `iotcDeviceConfig.json`, the `.crt`, and the key
   `.pem` — into that unit's `credentials/` folder. Filenames don't matter; the
   app auto-detects them (see `app/credentials.py`).
5. Run the self-test; it should report the three files found, and the device
   will appear connected in the console once started.

(Exact menu labels vary slightly across IOTCONNECT releases.)

## How the data is framed on the wire
`Client.send_telemetry(data)` (lite SDK) wraps the flat dict as
`{"d":[{"d":{...}}]}` over MQTT — the dict keys become the template attribute
names. No telemetry groups (`tg`) are used.
