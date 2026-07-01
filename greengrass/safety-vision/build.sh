#!/bin/bash
# Build the Greengrass component artifact + recipe with GDK.
#
# Produces:
#   greengrass-build/recipes/recipe.yaml          (upload/register in /IOTCONNECT)
#   greengrass-build/artifacts/.../safety-vision.zip
set -e
cd "$(dirname "$0")"

if ! which gdk > /dev/null 2>&1; then
  python3 -m pip install -U git+https://github.com/aws-greengrass/aws-greengrass-gdk-cli.git@v1.6.2
fi

gdk component build

echo
echo "Build complete."
echo "  Recipe:    greengrass-build/recipes/recipe.yaml"
echo "  Artifact:  greengrass-build/artifacts/<component>/<version>/safety-vision.zip"
echo
echo "Next: 'gdk component publish' (uploads to S3 + registers), then add the"
echo "component to a deployment / firmware in the /IOTCONNECT console."
