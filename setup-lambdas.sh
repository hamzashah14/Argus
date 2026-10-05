#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — tool Lambda deployment
#
# Creates/updates aiops-fetch-logs and aiops-fetch-metrics in BEDROCK_REGION
# (Bedrock Agents can only call Lambdas in their own region). They read logs
# and metrics from MONITOR_REGION, passed in as an environment variable.
#
# Re-run after any change under lambda/fetch_logs or lambda/fetch_metrics.
# Usage: ./setup-lambdas.sh
# =============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

require MONITOR_REGION BEDROCK_REGION INSTANCE_IDS LOG_CURSOR_SECRET
require_region MONITOR_REGION BEDROCK_REGION
ACCOUNT_ID="$(aws_account_id)"
TOOLS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${TOOLS_ROLE_NAME}"

aws iam get-role --role-name "$TOOLS_ROLE_NAME" >/dev/null 2>&1 || die "IAM role $TOOLS_ROLE_NAME not found — run ./setup-iam.sh first."

ENV_JSON="$("$KIRA_PYTHON" -c 'import json,os; keys=["MONITOR_REGION","LOG_GROUP_PREFIX","LOG_CURSOR_SECRET","ENVIRONMENT","EXPECTED_ACCOUNT_ID","DISK_PATH"]; values={k:os.environ[k] for k in keys}; values["ALLOWED_INSTANCE_IDS"]=os.environ["INSTANCE_IDS"]; print(json.dumps({"Variables":values}))')"

echo ""
echo "AIOps — tool Lambdas in $BEDROCK_REGION (reading $MONITOR_REGION)"
echo ""
# 60s: fetch_logs runs up to three Logs Insights queries and bounds its own
# polling to the time Lambda has left.
deploy_lambda "$FETCH_LOGS_FUNC" "$ROOT_DIR/lambda/fetch_logs" "$BEDROCK_REGION" "$TOOLS_ROLE_ARN" 60 256 "$ENV_JSON" "AIOps fetch_logs tool"
deploy_lambda "$FETCH_METRICS_FUNC" "$ROOT_DIR/lambda/fetch_metrics" "$BEDROCK_REGION" "$TOOLS_ROLE_ARN" 30 128 "$ENV_JSON" "AIOps fetch_metrics tool"

echo ""
echo "Done. Next: ./deploy.sh"
echo ""
