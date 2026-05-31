#!/usr/bin/env bash
# Fetch the image tarball from S3 and docker-load it. Run on the DEVICE (Docker
# must already be installed: scripts/install-docker.sh). Two modes:
#
#   A) presigned URL (no AWS creds, just curl/wget):
#        S3_URL='https://my-bucket.s3...' bash scripts/fetch-from-s3.sh
#   B) s3:// URI (device has AWS credentials):
#        S3_URI='s3://my-bucket/physical-ai/physical-ai-demo.tar.gz' bash scripts/fetch-from-s3.sh
set -euo pipefail

OUT="${OUT:-/tmp/physical-ai-demo.tar.gz}"

if [ -n "${S3_URL:-}" ]; then
  echo ">> Downloading via presigned URL..."
  if command -v curl >/dev/null; then curl -fSL "$S3_URL" -o "$OUT"
  elif command -v wget >/dev/null; then wget -O "$OUT" "$S3_URL"
  else echo "ERROR: need curl or wget." >&2; exit 1; fi
  # try the sibling checksum (strip any query string from the URL first)
  base="${S3_URL%%\?*}"
  (curl -fsSL "${base}.sha256" -o "${OUT}.sha256" 2>/dev/null) || true
elif [ -n "${S3_URI:-}" ]; then
  command -v aws >/dev/null || { echo "ERROR: aws CLI not found for S3_URI mode." >&2; exit 1; }
  echo ">> Downloading via aws s3 cp..."
  aws s3 cp "$S3_URI" "$OUT"
  aws s3 cp "${S3_URI}.sha256" "${OUT}.sha256" 2>/dev/null || true
else
  echo "ERROR: set S3_URL (presigned) or S3_URI (s3://...)." >&2
  exit 1
fi

if [ -f "${OUT}.sha256" ]; then
  echo ">> Verifying checksum..."
  want="$(awk '{print $1}' "${OUT}.sha256")"
  got="$(sha256sum "$OUT" | awk '{print $1}')"
  if [ "$want" = "$got" ]; then echo "   checksum OK"; else echo "   CHECKSUM MISMATCH — aborting." >&2; exit 1; fi
fi

echo ">> docker load (this unpacks ~17GB; takes a minute)..."
docker load < "$OUT"
echo
echo ">> Loaded. Next:"
echo "   cp .env.example .env   # edit RENDER_GID/VIDEO_GID/CAMERA_SOURCE"
echo "   put credentials/ next to docker-compose.yml, then: docker compose up -d"
