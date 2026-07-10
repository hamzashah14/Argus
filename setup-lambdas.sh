#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — Lambda Deployment Script
#
# What this script does:
#   - Creates/updates the 3 Lambda functions required by the Bedrock Agent
#   - Uploads code from the repo's lambda/* directories
#   - Sets runtime/handler/timeout and required environment variables
#
# Usage:
#   chmod +x setup-lambdas.sh
#   ./setup-lambdas.sh --prometheus-url http://<PROMETHEUS_ELB_URL>:9090
#
# Notes:
#   - This script will not modify IAM roles (use setup-iam.sh for that)
#   - Execution role used: aiops-lambda-role
# =============================================================================

set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

LAMBDA_ROLE_NAME="aiops-lambda-role"
LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"

# Defaults (can be overridden via env vars)
RUNTIME="python3.12"
TIMEOUT_SECONDS="30"
HANDLER="lambda_function.lambda_handler"

PROMETHEUS_URL_ARG=""

usage() {
  echo "Usage: $0 --prometheus-url http://<PROMETHEUS_ELB_URL>:9090"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prometheus-url)
      PROMETHEUS_URL_ARG="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      ;;
  esac
done

if [[ -z "$PROMETHEUS_URL_ARG" ]]; then
  usage
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "============================================="
echo " AIOps — Lambda Deployment"
echo " Account : $ACCOUNT_ID"
echo " Region  : $REGION"
echo "============================================="
echo ""

echo "[0/4] Validating prerequisites..."
if ! aws iam get-role --role-name "$LAMBDA_ROLE_NAME" --output json &>/dev/null; then
  echo "  ✗ IAM role '$LAMBDA_ROLE_NAME' not found. Run: ./setup-iam.sh first."
  exit 1
fi

echo "  ✓ IAM role exists: $LAMBDA_ROLE_NAME"

echo "[1/4] Checking Lambda function existence..."

for FUNC in aiops-fetch-logs aiops-fetch-metrics aiops-fetch-health; do
  if aws lambda get-function --function-name "$FUNC" --region "$REGION" &>/dev/null; then
    echo "  ✓ Exists: $FUNC"
  else
    echo "  - Will create: $FUNC"
  fi
done

create_or_update_lambda() {
  local func_name="$1"
  local src_dir="$2"
  local description="$3"
  local extra_env_json="$4" # JSON object string like: {"KEY":"VAL"}

  local zip_path="${SCRIPT_DIR}/.tmp_${func_name}.zip"

  # Build zip (lambda expects files at root, so include folder contents)
  rm -f "$zip_path"
  (cd "$src_dir" && zip -qr "$zip_path" .)

  local env_json="{}"
  if [[ "$extra_env_json" != "" ]]; then
    env_json="$extra_env_json"
  fi

  # Ensure env vars include required Prometheus URL for relevant lambdas
  if [[ "$func_name" == "aiops-fetch-metrics" || "$func_name" == "aiops-fetch-health" ]]; then
    # Merge by letting user-provided env_json win only if they explicitly set PROMETHEUS_URL
    # (simple approach: if PROMETHEUS_URL already in extra_env_json, don't override)
    if echo "$env_json" | grep -q '"PROMETHEUS_URL"'; then
      true
    else
      # append PROMETHEUS_URL
      env_json=$(python3 - <<PY
import json
env = json.loads('''$env_json''')
env['PROMETHEUS_URL'] = '''$PROMETHEUS_URL_ARG'''
print(json.dumps(env))
PY
)
    fi
  fi

  echo "  - Deploying: $func_name"

  if aws lambda get-function --function-name "$func_name" --region "$REGION" &>/dev/null; then
    # Update code
    aws lambda update-function-code \
      --function-name "$func_name" \
      --zip-file "fileb://$zip_path" \
      --region "$REGION" >/dev/null

    # Update configuration + env
    aws lambda update-function-configuration \
      --function-name "$func_name" \
      --runtime "$RUNTIME" \
      --handler "$HANDLER" \
      --timeout "$TIMEOUT_SECONDS" \
      --environment "Variables=$(echo "$env_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("{"+",".join([f"\\\"{k}\\\":\\\"{v}\\\"" for k,v in d.items()])+"}")')" \
      --region "$REGION" >/dev/null

    echo "    ✓ Updated code/config"
  else
    # Create
    aws lambda create-function \
      --function-name "$func_name" \
      --runtime "$RUNTIME" \
      --role "$LAMBDA_ROLE_ARN" \
      --handler "$HANDLER" \
      --timeout "$TIMEOUT_SECONDS" \
      --code "ZipFile=fileb://$zip_path" \
      --description "$description" \
      --environment "Variables=$(echo "$env_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("{"+",".join([f"\\\"{k}\\\":\\\"{v}\\\"" for k,v in d.items()])+"}")')" \
      --region "$REGION" >/dev/null

    echo "    ✓ Created"
  fi

  rm -f "$zip_path"
}

# Deploy each lambda with minimal required env vars
# fetch_logs: no extra env required
create_or_update_lambda "aiops-fetch-logs" "$SCRIPT_DIR/lambda/fetch_logs" "AIOps fetch_logs" "{}"

# fetch_metrics: set PROMETHEUS_URL
create_or_update_lambda "aiops-fetch-metrics" "$SCRIPT_DIR/lambda/fetch_metrics" "AIOps fetch_metrics" "{}"

# fetch_health: set PROMETHEUS_URL (and optionally cluster/namespace via env if you want)
create_or_update_lambda "aiops-fetch-health" "$SCRIPT_DIR/lambda/fetch_health" "AIOps fetch_service_health" "{}"

echo ""
echo "============================================="
echo " Done! Lambda functions deployed/updated."
echo " Functions: aiops-fetch-logs, aiops-fetch-metrics, aiops-fetch-health"
echo " Prometheus URL set to: $PROMETHEUS_URL_ARG"
echo "============================================="
echo ""

