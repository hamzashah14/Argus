#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — Bedrock Agent Deployment Script
#
# What this script does:
#   - Creates the Bedrock Agent (aiops-assistant / Kira)
#   - Attaches all 3 action groups with OpenAPI schemas
#   - Prepares the agent
#
# What to do BEFORE running this script (on AWS Console):
#   1. Create IAM role: aiops-lambda-role  (for Lambda functions)
#   2. Create 3 Lambda functions and paste code from lambda/ directory
#   3. Add Bedrock invoke permission to each Lambda (or run the 3 commands below)
#   4. Create IAM role: aiops-bedrock-agent-role  (for Bedrock Agent)
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
# =============================================================================

set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AGENT_ROLE_NAME="aiops-bedrock-agent-role"
AGENT_NAME="aiops-assistant"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "============================================="
echo " AIOps — Bedrock Agent Deployment"
echo " Account : $ACCOUNT_ID"
echo " Region  : $REGION"
echo "============================================="
echo ""

# =============================================================================
# PRE-CHECK: Verify Lambda functions and agent role exist before proceeding
# =============================================================================
echo "[0/3] Pre-flight checks..."

for FUNC in aiops-fetch-logs aiops-fetch-metrics aiops-fetch-health; do
  if ! aws lambda get-function --function-name "$FUNC" --region "$REGION" &>/dev/null; then
    echo "  ✗ Lambda '$FUNC' not found in $REGION"
    echo "    Create it on the AWS Console first, then re-run this script."
    exit 1
  fi
  echo "  ✓ Lambda: $FUNC"
done

if ! aws iam get-role --role-name "$AGENT_ROLE_NAME" &>/dev/null; then
  echo "  ✗ IAM role '$AGENT_ROLE_NAME' not found"
  echo "    Create it on the AWS Console first, then re-run this script."
  exit 1
fi

AGENT_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${AGENT_ROLE_NAME}"
echo "  ✓ IAM role: $AGENT_ROLE_NAME"

# =============================================================================
# STEP 1: Update Lambda timeouts and add Bedrock invoke permissions
# =============================================================================
echo ""
echo "[1/3] Configuring Lambda functions..."

for FUNC in aiops-fetch-logs aiops-fetch-metrics aiops-fetch-health; do
  aws lambda update-function-configuration \
    --function-name "$FUNC" \
    --timeout 30 \
    --region "$REGION" \
    --query 'FunctionName' --output text > /dev/null
  echo "  ✓ $FUNC timeout set to 30s"
done

echo ""
echo "  Adding Bedrock invoke permissions..."

for FUNC in aiops-fetch-logs aiops-fetch-metrics aiops-fetch-health; do
  aws lambda add-permission \
    --function-name "$FUNC" \
    --statement-id "AllowBedrockInvoke" \
    --action "lambda:InvokeFunction" \
    --principal "bedrock.amazonaws.com" \
    --region "$REGION" 2>/dev/null && echo "  ✓ $FUNC" || echo "  ✓ $FUNC (permission already exists)"
done

# =============================================================================
# STEP 2: Create Bedrock Agent
# =============================================================================
echo ""
echo "[2/3] Creating Bedrock Agent: $AGENT_NAME..."

AGENT_INSTRUCTION="You are Kira, a senior Site Reliability Engineer with 12 years of experience managing large-scale production systems on AWS. You have deep expertise in distributed systems, database performance tuning, container orchestration, and incident response.

You think like a real SRE during an incident — calm, methodical, and data-driven. You never guess. You always look at the data first before drawing conclusions.

You have 3 tools: fetch_logs (CloudWatch Logs), fetch_metrics (CloudWatch Metrics), and fetch_service_health (EKS cluster, node group, and pod health).

When an engineer comes with a problem:
Step 1: Understand the symptom.
Step 2: Form a hypothesis.
Step 3: Gather evidence using your tools.
Step 4: Diagnose by correlating the data across logs, metrics, and service health.
Step 5: Respond with root cause, evidence summary, immediate fix, and prevention steps.

Always cite specific log entries or metric values when drawing conclusions. Be concise but thorough."

EXISTING_AGENT_ID=$(aws bedrock-agent list-agents \
  --region "$REGION" \
  --query "agentSummaries[?agentName=='$AGENT_NAME'].agentId | [0]" \
  --output text 2>/dev/null)

if [ -n "$EXISTING_AGENT_ID" ] && [ "$EXISTING_AGENT_ID" != "None" ]; then
  AGENT_ID="$EXISTING_AGENT_ID"
  echo "  ✓ Agent already exists: $AGENT_ID"
else
  AGENT_ID=$(aws bedrock-agent create-agent \
    --agent-name "$AGENT_NAME" \
    --agent-resource-role-arn "$AGENT_ROLE_ARN" \
    --foundation-model "qwen.qwen3-32b-v1:0" \
    --instruction "$AGENT_INSTRUCTION" \
    --region "$REGION" \
    --query 'agent.agentId' --output text)
  echo "  ✓ Agent created: $AGENT_ID"
  echo "  Waiting 5s for agent to initialise..."
  sleep 5
fi

# =============================================================================
# STEP 3: Create action groups + prepare agent
# =============================================================================
echo ""
echo "[3/3] Adding action groups and preparing agent..."

python3 - <<PYEOF
import boto3, json, sys

region = "$REGION"
agent_id = "$AGENT_ID"
account_id = "$ACCOUNT_ID"
script_dir = "$SCRIPT_DIR"

client = boto3.client("bedrock-agent", region_name=region)

action_groups = [
    {
        "name": "fetch_logs",
        "func": "aiops-fetch-logs",
        "schema": "fetch_logs.json",
        "desc": "Search CloudWatch Logs for errors, warnings, and application events",
    },
    {
        "name": "fetch_metrics",
        "func": "aiops-fetch-metrics",
        "schema": "fetch_metrics.json",
        "desc": "Retrieve CloudWatch performance metrics (CPU, memory, latency, error rates)",
    },
    {
        "name": "fetch_service_health",
        "func": "aiops-fetch-health",
        "schema": "fetch_health.json",
        "desc": "Check live health status of EKS cluster, node groups, and crashing pods",
    },
]

existing = client.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT")
existing_names = [ag["actionGroupName"] for ag in existing.get("actionGroupSummaries", [])]

for ag in action_groups:
    if ag["name"] in existing_names:
        print(f"  ✓ {ag['name']} (already exists)")
        continue
    with open(f"{script_dir}/schemas/{ag['schema']}") as f:
        schema_content = f.read()
    func_arn = f"arn:aws:lambda:{region}:{account_id}:function:{ag['func']}"
    try:
        client.create_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupName=ag["name"],
            description=ag["desc"],
            actionGroupExecutor={"lambda": func_arn},
            apiSchema={"payload": schema_content},
        )
        print(f"  ✓ {ag['name']}")
    except Exception as e:
        print(f"  ✗ {ag['name']}: {e}", file=sys.stderr)
        sys.exit(1)
PYEOF

echo ""
echo "  Preparing agent..."
aws bedrock-agent prepare-agent \
  --agent-id "$AGENT_ID" \
  --region "$REGION" \
  --query 'agentStatus' --output text

echo ""
echo "============================================="
echo " Done!"
echo "============================================="
echo ""
echo " Agent ID   : $AGENT_ID"
echo " Alias ID   : TSTALIASID"
echo " Region     : $REGION"
echo ""
echo " Next steps:"
echo "  1. Generate sample data:"
echo "     python3 scripts/generate_sample_data.py --region $REGION"
echo ""
echo "  2. Test in Bedrock Console:"
echo "     https://$REGION.console.aws.amazon.com/bedrock/home?region=$REGION#/agents/$AGENT_ID"
echo ""
echo "  3. Run Streamlit UI:"
echo "     cp .env.example .env"
echo "     # Set BEDROCK_AGENT_ID=$AGENT_ID"
echo "     pip install -r requirements.txt"
echo "     streamlit run app.py"
echo ""
