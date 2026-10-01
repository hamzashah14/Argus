#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — IAM setup
#
# Creates/updates:
#   aiops-lambda-role        — the fetch_logs / fetch_metrics tool Lambdas.
#                              Log reads are limited to <LOG_GROUP_PREFIX>/*.
#   aiops-bedrock-agent-role — the Bedrock Agent itself.
# (The trigger Lambda gets its own role, created by setup-alerts.sh, because
# its permissions reference the agent alias and SNS topic.)
#
# Re-run after changing MONITOR_REGION, BEDROCK_REGION or LOG_GROUP_PREFIX.
# Usage: ./setup-iam.sh
# =============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

require MONITOR_REGION BEDROCK_REGION
require_region MONITOR_REGION BEDROCK_REGION
ACCOUNT_ID="$(aws_account_id)"

echo ""
echo "AIOps — IAM setup (account $ACCOUNT_ID)"
echo ""

ensure_role() { # name trust_json description
  if aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$1" --policy-document "$2"
    echo "  ✓ Role exists, trust policy refreshed: $1"
  else
    aws iam create-role --role-name "$1" --assume-role-policy-document "$2" --description "$3" >/dev/null
    echo "  ✓ Created role: $1"
  fi
}

# -----------------------------------------------------------------------------
# Tool Lambdas role
# -----------------------------------------------------------------------------
echo "[1/2] $TOOLS_ROLE_NAME"
ensure_role "$TOOLS_ROLE_NAME" '{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}' "AIOps tool Lambdas — read EC2/CWAgent logs and metrics"

aws iam attach-role-policy --role-name "$TOOLS_ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

LOG_GROUPS_ARN="arn:aws:logs:${MONITOR_REGION}:${ACCOUNT_ID}:log-group:${LOG_GROUP_PREFIX}/*"
aws iam put-role-policy --role-name "$TOOLS_ROLE_NAME" --policy-name "aiops-lambda-inline-policy" --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {
      \"Sid\": \"ReadMonitoredLogGroupsOnly\",
      \"Effect\": \"Allow\",
      \"Action\": [\"logs:StartQuery\", \"logs:FilterLogEvents\", \"logs:DescribeLogStreams\"],
      \"Resource\": \"$LOG_GROUPS_ARN\"
    },
    {
      \"Sid\": \"LogsActionsWithoutResourceScoping\",
      \"Effect\": \"Allow\",
      \"Action\": [\"logs:GetQueryResults\", \"logs:StopQuery\", \"logs:DescribeLogGroups\"],
      \"Resource\": \"*\"
    },
    {
      \"Sid\": \"ReadMetrics\",
      \"Effect\": \"Allow\",
      \"Action\": [\"cloudwatch:GetMetricStatistics\", \"cloudwatch:GetMetricData\", \"cloudwatch:ListMetrics\"],
      \"Resource\": \"*\"
    }
  ]
}"
echo "  ✓ Log reads limited to $LOG_GROUP_PREFIX/* in $MONITOR_REGION; metrics read-only"

# An earlier version granted bedrock:InvokeAgent + sns:Publish on this shared
# role; that now lives on the trigger Lambda's own role.
if aws iam delete-role-policy --role-name "$TOOLS_ROLE_NAME" --policy-name "aiops-alerting-inline-policy" 2>/dev/null; then
  echo "  ✓ Removed old aiops-alerting-inline-policy from $TOOLS_ROLE_NAME"
fi

# -----------------------------------------------------------------------------
# Bedrock Agent role
# -----------------------------------------------------------------------------
echo ""
echo "[2/2] $AGENT_ROLE_NAME"
ensure_role "$AGENT_ROLE_NAME" "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Effect\": \"Allow\",
    \"Principal\": {\"Service\": \"bedrock.amazonaws.com\"},
    \"Action\": \"sts:AssumeRole\",
    \"Condition\": {
      \"StringEquals\": {\"aws:SourceAccount\": \"$ACCOUNT_ID\"},
      \"ArnLike\": {\"aws:SourceArn\": \"arn:aws:bedrock:${BEDROCK_REGION}:${ACCOUNT_ID}:agent/*\"}
    }
  }]
}" "Bedrock Agent — AIOps assistant (Kira)"

# foundation-model/* across regions + inference-profile/*: cross-region
# inference profiles route requests to the model in other regions.
aws iam put-role-policy --role-name "$AGENT_ROLE_NAME" --policy-name "aiops-bedrock-agent-inline-policy" --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {
      \"Sid\": \"InvokeToolLambdas\",
      \"Effect\": \"Allow\",
      \"Action\": \"lambda:InvokeFunction\",
      \"Resource\": [
        \"arn:aws:lambda:${BEDROCK_REGION}:${ACCOUNT_ID}:function:${FETCH_LOGS_FUNC}\",
        \"arn:aws:lambda:${BEDROCK_REGION}:${ACCOUNT_ID}:function:${FETCH_METRICS_FUNC}\"
      ]
    },
    {
      \"Sid\": \"InvokeModel\",
      \"Effect\": \"Allow\",
      \"Action\": [\"bedrock:InvokeModel\", \"bedrock:InvokeModelWithResponseStream\", \"bedrock:GetInferenceProfile\", \"bedrock:GetFoundationModel\"],
      \"Resource\": [
        \"arn:aws:bedrock:*::foundation-model/*\",
        \"arn:aws:bedrock:${BEDROCK_REGION}:${ACCOUNT_ID}:inference-profile/*\"
      ]
    }
  ]
}"
echo "  ✓ Tool Lambda invoke + model invoke"

echo ""
echo "Done. Next: ./setup-lambdas.sh"
echo ""
