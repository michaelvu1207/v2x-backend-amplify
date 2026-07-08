#!/usr/bin/env bash
set -euo pipefail

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing dependency: $1" >&2
    exit 1
  }
}

need aws

AWS_REGION="${AWS_REGION:-us-west-1}"
export AWS_REGION

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
STATE_BUCKET="${STATE_BUCKET:-v2x-backend-state-${ACCOUNT_ID}-${AWS_REGION}}"

aws s3api head-bucket --bucket "${STATE_BUCKET}" >/dev/null

aws s3api put-public-access-block \
  --bucket "${STATE_BUCKET}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null

aws s3api put-bucket-acl \
  --bucket "${STATE_BUCKET}" \
  --acl private >/dev/null 2>&1 || true

if aws s3api get-bucket-policy --bucket "${STATE_BUCKET}" >/dev/null 2>&1; then
  aws s3api delete-bucket-policy --bucket "${STATE_BUCKET}" >/dev/null
fi

echo "Done."
echo "State bucket hardened: ${STATE_BUCKET}"
