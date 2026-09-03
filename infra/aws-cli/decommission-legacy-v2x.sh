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
AMPLIFY_REGION="${AMPLIFY_REGION:-us-west-2}"
export AWS_REGION

TABLE_NAME="${TABLE_NAME:-v2x_detections}"
INGEST_LAMBDA_NAME="${INGEST_LAMBDA_NAME:-v2x-detections-ingest}"
READ_LAMBDA_NAME="${READ_LAMBDA_NAME:-v2x-detections-read}"
API_NAME="${API_NAME:-v2x-detections-api}"
RULE_NAME="${RULE_NAME:-v2x_detections_to_ddb}"
IOT_POLICY_NAME="${IOT_POLICY_NAME:-v2x-edge-publish}"
READ_POLICY_NAME="${READ_POLICY_NAME:-v2x-detections-ddb-read}"
LAMBDA_ROLE_POLICY_NAME="${LAMBDA_ROLE_POLICY_NAME:-v2x-detections-ddb-put}"
AMPLIFY_APP_NAME="${AMPLIFY_APP_NAME:-v2x-viewer}"

echo "Decommissioning legacy V2X resources..."
echo "Camera video is local to path-rfs; no Kinesis Video resources are part of this legacy stack."

APP_ID="$(AWS_REGION="${AMPLIFY_REGION}" aws amplify list-apps --max-results 100 --query "apps[?name==\`${AMPLIFY_APP_NAME}\`].appId | [0]" --output text 2>/dev/null || true)"
if [[ -n "${APP_ID}" && "${APP_ID}" != "None" ]]; then
  AWS_REGION="${AMPLIFY_REGION}" aws amplify delete-app --app-id "${APP_ID}" >/dev/null || true
fi

API_ID="$(aws apigatewayv2 get-apis --query "Items[?Name==\`${API_NAME}\`].ApiId | [0]" --output text 2>/dev/null || true)"
if [[ -n "${API_ID}" && "${API_ID}" != "None" ]]; then
  aws apigatewayv2 delete-api --api-id "${API_ID}" >/dev/null || true
fi

if aws iot get-topic-rule --rule-name "${RULE_NAME}" >/dev/null 2>&1; then
  aws iot delete-topic-rule --rule-name "${RULE_NAME}" >/dev/null || true
fi

if aws iot get-policy --policy-name "${IOT_POLICY_NAME}" >/dev/null 2>&1; then
  TARGETS="$(aws iot list-targets-for-policy --policy-name "${IOT_POLICY_NAME}" --query targets --output text 2>/dev/null || true)"
  for target in ${TARGETS}; do
    [[ -z "${target}" ]] && continue
    aws iot detach-policy --policy-name "${IOT_POLICY_NAME}" --target "${target}" >/dev/null || true
  done
  aws iot delete-policy --policy-name "${IOT_POLICY_NAME}" >/dev/null || true
fi

for function_name in "${READ_LAMBDA_NAME}" "${INGEST_LAMBDA_NAME}"; do
  if aws lambda get-function --function-name "${function_name}" >/dev/null 2>&1; then
    role_arn="$(aws lambda get-function --function-name "${function_name}" --query Configuration.Role --output text 2>/dev/null || true)"
    if [[ -n "${role_arn}" && "${role_arn}" != "None" ]]; then
      role_name="${role_arn##*/}"
      aws iam delete-role-policy --role-name "${role_name}" --policy-name "${READ_POLICY_NAME}" >/dev/null || true
      aws iam delete-role-policy --role-name "${role_name}" --policy-name "${LAMBDA_ROLE_POLICY_NAME}" >/dev/null || true
    fi
    aws lambda delete-function --function-name "${function_name}" >/dev/null || true
  fi
done

if aws dynamodb describe-table --table-name "${TABLE_NAME}" >/dev/null 2>&1; then
  aws dynamodb delete-table --table-name "${TABLE_NAME}" >/dev/null || true
fi

echo "Legacy V2X resources scheduled for deletion."
