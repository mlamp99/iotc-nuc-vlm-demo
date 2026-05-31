#!/usr/bin/env bash
# Upload the shipped image tarball to S3 so devices can fetch it. Run on the
# BUILD machine (needs the AWS CLI + credentials: `aws configure`).
#
#   S3_URI=s3://my-bucket/physical-ai/ bash scripts/push-to-s3.sh
#   PRESIGN=1 S3_URI=s3://my-bucket/physical-ai/ bash scripts/push-to-s3.sh   # also print a presigned URL
#
# The image contains NO secrets (credentials are mounted at runtime), so a
# presigned URL is a low-risk way to let a device download with no AWS creds.
set -euo pipefail

: "${S3_URI:?Set S3_URI, e.g. S3_URI=s3://my-bucket/physical-ai/}"
TARBALL="${TARBALL:-ship/physical-ai-demo.tar.gz}"
PRESIGN_EXPIRY="${PRESIGN_EXPIRY:-604800}"   # 7 days (max for SigV4 presign)

[ -f "$TARBALL" ] || { echo "ERROR: $TARBALL not found (run scripts/build-and-save.sh first)." >&2; exit 1; }
command -v aws >/dev/null || { echo "ERROR: aws CLI not found. Install it and run 'aws configure'." >&2; exit 1; }

KEY="${S3_URI%/}/$(basename "$TARBALL")"

echo ">> Computing checksum..."
sha256sum "$TARBALL" > "${TARBALL}.sha256"

echo ">> Uploading $(du -h "$TARBALL" | cut -f1) -> $KEY (multipart auto)..."
aws s3 cp "$TARBALL" "$KEY"
aws s3 cp "${TARBALL}.sha256" "${KEY}.sha256"

echo
echo ">> Done. On each device (pick one):"
echo "   A) no AWS creds needed — presigned URL:"
if [ "${PRESIGN:-0}" = "1" ]; then
  url="$(aws s3 presign "$KEY" --expires-in "$PRESIGN_EXPIRY")"
  echo "      S3_URL='$url' bash scripts/fetch-from-s3.sh"
  echo "      (valid ${PRESIGN_EXPIRY}s)"
else
  echo "      re-run with PRESIGN=1 to generate the URL, then:"
  echo "      S3_URL='<presigned-url>' bash scripts/fetch-from-s3.sh"
fi
echo "   B) device has AWS creds:"
echo "      S3_URI='$KEY' bash scripts/fetch-from-s3.sh"
