# Running this on Ubuntu Core — notes & starter kit

> **For classic Ubuntu Desktop/Server, use `DEVICE-SETUP.md` instead — this file
> is only for Ubuntu Core (the immutable, snap-based edition).**
>
> **Status: untested scaffolding.** These files are a tested-by-design starting
> point, not a validated deployment. The blocking unknown is always the kernel
> snap (below). Validate `core-readiness.sh` on the actual Core device first.

The good news: the **hard part is already portable.** The Intel GPU user-space
runtime (OpenVINO + `intel-opencl-icd 26.05`) and all models are baked into the
container image, so they travel to Core's Docker unchanged. What's left is host
plumbing, and it splits into three things.

## 1. The kernel snap (the only true blocker)

Ubuntu Core's kernel is a snap. The Intel GPU (`i915`/`xe`) and NPU (`intel_vpu`)
drivers **and firmware** must be in it. Arrow Lake / Arc 140T needs a recent
kernel (~6.12+). Before anything else, confirm on the Core device:

```bash
uname -r
ls -l /dev/dri/renderD128     # GPU must be present
ls -l /dev/accel/accel0       # NPU (optional)
```

If `/dev/dri` is missing, no amount of Docker config helps — you need a newer
`pc-kernel` snap (a recent Core 24 track) or a board-enablement kernel snap from
Canonical/Intel/Avnet. **This is the item to settle first and the main risk.**

## 2. Docker via the snap (recommended route)

```bash
sudo snap install docker
sudo snap connect docker:home               # mount working dir from $HOME
sudo snap connect docker:removable-media    # or mount from /media (USB)
```
The `docker` snap bundles `docker compose`. Container device access works through
the `docker-support` interface; the **render group still applies**, so the
`group_add` in compose matters as on classic Ubuntu.

Constraints that drove the override file:
- Confined Docker can only bind-mount from **snap-allowed paths** ($HOME via the
  `home` interface, or `/media` via `removable-media`) — not arbitrary dirs.
  `docker-compose.core.yml` moves the credentials / `.env` / model-cache mounts
  to `${CORE_WORKDIR:-$HOME/physical-ai}`.
- `.env` is made optional there (defaults baked into the app), so a unit can run
  with just credentials dropped in.

### Bring-up
```bash
# one-time
sudo bash core/core-setup.sh            # installs docker snap, connects interfaces
# load the image (sideload, or pull from a registry — see below)
docker load < physical-ai-demo.tar.gz
# run with the Core override
mkdir -p ~/physical-ai/credentials && cp <your-certs> ~/physical-ai/credentials/
docker compose -f docker-compose.yml -f docker-compose.core.yml up -d
```

## 3. Native snap (the "blessed" long-term route)

Instead of Docker, repackage the app as its own confined snap (snapcraft.yaml
staging OpenVINO + the Intel user-space + models, connecting the `opengl`,
`camera`, and `network` interfaces). Cleaner for OTA and the Snap Store model,
but more work than the Docker route. Recommended only once there's a fleet.

## Things that make replication easier (do these)

1. **Push the image to a registry** instead of shipping 2.5 GB tarballs — the
   docker snap pulls cleanly and updates are a `docker pull`. See
   `scripts/push-image.sh`.
2. **Pin a known-good kernel snap** for this silicon and treat it as part of the
   image (gadget/model assertion) so every unit is identical.
3. **Keep models baked** (already done) — no downloads at the edge, no writable
   model volume to provision.
4. **One device = one IOTCONNECT identity** — provision per unit (see
   `IOTCONNECT-TEMPLATE.md`), drop its certs into the working dir; the app
   auto-detects them.
5. **Use the Core override** so all writable state lives under one `CORE_WORKDIR`
   you can back up / re-provision.

## Readiness check

Run this on the target before committing to a deployment:
```bash
bash core/core-readiness.sh
```
It checks kernel/devices, the docker snap + interfaces, and — if the image is
present — whether the container actually sees the GPU.
