#!/bin/bash
# Greengrass run lifecycle: start the container in the foreground so the Nucleus
# owns its lifecycle (the matching `shutdown` script runs `docker compose down`).
set -e

cd "$(dirname "$0")"

# --- Phase B: forward the Nucleus IPC socket into the container ---------------
# Nucleus sets AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT + SVCUID +
# AWS_IOT_THING_NAME + AWS_REGION in this script's environment. We re-export the
# socket path under GG_IPC_SOCKET (referenced by docker-compose.gg.yml for both
# the env var and the bind mount). When IOTC_TRANSPORT=lite (Phase A) these are
# simply unused by the app.
export GG_IPC_SOCKET="${AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT:-/dev/null}"
export SVCUID="${SVCUID:-}"
export AWS_IOT_THING_NAME="${AWS_IOT_THING_NAME:-}"
export AWS_REGION="${AWS_REGION:-}"

echo "Starting Safety Vision (transport=${IOTC_TRANSPORT:-lite}, ipc=${GG_IPC_SOCKET})"

exec docker compose -f docker-compose.gg.yml up
