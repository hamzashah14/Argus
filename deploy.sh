#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — Bedrock Agent deployment
#
# Creates the agent, or updates an existing one in place: instruction (from
# agent-instruction.txt), model, role, both action groups' schemas, removal of
# stale action groups, account-scoped Lambda permissions, then prepares it and
# waits until it's PREPARED. Safe to re-run after any change.
#
# Requires: ./setup-iam.sh and ./setup-lambdas.sh already run, and boto3
# installed locally (pip install -r requirements.txt).
# Usage: ./deploy.sh
# =============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

require BEDROCK_REGION BEDROCK_MODEL_ID
require_region BEDROCK_REGION
python3 -c "import boto3" 2>/dev/null || die "boto3 isn't installed locally — run: pip install -r requirements.txt"
ACCOUNT_ID="$(aws_account_id)"

echo ""
echo "AIOps — Bedrock Agent '$AGENT_NAME' in $BEDROCK_REGION, model $BEDROCK_MODEL_ID"
echo ""
ACCOUNT_ID="$ACCOUNT_ID" AGENT_ROLE_NAME="$AGENT_ROLE_NAME" \
  FETCH_LOGS_FUNC="$FETCH_LOGS_FUNC" FETCH_METRICS_FUNC="$FETCH_METRICS_FUNC" \
  python3 "$ROOT_DIR/scripts/deploy_agent.py"
