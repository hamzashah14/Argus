#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — IAM Setup Script
#
# Creates all IAM roles and policies required for the project:
#   1. aiops-lambda-role       — used by all 3 Lambda functions
#   2. aiops-bedrock-agent-role — used by the Bedrock Agent
#
# Usage:
#   chmod +x setup-iam.sh
#   ./setup-iam.sh
# =============================================================================

set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "============================================="
echo " AIOps — IAM Setup"
echo " Account : $ACCOUNT_ID"
echo " Region  : $REGION"
echo "============================================="
echo ""

# =============================================================================
# ROLE 1: aiops-lambda-role
# Used by: aiops-fetch-logs, aiops-fetch-metrics, aiops-fetch-health
# =============================================================================
LAMBDA_ROLE_NAME="aiops-lambda-role"

echo "[1/2] Creating IAM role: $LAMBDA_ROLE_NAME"

LAMBDA_TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
)

if aws iam get-role --role-name "$LAMBDA_ROLE_NAME" &>/dev/null; then
  echo "  ✓ Role already exists: $LAMBDA_ROLE_NAME"
else
  aws iam create-role \
    --role-name "$LAMBDA_ROLE_NAME" \
    --assume-role-policy-document "$LAMBDA_TRUST_POLICY" \
    --description "Role for AIOps Lambda functions — fetch logs, metrics, and EKS health" \
    --query 'Role.RoleName' --output text
  echo "  ✓ Created: $LAMBDA_ROLE_NAME"
fi

# Attach managed policy for basic Lambda execution (CloudWatch Logs write)
aws iam attach-role-policy \
  --role-name "$LAMBDA_ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
echo "  ✓ Attached: AWSLambdaBasicExecutionRole"

# Inline policy for reading CloudWatch Logs and EKS health
LAMBDA_INLINE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchLogsRead",
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EKSRead",
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster",
        "eks:ListNodegroups",
        "eks:DescribeNodegroup"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

aws iam put-role-policy \
  --role-name "$LAMBDA_ROLE_NAME" \
  --policy-name "aiops-lambda-inline-policy" \
  --policy-document "$LAMBDA_INLINE_POLICY"
echo "  ✓ Inline policy applied: CloudWatch Logs read + EKS describe"

# =============================================================================
# ROLE 2: aiops-bedrock-agent-role
# Used by: Bedrock Agent (aiops-assistant)
# =============================================================================
AGENT_ROLE_NAME="aiops-bedrock-agent-role"

echo ""
echo "[2/2] Creating IAM role: $AGENT_ROLE_NAME"

BEDROCK_TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "$ACCOUNT_ID"
        }
      }
    }
  ]
}
EOF
)

if aws iam get-role --role-name "$AGENT_ROLE_NAME" &>/dev/null; then
  echo "  ✓ Role already exists: $AGENT_ROLE_NAME"
else
  aws iam create-role \
    --role-name "$AGENT_ROLE_NAME" \
    --assume-role-policy-document "$BEDROCK_TRUST_POLICY" \
    --description "Role for Bedrock Agent — AIOps assistant (Kira)" \
    --query 'Role.RoleName' --output text
  echo "  ✓ Created: $AGENT_ROLE_NAME"
fi

# Inline policy for invoking Lambda functions and Bedrock models
AGENT_INLINE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeLambdaFunctions",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": [
        "arn:aws:lambda:$REGION:$ACCOUNT_ID:function:aiops-fetch-logs",
        "arn:aws:lambda:$REGION:$ACCOUNT_ID:function:aiops-fetch-metrics",
        "arn:aws:lambda:$REGION:$ACCOUNT_ID:function:aiops-fetch-health"
      ]
    },
    {
      "Sid": "InvokeBedrockModels",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:$REGION::foundation-model/*"
    }
  ]
}
EOF
)

aws iam put-role-policy \
  --role-name "$AGENT_ROLE_NAME" \
  --policy-name "aiops-bedrock-agent-inline-policy" \
  --policy-document "$AGENT_INLINE_POLICY"
echo "  ✓ Inline policy applied: Lambda invoke + Bedrock model invoke"

echo ""
echo "============================================="
echo " Done!"
echo "============================================="
echo ""
echo " Roles created:"
echo "  - $LAMBDA_ROLE_NAME"
echo "    ARN: arn:aws:iam::$ACCOUNT_ID:role/$LAMBDA_ROLE_NAME"
echo ""
echo "  - $AGENT_ROLE_NAME"
echo "    ARN: arn:aws:iam::$ACCOUNT_ID:role/$AGENT_ROLE_NAME"
echo ""
echo " Next step: Create the 3 Lambda functions in AWS Console"
echo "   and assign '$LAMBDA_ROLE_NAME' as their execution role."
echo ""
