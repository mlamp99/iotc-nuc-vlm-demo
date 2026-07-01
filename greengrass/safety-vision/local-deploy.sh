#!/bin/bash
# Build and deploy this component to the LOCAL Greengrass core for development.
# Requires the Greengrass CLI (aws.greengrass.Cli) to be deployed on this device
# and a Greengrass install at GG_ROOT (default /greengrass/v2).
set -e
cd "$(dirname "$0")"

GG_ROOT="${GG_ROOT:-/greengrass/v2}"
COMPONENT_NAME="io.iotconnect.example.IotConnectSafetyVision"
VERSION="1.0.1"

bash build.sh

sudo "${GG_ROOT}/bin/greengrass-cli" deployment create \
  --recipeDir greengrass-build/recipes \
  --artifactDir greengrass-build/artifacts \
  --merge "${COMPONENT_NAME}=${VERSION}"

echo
echo "Local deployment requested. Watch logs with:"
echo "  sudo tail -f ${GG_ROOT}/logs/${COMPONENT_NAME}.log"
