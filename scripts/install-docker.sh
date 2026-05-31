#!/usr/bin/env bash
# Installs Docker Engine + Compose plugin on Ubuntu (run on BOTH your NUC 16
# and the target device). Requires sudo and internet.
#
#   sudo bash scripts/install-docker.sh
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo bash scripts/install-docker.sh" >&2
  exit 1
fi

echo ">> Removing any old/conflicting Docker packages..."
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  apt-get remove -y "$pkg" 2>/dev/null || true
done

echo ">> Installing prerequisites..."
apt-get update
apt-get install -y ca-certificates curl gnupg

echo ">> Adding Docker's official GPG key and repository..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# shellcheck source=/dev/null
. /etc/os-release
codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $codename stable" \
  > /etc/apt/sources.list.d/docker.list

echo ">> Installing Docker Engine + Compose plugin..."
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

echo ">> Adding ${SUDO_USER:-$USER} to the docker group (no sudo for docker after re-login)..."
usermod -aG docker "${SUDO_USER:-$USER}" || true

systemctl enable --now docker

echo
echo ">> Done. Versions:"
docker --version
docker compose version
echo
echo ">> Log out and back in (or run: newgrp docker) so group membership takes effect."
