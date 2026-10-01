#!/usr/bin/env bash
# Sourced by the setup scripts: loads config.env, applies defaults, validates
# values, and provides shared helpers. Not meant to be run directly.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$ROOT_DIR/config.env}"

die() { echo "  ✗ $*" >&2; exit 1; }
warn() { echo "  ! $*" >&2; WARNINGS=$((${WARNINGS:-0} + 1)); }

[[ -f "$CONFIG_FILE" ]] || die "Missing $CONFIG_FILE — copy config.env.example to config.env and fill it in."
if grep -q $'\r' "$CONFIG_FILE"; then
  die "$CONFIG_FILE has Windows (CRLF) line endings; convert it to LF first."
fi

# Strict KEY=VALUE reader instead of `source`: never executes anything from the
# file, and a value with a space (INSTANCE_IDS=i-a, i-b) is kept as data
# instead of being run as a command.
_line_no=0
while IFS= read -r _line || [[ -n "$_line" ]]; do
  _line_no=$((_line_no + 1))
  [[ "$_line" =~ ^[[:space:]]*(#|$) ]] && continue
  [[ "$_line" =~ ^[[:space:]]*([A-Z][A-Z0-9_]*)=(.*)$ ]] \
    || die "$CONFIG_FILE line $_line_no isn't KEY=VALUE: $_line"
  _key="${BASH_REMATCH[1]}"
  _val="${BASH_REMATCH[2]}"
  _val="${_val%"${_val##*[![:space:]]}"}"
  if [[ "$_val" =~ ^\'(.*)\'$ || "$_val" =~ ^\"(.*)\"$ ]]; then
    _val="${BASH_REMATCH[1]}"
  fi
  printf -v "$_key" '%s' "$_val"
  export "${_key?}"
done <"$CONFIG_FILE"
unset _line _line_no _key _val

: "${LOG_GROUP_PREFIX:=/aiops}"
LOG_GROUP_PREFIX="${LOG_GROUP_PREFIX%/}"
: "${LOG_RETENTION_DAYS:=30}"
: "${AGENT_NAME:=aiops-assistant}"
: "${CONTAINER_NAMES:=}"
: "${ENABLE_RESOURCE_ALARMS:=true}"
: "${CPU_THRESHOLD:=90}"
: "${MEM_THRESHOLD:=90}"
: "${DISK_THRESHOLD:=85}"
: "${DISK_PATH:=/}"
: "${ENABLE_NGINX_ALARM:=true}"
: "${NGINX_ERROR_THRESHOLD:=5}"
: "${NGINX_ACCESS_FILTER_PATTERN:=[ip, ident, user, timestamp, request, status_code = 502 || status_code = 504, bytes, referer, agent]}"
: "${NGINX_ERROR_FILTER_PATTERN:=?\"upstream timed out\" ?\"no live upstreams\" ?\"connect() failed\"}"
: "${ENABLE_PROCESS_ALARM:=false}"
: "${TRIGGER_RESERVED_CONCURRENCY:=}"

TOOLS_ROLE_NAME="aiops-lambda-role"
AGENT_ROLE_NAME="aiops-bedrock-agent-role"
TRIGGER_ROLE_NAME="aiops-trigger-role"
FETCH_LOGS_FUNC="aiops-fetch-logs"
FETCH_METRICS_FUNC="aiops-fetch-metrics"
TRIGGER_FUNC="aiops-trigger-investigation"
ALARMS_TOPIC_NAME="aiops-alarms"
REPORTS_TOPIC_NAME="aiops-incident-reports"
EC2_DOWN_RULE_NAME="aiops-ec2-down"
LAMBDA_RUNTIME="python3.12"

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
  aws sts get-caller-identity --query Account --output text 2>/dev/null \
    || die "The AWS CLI has no valid credentials (aws sts get-caller-identity failed)."
}

# Creates or updates a Lambda from <src_dir>/lambda_function.py. Waits for each
# update to settle: Lambda rejects a config change while a code update is still
# in progress (ResourceConflictException).
deploy_lambda() { # name src_dir region role_arn timeout_s memory_mb env_json description
  local name="$1" src="$2" region="$3" role="$4" timeout="$5" memory="$6" env_json="$7" desc="$8"
  local zip="$ROOT_DIR/.tmp_${name}.zip" err="$ROOT_DIR/.tmp_${name}.err" attempt
  rm -f "$zip"
  zip -qj "$zip" "$src/lambda_function.py"

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
