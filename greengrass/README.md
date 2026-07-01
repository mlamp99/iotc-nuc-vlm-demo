# Safety Vision — AWS Greengrass component for /IOTCONNECT

This packages the construction-safety vision app (in [`../`](../)) as an AWS
Greengrass v2 component for Avnet **/IOTCONNECT**, **in addition to** the
standalone Docker demo. The standalone demo (`../docker-compose.yml`) is
unchanged — this is a separate, parallel way to deploy and manage the same app
on a Greengrass core device running **regular Nucleus (Classic)**.

Because the workload needs the Intel OpenVINO runtime, iGPU/NPU access and
multi-GB baked-in models, it ships as a **Docker-application component** (it
reuses the existing `ghcr.io/mlamp99/physical-ai-demo` image) rather than as a
pure-Python pip component. Greengrass manages the lifecycle via the
`aws.greengrass.DockerApplicationManager` dependency.

## Layout

```
greengrass/
├── install-nucleus.sh              # one-shot Nucleus Classic install (run as root)
├── connection-kit/                 # the core device's GG connection kit (SECRET)
└── safety-vision/                  # the GDK component project
    ├── gdk-config.json             # GDK metadata (component name, bucket, region)
    ├── recipe.yaml                 # Greengrass recipe (templated by GDK)
    ├── build.sh                    # gdk component build
    ├── local-deploy.sh             # build + deploy to the local core (dev)
    ├── requirements-greengrass.txt # greengrass SDK extras (baked into the :greengrass image)
    ├── iotc-template/
    │   └── Construction-Safety-VLM-template.json   # device template to import
    └── wrapper/
        ├── docker-compose.gg.yml   # devices + env + IPC passthrough
        ├── component-install.sh     # pull the (public) image
        └── component-run.sh         # forward IPC env, docker compose up
```

> ⚠️ `connection-kit/` contains the core device's **private key**. Never commit
> or share it (it lives OUTSIDE the GDK project dir so it can't be swept into the
> component artifact). It is git-ignored at the repo level; treat it as a secret.

## How it connects to /IOTCONNECT

The component sends telemetry and receives commands **through the Greengrass
Nucleus over IPC** — it publishes under the **core device's** identity (e.g.
`mclNUC16`), with no separate device certs. This is the default; deploy with no
configuration needed.

How it's wired:

- **Image** — uses `ghcr.io/mlamp99/physical-ai-demo:greengrass`, which bundles
  the /IOTCONNECT Greengrass SDK (`requirements-greengrass.txt`). The standalone
  demo's `:latest` image uses the lite SDK for direct MQTT instead; the two SDKs
  can't coexist (conflicting `iotconnect-lib`), so they're separate image tags
  built from the one `../Dockerfile` via `ARG IOTC_SDK`. Build/push the greengrass
  image with `PUSH=1 ../scripts/build-greengrass-image.sh`.
- **IPC** — the recipe grants IPC access (`accessControl`: mqttproxy + pubsub) and
  `wrapper/component-run.sh` forwards the Nucleus IPC socket + `SVCUID` +
  `AWS_IOT_THING_NAME` + `AWS_REGION` into the container, bind-mounting the socket
  at its advertised path.
- **Config** — `IOTC_TRANSPORT=greengrass` is the recipe default. Optionally set
  `IOTC_CPID`/`IOTC_ENV` for REST topic discovery; otherwise the DUID is inferred
  from `AWS_IOT_THING_NAME`.

## Replicate from scratch (end-to-end)

These are the exact steps to stand up a new Greengrass core device for this
component. Tested with the `mclNUC16` device on an Intel NUC, Nucleus Classic
**2.16.1**, region **us-east-1**.

### 1. Create the device template in /IOTCONNECT

In the /IOTCONNECT console → **Templates → Import**, import
[`iotc-template/Construction-Safety-VLM-template.json`](safety-vision/iotc-template/Construction-Safety-VLM-template.json).
It defines all telemetry attributes (detections, PPE/safety flags, VLM fields,
hardware metrics, `location`) and the four commands (`capture`, `set-prompt`,
`set-vlm`, `ask-vlm`) the app uses — identical to the standalone demo's template,
so dashboards are reusable.

### 2. Create the Greengrass device + download the connection kit

Console → **Devices → Create Device**, choosing the Greengrass-capable device
type bound to the *Construction Safety VLM* template (CA-signed / dv 2.1). After
creation, download its **connection kit** zip — it contains `config.yaml`,
`device.pem.crt`, `private.pem.key`, `AmazonRootCA1.pem`. Keep it secret.

### 3. Host prep on the device (mostly shared with the demo)

```bash
# Docker + Compose, Intel iGPU/NPU host drivers — same as the standalone demo:
sudo bash ../scripts/install-docker.sh   # if Docker isn't installed
sudo bash ../scripts/host-setup.sh       # Intel GPU/NPU host drivers
# Java for Nucleus Classic:
sudo apt-get install -y default-jdk
```

### 4. Install the Greengrass Nucleus (Classic) with the connection kit

> Use the **Classic** installer (`install-nucleus.sh`). Do NOT use Avnet's
> `iotc-python-greengrass-sdk/installer/ubuntu/device-setup.sh` — that installs
> Greengrass *Lite*, which does not support `DockerApplicationManager`.

Drop the connection kit into `greengrass/connection-kit/` and run:

```bash
sudo bash greengrass/install-nucleus.sh
# or point at a specific kit: sudo bash greengrass/install-nucleus.sh /path/to/kit.zip
```

The script installs Java if needed, downloads the pinned Nucleus (2.16.1), stages
the kit (so `{{config_dir}}` in `config.yaml` resolves), and registers Greengrass
as a system service. Verify:

```bash
sudo systemctl status greengrass
sudo tail -f /greengrass/v2/logs/greengrass.log
```

The device should now show **Last Connection** populated in the console (it is
online as a Greengrass core). Nucleus runs as **root**, so it already has access
to `/dev/dri`, `/dev/accel` and the camera.

### 5. Build the component (and the greengrass image)

```bash
# one-time / on app changes: build + push the greengrass image variant
PUSH=1 ./scripts/build-greengrass-image.sh    # needs: docker login ghcr.io

cd greengrass/safety-vision
./build.sh     # GDK -> greengrass-build/recipes/recipe.yaml + .../safety-vision.zip
```

This needs no AWS credentials. Upload the generated **recipe.yaml** and the
**safety-vision.zip** artifact to /IOTCONNECT via **Package** (the platform hosts
the artifact). `gdk component publish` is the alternative if you have direct AWS
S3 credentials and want to push to your own bucket (`iotc-safety-vision`).

### 6. Deploy to the device

In the /IOTCONNECT console: **Package → add this component → deploy to the device**.
No configuration is required — the recipe defaults `IOTC_TRANSPORT=greengrass`, so
telemetry flows under the core device's identity out of the box. Optionally set:

- `IOTC_CPID`, `IOTC_ENV` for REST topic discovery
- any app tunables (`VLM_INTERVAL_S`, `DETECTOR_DEVICE`, `MJPEG_PORT`, …)

Watch it converge:

```bash
sudo tail -f /greengrass/v2/logs/io.iotconnect.example.IotConnectSafetyVision.log
# viewer: http://<device-ip>:8080   telemetry: device's Live Data in /IOTCONNECT
```

For local dev iteration on a device that already has the Greengrass CLI
(`aws.greengrass.Cli`) deployed, skip steps 5–6 and use `./local-deploy.sh`.

## Device prerequisites (core device)

- Greengrass Nucleus **Classic** (DockerApplicationManager is not on Nucleus Lite).
- Docker Engine + Compose v2 installed (Nucleus runs as root here, so no extra
  `docker`-group setup is needed).
- Access to `/dev/dri`, `/dev/accel`, `/dev/video0` (root has this).
- Intel host drivers for the iGPU/NPU (same as the standalone demo;
  see `../scripts/host-setup.sh`).
- GHCR image package is **public**, so no registry login is required.
