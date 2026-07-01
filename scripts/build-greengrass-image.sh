#!/bin/bash
# Build (and optionally push) the GREENGRASS variant of the image.
#
# This image swaps the lite SDK for the /IOTCONNECT Greengrass SDK (the two
# cannot coexist). The standalone demo keeps using the default ':latest' image
# built by build-and-save.sh; the Greengrass component uses ':greengrass'.
#
#   ./scripts/build-greengrass-image.sh           # build only
#   PUSH=1 ./scripts/build-greengrass-image.sh     # build + push (needs docker login ghcr.io)
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-ghcr.io/mlamp99/physical-ai-demo:greengrass}"

docker build --build-arg IOTC_SDK=greengrass -t "$IMAGE" .

if [[ "${PUSH:-0}" == "1" ]]; then
  docker push "$IMAGE"
  echo "Pushed $IMAGE"
else
  echo "Built $IMAGE (set PUSH=1 to push)"
fi
