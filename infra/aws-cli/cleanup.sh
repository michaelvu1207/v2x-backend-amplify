#!/usr/bin/env bash
set -euo pipefail

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing dependency: $1" >&2
    exit 1
  }
}

need aws
need jq

AWS_REGION="${AWS_REGION:-us-west-1}"
export AWS_REGION

TABLE_NAME="${TABLE_NAME:-v2x-backend-detections}"
LAMBDA_NAME="${LAMBDA_NAME:-v2x-backend-ingest}"
READ_LAMBDA_NAME="${READ_LAMBDA_NAME:-v2x-backend-read}"
API_NAME="${API_NAME:-v2x-backend-api}"
RULE_NAME="${RULE_NAME:-v2x_backend_detections_to_ddb}"
IOT_POLICY_NAME="${IOT_POLICY_NAME:-v2x-backend-edge-publish}"
THING_NAME="${THING_NAME:-edge-device-001}"
LAMBDA_ROLE_POLICY_NAME="${LAMBDA_ROLE_POLICY_NAME:-v2x-backend-detections-ddb-put}"
READ_POLICY_NAME="${READ_POLICY_NAME:-v2x-backend-detections-ddb-read}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

echo "Cleaning up in ${AWS_REGION}..."
echo "Camera video is local to path-rfs; this cleanup manages no Kinesis Video resources."

if aws iot get-topic-rule --rule-name "${RULE_NAME}" >/dev/null 2>&1; then
  aws iot delete-topic-rule --rule-name "${RULE_NAME}" >/dev/null
fi

# Best-effort: detach & delete cert(s) attached to thing
if aws iot describe-thing --thing-name "${THING_NAME}" >/dev/null 2>&1; then
  PRINCIPALS="$(aws iot list-thing-principals --thing-name "${THING_NAME}" --query principals --output json)"
  echo "${PRINCIPALS}" | jq -r '.[]?' | while read -r principal; do
    [[ -z "${principal}" ]] && continue
    aws iot detach-thing-principal --thing-name "${THING_NAME}" --principal "${principal}" >/dev/null || true
    aws iot detach-policy --policy-name "${IOT_POLICY_NAME}" --target "${principal}" >/dev/null || true
    CERT_ID="$(basename "${principal}")"
    aws iot update-certificate --certificate-id "${CERT_ID}" --new-status INACTIVE >/dev/null || true
    aws iot delete-certificate --certificate-id "${CERT_ID}" --force-delete >/dev/null || true
  done
  aws iot delete-thing --thing-name "${THING_NAME}" >/dev/null || true
fi

if aws iot get-policy --policy-name "${IOT_POLICY_NAME}" >/dev/null 2>&1; then
  aws iot delete-policy --policy-name "${IOT_POLICY_NAME}" >/dev/null || true
fi

API_ID="$(aws apigatewayv2 get-apis --query "Items[?Name==\`${API_NAME}\`].ApiId | [0]" --output text 2>/dev/null || true)"
if [[ -n "${API_ID}" && "${API_ID}" != "None" ]]; then
  aws apigatewayv2 delete-api --api-id "${API_ID}" >/dev/null || true
fi

ROLE_NAME="${LAMBDA_NAME}-role"
if aws lambda get-function --function-name "${LAMBDA_NAME}" >/dev/null 2>&1; then
  # Best-effort: remove the inline policy we may have added to the Lambda execution role.
  ROLE_ARN="$(aws lambda get-function --function-name "${LAMBDA_NAME}" --query Configuration.Role --output text 2>/dev/null || true)"
  if [[ -n "${ROLE_ARN}" && "${ROLE_ARN}" != "None" ]]; then
    ROLE_NAME_FROM_ARN="${ROLE_ARN##*/}"
    aws iam delete-role-policy --role-name "${ROLE_NAME_FROM_ARN}" --policy-name "${LAMBDA_ROLE_POLICY_NAME}" >/dev/null || true
  fi
  aws lambda delete-function --function-name "${LAMBDA_NAME}" >/dev/null
fi

if aws lambda get-function --function-name "${READ_LAMBDA_NAME}" >/dev/null 2>&1; then
  ROLE_ARN="$(aws lambda get-function --function-name "${READ_LAMBDA_NAME}" --query Configuration.Role --output text 2>/dev/null || true)"
  if [[ -n "${ROLE_ARN}" && "${ROLE_ARN}" != "None" ]]; then
    ROLE_NAME_FROM_ARN="${ROLE_ARN##*/}"
    aws iam delete-role-policy --role-name "${ROLE_NAME_FROM_ARN}" --policy-name "${READ_POLICY_NAME}" >/dev/null || true
  fi
  aws lambda delete-function --function-name "${READ_LAMBDA_NAME}" >/dev/null
fi

if aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  aws iam detach-role-policy --role-name "${ROLE_NAME}" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole >/dev/null || true
  aws iam delete-role-policy --role-name "${ROLE_NAME}" --policy-name "${LAMBDA_NAME}-ddb-put" >/dev/null || true
  aws iam delete-role --role-name "${ROLE_NAME}" >/dev/null || true
fi

if aws dynamodb describe-table --table-name "${TABLE_NAME}" >/dev/null 2>&1; then
  aws dynamodb delete-table --table-name "${TABLE_NAME}" >/dev/null
  aws dynamodb wait table-not-exists --table-name "${TABLE_NAME}" || true
fi

echo "Cleanup complete."
