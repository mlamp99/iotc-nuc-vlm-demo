#!/bin/bash
# Provision THIS machine as an AWS IoT Greengrass v2 core device (Nucleus Classic)
# using an /IOTCONNECT connection kit. Must be run as root.
#
#   sudo bash greengrass/install-nucleus.sh [path-to-connectionKit.zip]
#
# Defaults to the kit stored at greengrass/connection-kit/*.zip. Installs Java if
# missing, downloads the pinned Nucleus, and registers it as a system service.
set -euo pipefail

GG_VERSION="2.16.1"
GG_ROOT="/greengrass/v2"
# PERMANENT home for the device certs. config.yaml references them via
# {{config_dir}}, so this dir must persist for the life of the device — do NOT
# use /tmp (wiped on reboot) and do NOT delete it after install.
CERT_DIR="/greengrass/certs"
HERE="$(cd "$(dirname "$0")" && pwd)"
KIT_ZIP="${1:-$(ls -1 "${HERE}"/connection-kit/*.zip 2>/dev/null | head -n1)}"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run as root:  sudo bash $0 [kit.zip]" >&2
  exit 1
fi
if [[ -z "${KIT_ZIP}" || ! -f "${KIT_ZIP}" ]]; then
  echo "ERROR: connection kit zip not found. Pass it as the first argument." >&2
  exit 2
fi
echo ">> Using connection kit: ${KIT_ZIP}"

# 1. Java (Nucleus Classic is a JVM runtime)
if ! command -v java >/dev/null 2>&1; then
  echo ">> Installing default-jdk..."
  apt-get update -y
  apt-get install -y default-jdk unzip
fi

# 2. Stage the kit into the PERMANENT cert dir. config.yaml references certs via
#    {{config_dir}}, which the installer resolves to the directory of the
#    --init-config file — so config.yaml + the 3 cert files must live together in
#    a location that persists. (A previous version staged these in /tmp and
#    deleted them, which left Greengrass pointing at missing files ->
#    AWS_ERROR_FILE_INVALID_PATH and no MQTT connection.)
mkdir -p "${CERT_DIR}"
unzip -o "${KIT_ZIP}" -d "${CERT_DIR}" >/dev/null
chmod 700 "${CERT_DIR}"; chmod 600 "${CERT_DIR}"/* ; chown -R root:root "${CERT_DIR}"
# The /IOTCONNECT kit's config.yaml references certs via a {{config_dir}}
# placeholder that the standard AWS Greengrass (Classic) installer does NOT
# expand — it would be copied verbatim into the effective config, leaving
# Greengrass trying to open "{{config_dir}}/AmazonRootCA1.pem"
# (AWS_ERROR_FILE_INVALID_PATH -> no MQTT). Substitute it with the real path.
sed -i "s|{{config_dir}}|${CERT_DIR}|g" "${CERT_DIR}/config.yaml"
echo ">> Staged kit to ${CERT_DIR} ($(ls "${CERT_DIR}" | tr '\n' ' '))"

# 3. Download the pinned Nucleus installer (temp is fine — only used during install)
INSTALLER_DIR="$(mktemp -d /tmp/gg-installer.XXXXXX)"
trap 'rm -rf "${INSTALLER_DIR}"' EXIT
echo ">> Downloading Greengrass ${GG_VERSION}..."
curl -fsSL "https://d2s8p88vqu9w66.cloudfront.net/releases/greengrass-${GG_VERSION}.zip" \
  -o "${INSTALLER_DIR}/gg.zip"
unzip -q -o "${INSTALLER_DIR}/gg.zip" -d "${INSTALLER_DIR}/GreengrassInstaller"

# 4. Install + register as a system service (manual provisioning: certs supplied
#    by the kit, so NO --provision flag).
echo ">> Installing Nucleus to ${GG_ROOT} as a system service..."
java -Droot="${GG_ROOT}" -Dlog.store=FILE \
  -jar "${INSTALLER_DIR}/GreengrassInstaller/lib/Greengrass.jar" \
  --init-config "${CERT_DIR}/config.yaml" \
  --component-default-user root:root \
  --setup-system-service true

echo
echo ">> Done. Check status with:"
echo "     sudo systemctl status greengrass"
echo "     sudo tail -f ${GG_ROOT}/logs/greengrass.log"
echo "   The device should show 'Last Connection' in the /IOTCONNECT console."
