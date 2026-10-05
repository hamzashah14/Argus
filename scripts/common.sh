#!/usr/bin/env bash
# Sourced by the setup scripts: loads config.env, applies defaults, validates
# values, and provides shared helpers. Not meant to be run directly.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$ROOT_DIR/config.env}"

die() { echo "  ✗ $*" >&2; exit 1; }
warn() { echo "  ! $*" >&2; WARNINGS=$((${WARNINGS:-0} + 1)); }

[[ -f "$CONFIG_FILE" ]] || die "Missing $CONFIG_FILE — copy config.env.example and fill it in."
CONFIG_FILE="$(cd "$(dirname "$CONFIG_FILE")" && pwd)/$(basename "$CONFIG_FILE")"
KIRA_PYTHON="${KIRA_PYTHON:-$ROOT_DIR/.venv/bin/python}"
[[ -x "$KIRA_PYTHON" ]] || KIRA_PYTHON=python3
"$KIRA_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' \
  || die "Use Python 3.12 in .venv or set KIRA_PYTHON to a Python 3.12 executable."
cd "$ROOT_DIR"
case "$(basename "$0")" in
  setup-iam.sh) CONFIG_PURPOSE=iam ;;
  setup-lambdas.sh) CONFIG_PURPOSE=tools ;;
  deploy.sh) CONFIG_PURPOSE=agent ;;
  setup-alerts.sh) CONFIG_PURPOSE=alerts ;;
  *) CONFIG_PURPOSE=validate ;;
esac
_config_exports="$("$KIRA_PYTHON" -m kira.config "$CONFIG_FILE" --purpose "$CONFIG_PURPOSE" --exports)" \
  || die "Configuration validation failed; no cloud changes were made."
# Values are serialized by shlex.quote from a fixed validated field allowlist.
eval "$_config_exports"
unset _config_exports
export KIRA_PYTHON

export TOOLS_ROLE_NAME="aiops-lambda-role"
export AGENT_ROLE_NAME="aiops-bedrock-agent-role"
export TRIGGER_ROLE_NAME="aiops-trigger-role"
export FETCH_LOGS_FUNC="aiops-fetch-logs"
export FETCH_METRICS_FUNC="aiops-fetch-metrics"
export TRIGGER_FUNC="aiops-trigger-investigation"
export ALARMS_TOPIC_NAME="aiops-alarms"
export REPORTS_TOPIC_NAME="aiops-incident-reports"
export EC2_DOWN_RULE_NAME="aiops-ec2-down"
export LAMBDA_RUNTIME="python3.12"

require() {
  local missing=() v
  for v in "$@"; do [[ -n "${!v:-}" ]] || missing+=("$v"); done
  ((${#missing[@]} == 0)) || die "Set these in $CONFIG_FILE first: ${missing[*]}"
}

require_bool() {
  local v
  for v in "$@"; do
    case "${!v}" in true | false) ;; *) die "$v must be true or false (got '${!v}')" ;; esac
  done
}

require_int() {
  local v
  for v in "$@"; do [[ "${!v}" =~ ^[0-9]+$ ]] || die "$v must be a whole number (got '${!v}')"; done
}

require_region() {
  local v
  for v in "$@"; do [[ "${!v}" =~ ^[a-z]{2}(-gov)?-[a-z]+-[0-9]$ ]] || die "$v doesn't look like an AWS region (got '${!v}')"; done
}

aws_account_id() {
  local actual
  actual="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" \
    || die "AWS identity check failed. Authenticate the intended profile first."
  [[ "$actual" == "$EXPECTED_ACCOUNT_ID" ]] || die "AWS identity differs from EXPECTED_ACCOUNT_ID; no cloud changes were made."
  [[ "$ENVIRONMENT" == "development" && "${ALLOW_LEGACY_DEVELOPMENT_DEPLOY:-false}" == "true" ]] \
    || die "Legacy mutable deployment is disabled. Use python -m infra and the Phase 2 guide. Development-only opt-in: ALLOW_LEGACY_DEVELOPMENT_DEPLOY=true."
  echo "$actual"
}

# Creates or updates a Lambda from <src_dir>/lambda_function.py. Waits for each
# update to settle: Lambda rejects a config change while a code update is still
# in progress (ResourceConflictException).
deploy_lambda() { # name src_dir region role_arn timeout_s memory_mb env_json description
  local name="$1" src="$2" region="$3" role="$4" timeout="$5" memory="$6" env_json="$7" desc="$8"
  local zip="$ROOT_DIR/.tmp_${name}.zip" err="$ROOT_DIR/.tmp_${name}.err" attempt
  rm -f "$zip"
  "$KIRA_PYTHON" "$ROOT_DIR/scripts/build_lambdas.py" --function "$(basename "$src")" --output "$ROOT_DIR/.build/lambda" --catalog "$METRIC_CATALOG_FILE"
  cp "$ROOT_DIR/.build/lambda/$(basename "$src").zip" "$zip"

  if aws lambda get-function --function-name "$name" --region "$region" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$name" --zip-file "fileb://$zip" --region "$region" >/dev/null
    aws lambda wait function-updated --function-name "$name" --region "$region"
    aws lambda update-function-configuration --function-name "$name" --role "$role" \
      --runtime "$LAMBDA_RUNTIME" --handler lambda_function.lambda_handler \
      --timeout "$timeout" --memory-size "$memory" --environment "$env_json" \
      --description "$desc" --region "$region" >/dev/null
    aws lambda wait function-updated --function-name "$name" --region "$region"
    echo "  ✓ Updated $name"
  else
    # A just-created IAM role can take a few seconds before Lambda may assume it.
    for attempt in 1 2 3 4 5 6; do
      if aws lambda create-function --function-name "$name" --role "$role" \
        --runtime "$LAMBDA_RUNTIME" --handler lambda_function.lambda_handler \
        --timeout "$timeout" --memory-size "$memory" --environment "$env_json" \
        --code "ZipFile=fileb://$zip" --description "$desc" --region "$region" >/dev/null 2>"$err"; then
        break
      fi
      if ((attempt == 6)); then
        cat "$err" >&2
        rm -f "$zip" "$err"
        die "Could not create $name"
      fi
      sleep 5
    done
    aws lambda wait function-active --function-name "$name" --region "$region"
    echo "  ✓ Created $name"
  fi
  rm -f "$zip" "$err"
}
