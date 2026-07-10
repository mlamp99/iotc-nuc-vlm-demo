# Physical AI edge demo image.
#
# Base: Ubuntu 26.04 — its stock Intel compute-runtime (intel-opencl-icd 26.05)
# is the version that actually drives the Arrow Lake / Arc 140T iGPU. Older
# bases (Ubuntu 24.04 = 23.43, the official OpenVINO image = 24.48) only expose
# the CPU on this silicon. The GPU/NPU *kernel* drivers live on the host and are
# passed in via /dev/dri and /dev/accel (see docker-compose.yml); this image
# carries the matching user-space runtime.
FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System deps: Python, OpenCV runtime libs, and the Intel user-space GPU
# compute runtime (OpenCL + Level-Zero) so OpenVINO can target the Arc iGPU.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        libgl1 libglib2.0-0 \
        ca-certificates \
        ocl-icd-libopencl1 intel-opencl-icd \
        libze1 libze-intel-gpu1 \
        intel-media-va-driver-non-free \
    && rm -rf /var/lib/apt/lists/*

# Use a venv so we sidestep PEP 668 "externally managed" and keep a clean PATH.
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python3 -m venv "$VIRTUAL_ENV" && pip install --no-cache-dir --upgrade pip

# CPU-only PyTorch first so Ultralytics doesn't pull the multi-GB CUDA build.
# (Inference runs through OpenVINO; torch is only used by Ultralytics plumbing.)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Transport SDK selection. The lite SDK (in requirements.txt, default) and the
# Greengrass SDK CANNOT coexist — both depend on iotconnect-lib at conflicting
# versions. So we build two image variants from this one Dockerfile:
#   IOTC_SDK=lite       (default) -> standalone demo, X.509 direct MQTT  -> :latest
#   IOTC_SDK=greengrass           -> Greengrass component, IPC transport -> :greengrass
# For the greengrass variant we drop lite and install the greengrass extras
# (see greengrass/safety-vision/requirements-greengrass.txt). The app picks the
# matching transport at runtime via IOTC_TRANSPORT (app/iotc.py).
ARG IOTC_SDK=lite
COPY greengrass/safety-vision/requirements-greengrass.txt /app/requirements-greengrass.txt
RUN if [ "$IOTC_SDK" = "greengrass" ]; then \
        pip uninstall -y iotconnect-sdk-lite paho-mqtt || true; \
        pip install --no-cache-dir -r requirements-greengrass.txt; \
    fi

# Intel NPU (AI Boost) user-space: not in Ubuntu repos, so install Intel's
# release packages. Firmware is loaded host-side by the kernel intel_vpu driver,
# so only the level-zero backend + driver-compiler are needed here. This lets the
# detector run on the NPU, freeing the iGPU for the VLM. Placed after the pip
# layers so changing it doesn't bust the (slow) dependency cache.
ARG NPU_VER=v1.32.1
ARG NPU_TARBALL=linux-npu-driver-v1.32.1.20260422-24767473183-ubuntu2404.tar.gz
RUN apt-get update && apt-get install -y --no-install-recommends wget libtbb12 \
    && cd /tmp \
    && wget -q "https://github.com/intel/linux-npu-driver/releases/download/${NPU_VER}/${NPU_TARBALL}" -O npu.tgz \
    && tar xzf npu.tgz \
    && dpkg -i intel-level-zero-npu*.deb intel-driver-compiler-npu*.deb \
    && rm -rf /tmp/*.deb /tmp/*.tar.gz /tmp/npu.tgz /var/lib/apt/lists/*

# MCP client for cross-device hazard actions (app/hazard_actions.py talks to
# the host's iotc-mcp-server). Own layer, after the slow NPU/dep layers, so
# adding it didn't bust their cache.
RUN pip install --no-cache-dir mcp

# Application code and pre-converted models (baked in so nothing downloads at
# the venue). prepare_models.sh must have populated ./models before building.
COPY app /app/app
COPY models /app/models

# Credentials are NOT baked into the image — they are mounted at runtime
# (see compose) so the image stays shareable without leaking secrets.

# Link this image to its source repo on GitHub (shows the package on the repo,
# and lets GHCR inherit the repo's README/visibility).
LABEL org.opencontainers.image.source="https://github.com/mlamp99/iotc-nuc-vlm-demo"
LABEL org.opencontainers.image.description="Physical AI Construction VLM — Intel NUC + OpenVINO + /IOTCONNECT"

EXPOSE 8080

# Default to the demo; override with `python3 -m app.selftest` for pre-flight.
CMD ["python3", "-m", "app.main"]
