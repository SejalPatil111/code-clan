#!/usr/bin/env bash
# =============================================================================
# CodeClan — Install and Register gVisor (`runsc`) on Ubuntu/Debian Linux Hosts
#
# Usage:
#   sudo bash scripts/install-gvisor-linux.sh
# =============================================================================
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: gVisor (runsc) requires a Linux host." >&2
  exit 1
fi

ARCH="$(uname -m)"
if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "aarch64" ]]; then
  echo "ERROR: Unsupported architecture ${ARCH} for gVisor." >&2
  exit 1
fi

echo "[1/5] Installing prerequisite packages..."
apt-get update -y
apt-get install -y apt-transport-https ca-certificates curl gnupg

echo "[2/5] Adding official gVisor APT signing key and repository..."
curl -fsSL https://gvisor.dev/archive.key | gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
  > /etc/apt/sources.list.d/gvisor.list

echo "[3/5] Installing runsc package..."
apt-get update -y
apt-get install -y runsc

echo "[4/5] Registering runsc OCI runtime in /etc/docker/daemon.json..."
runsc install
systemctl restart docker

echo "[5/5] Verifying gVisor (runsc) runtime..."
docker info --format 'Registered Runtimes: {{json .Runtimes}}'
docker run --rm --runtime=runsc alpine uname -a
docker run --rm --runtime=runsc alpine dmesg | head -n 5

echo "SUCCESS: gVisor (runsc) is installed, registered with Docker, and verified!"
