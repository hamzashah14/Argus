#!/usr/bin/env bash
# =============================================================================
# AIOps Assistant — event-based alerting
#
# In MONITOR_REGION, creates/updates:
#   - SNS topics aiops-alarms (trigger bus, account-scoped policy) and
#     aiops-incident-reports (email)
#   - aiops-trigger-role and the aiops-trigger-investigation Lambda
#     (600s timeout, no retries, optional reserved concurrency)
#   - EventBridge rule: stop/terminate of the listed instances only
#   - Per instance: log groups (with retention) and alarms — status check,
#     CPU, and (only if CWAgent is already publishing them) memory/disk/process,
#     plus the Nginx 502/504/upstream-error alarm
#   - A watcher alarm that emails if the trigger Lambda itself fails
#
# Every run must list ALL monitored instances in INSTANCE_IDS: the EventBridge
# rule is rewritten to exactly that list. Safe to re-run.
# Usage: ./setup-alerts.sh
# =============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"
WARNINGS=0

require MONITOR_REGION BEDROCK_REGION BEDROCK_AGENT_ID BEDROCK_AGENT_ALIAS_ID ALERT_EMAIL INSTANCE_IDS
require_region MONITOR_REGION BEDROCK_REGION
require_bool ENABLE_RESOURCE_ALARMS ENABLE_NGINX_ALARM ENABLE_PROCESS_ALARM
require_int CPU_THRESHOLD MEM_THRESHOLD DISK_THRESHOLD NGINX_ERROR_THRESHOLD LOG_RETENTION_DAYS
[[ -z "$TRIGGER_RESERVED_CONCURRENCY" ]] || require_int TRIGGER_RESERVED_CONCURRENCY
[[ "$ALERT_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || die "ALERT_EMAIL '$ALERT_EMAIL' doesn't look like an email address."
[[ "$BEDROCK_AGENT_ALIAS_ID" != "TSTALIASID" ]] || warn "BEDROCK_AGENT_ALIAS_ID is TSTALIASID, which follows the editable DRAFT. Create a versioned alias for production."
ACCOUNT_ID="$(aws_account_id)"
R=(--region "$MONITOR_REGION")

IFS=',' read -ra IDS <<<"${INSTANCE_IDS// /}"
((${#IDS[@]} > 0)) || die "INSTANCE_IDS is empty."
for ID in "${IDS[@]}"; do
  [[ "$ID" =~ ^i-([0-9a-f]{8}|[0-9a-f]{17})$ ]] || die "INSTANCE_IDS contains '$ID', which isn't an EC2 instance ID."
done
aws ec2 describe-instances --instance-ids "${IDS[@]}" "${R[@]}" >/dev/null 2>&1 \
  || die "Not every instance in INSTANCE_IDS exists in $MONITOR_REGION. Check the IDs and MONITOR_REGION."
IFS=',' read -ra CONTAINERS <<<"${CONTAINER_NAMES// /}"

echo ""
echo "AIOps — alerting in $MONITOR_REGION for ${#IDS[@]} instance(s), account $ACCOUNT_ID"
echo ""

# -----------------------------------------------------------------------------
echo "[1/6] SNS topics"
# -----------------------------------------------------------------------------
ALARMS_TOPIC_ARN="$(aws sns create-topic --name "$ALARMS_TOPIC_NAME" "${R[@]}" --query TopicArn --output text)"
REPORTS_TOPIC_ARN="$(aws sns create-topic --name "$REPORTS_TOPIC_NAME" "${R[@]}" --query TopicArn --output text)"
RULE_ARN="arn:aws:events:${MONITOR_REGION}:${ACCOUNT_ID}:rule/${EC2_DOWN_RULE_NAME}"

# Replaces the topic policy: keeps AWS's default owner-only statement, and lets
# only THIS account's EventBridge rule and CloudWatch alarms publish. Without
# the source conditions, any account could publish here and run up Bedrock cost.
ALARMS_POLICY="$(python3 - "$ALARMS_TOPIC_ARN" "$ACCOUNT_ID" "$RULE_ARN" "$MONITOR_REGION" <<'PY'
import json, sys
topic, account, rule, region = sys.argv[1:]
print(json.dumps({"Version": "2012-10-17", "Statement": [
    {"Sid": "__default_statement_ID", "Effect": "Allow", "Principal": {"AWS": "*"},
     "Action": ["SNS:GetTopicAttributes", "SNS:SetTopicAttributes", "SNS:AddPermission", "SNS:RemovePermission",
                "SNS:DeleteTopic", "SNS:Subscribe", "SNS:ListSubscriptionsByTopic", "SNS:Publish"],
     "Resource": topic, "Condition": {"StringEquals": {"AWS:SourceOwner": account}}},
    {"Sid": "AllowOurEc2DownRule", "Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"},
     "Action": "sns:Publish", "Resource": topic, "Condition": {"ArnEquals": {"aws:SourceArn": rule}}},
    {"Sid": "AllowOurCloudWatchAlarms", "Effect": "Allow", "Principal": {"Service": "cloudwatch.amazonaws.com"},
     "Action": "sns:Publish", "Resource": topic, "Condition": {
         "StringEquals": {"aws:SourceAccount": account},
         "ArnLike": {"aws:SourceArn": f"arn:aws:cloudwatch:{region}:{account}:alarm:aiops-*"}}},
]}))
PY
)"
aws sns set-topic-attributes --topic-arn "$ALARMS_TOPIC_ARN" --attribute-name Policy --attribute-value "$ALARMS_POLICY" "${R[@]}"
echo "  ✓ $ALARMS_TOPIC_NAME — publishable only by this account's rule and aiops-* alarms"

EMAIL_SUB="$(aws sns list-subscriptions-by-topic --topic-arn "$REPORTS_TOPIC_ARN" "${R[@]}" \
  --query "Subscriptions[?Endpoint=='$ALERT_EMAIL'].SubscriptionArn | [0]" --output text)"
if [[ -z "$EMAIL_SUB" || "$EMAIL_SUB" == "None" || "$EMAIL_SUB" == "PendingConfirmation" ]]; then
  aws sns subscribe --topic-arn "$REPORTS_TOPIC_ARN" --protocol email --notification-endpoint "$ALERT_EMAIL" "${R[@]}" >/dev/null
  warn "Confirmation email sent to $ALERT_EMAIL — click the link or no report will ever arrive."
else
  echo "  ✓ $ALERT_EMAIL subscribed and confirmed"
fi

# -----------------------------------------------------------------------------
echo ""
echo "[2/6] Trigger Lambda role"
# -----------------------------------------------------------------------------
TRIGGER_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
if aws iam get-role --role-name "$TRIGGER_ROLE_NAME" >/dev/null 2>&1; then
  echo "  ✓ $TRIGGER_ROLE_NAME exists"
else
  aws iam create-role --role-name "$TRIGGER_ROLE_NAME" --assume-role-policy-document "$TRIGGER_TRUST" \
    --description "AIOps trigger Lambda — invoke the agent, publish incident reports" >/dev/null
  echo "  ✓ Created $TRIGGER_ROLE_NAME"
fi
aws iam attach-role-policy --role-name "$TRIGGER_ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
aws iam put-role-policy --role-name "$TRIGGER_ROLE_NAME" --policy-name "aiops-trigger-inline-policy" --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Sid\": \"InvokeOurAgentAlias\", \"Effect\": \"Allow\", \"Action\": \"bedrock:InvokeAgent\",
     \"Resource\": \"arn:aws:bedrock:${BEDROCK_REGION}:${ACCOUNT_ID}:agent-alias/${BEDROCK_AGENT_ID}/${BEDROCK_AGENT_ALIAS_ID}\"},
    {\"Sid\": \"PublishIncidentReports\", \"Effect\": \"Allow\", \"Action\": \"sns:Publish\", \"Resource\": \"$REPORTS_TOPIC_ARN\"}
  ]
}"
echo "  ✓ bedrock:InvokeAgent on the configured alias + sns:Publish on $REPORTS_TOPIC_NAME"

# -----------------------------------------------------------------------------
echo ""
echo "[3/6] Trigger Lambda"
# -----------------------------------------------------------------------------
TRIGGER_ENV="$(python3 -c 'import json, sys; k = ["BEDROCK_REGION", "BEDROCK_AGENT_ID", "BEDROCK_AGENT_ALIAS_ID", "REPORTS_TOPIC_ARN"]; print(json.dumps({"Variables": dict(zip(k, sys.argv[1:]))}))' \
  "$BEDROCK_REGION" "$BEDROCK_AGENT_ID" "$BEDROCK_AGENT_ALIAS_ID" "$REPORTS_TOPIC_ARN")"
# 600s: an investigation is ~10 tool calls plus model time. The function
# itself stops reading 45s before this to always publish something.
deploy_lambda "$TRIGGER_FUNC" "$ROOT_DIR/lambda/trigger_investigation" "$MONITOR_REGION" \
  "arn:aws:iam::${ACCOUNT_ID}:role/${TRIGGER_ROLE_NAME}" 600 256 "$TRIGGER_ENV" "AIOps automatic incident investigation"

# No automatic retries: a retry would re-run a paid investigation and send a
# duplicate email. Failures surface through the watcher alarm instead.
aws lambda put-function-event-invoke-config --function-name "$TRIGGER_FUNC" \
  --maximum-retry-attempts 0 --maximum-event-age-in-seconds 3600 "${R[@]}" >/dev/null
echo "  ✓ Retries off"

if [[ -n "$TRIGGER_RESERVED_CONCURRENCY" ]]; then
  if aws lambda put-function-concurrency --function-name "$TRIGGER_FUNC" \
    --reserved-concurrent-executions "$TRIGGER_RESERVED_CONCURRENCY" "${R[@]}" >/dev/null 2>&1; then
    echo "  ✓ At most $TRIGGER_RESERVED_CONCURRENCY investigation(s) at once"
  else
    warn "Couldn't reserve concurrency (account concurrency quota too low?). Investigations aren't capped."
  fi
fi

aws lambda remove-permission --function-name "$TRIGGER_FUNC" --statement-id AllowSNSInvoke "${R[@]}" >/dev/null 2>&1 || true
aws lambda add-permission --function-name "$TRIGGER_FUNC" --statement-id AllowSNSInvoke \
  --action lambda:InvokeFunction --principal sns.amazonaws.com --source-arn "$ALARMS_TOPIC_ARN" "${R[@]}" >/dev/null
TRIGGER_ARN="arn:aws:lambda:${MONITOR_REGION}:${ACCOUNT_ID}:function:${TRIGGER_FUNC}"
LAMBDA_SUB="$(aws sns list-subscriptions-by-topic --topic-arn "$ALARMS_TOPIC_ARN" "${R[@]}" \
  --query "Subscriptions[?Endpoint=='$TRIGGER_ARN'].SubscriptionArn | [0]" --output text)"
if [[ -z "$LAMBDA_SUB" || "$LAMBDA_SUB" == "None" ]]; then
  aws sns subscribe --topic-arn "$ALARMS_TOPIC_ARN" --protocol lambda --notification-endpoint "$TRIGGER_ARN" "${R[@]}" >/dev/null
fi
echo "  ✓ Subscribed to $ALARMS_TOPIC_NAME"

# -----------------------------------------------------------------------------
echo ""
echo "[4/6] EventBridge rule (monitored instances only)"
# -----------------------------------------------------------------------------
EVENT_PATTERN="$(python3 -c 'import json, sys; print(json.dumps({"source": ["aws.ec2"], "detail-type": ["EC2 Instance State-change Notification"], "detail": {"state": ["stopped", "terminated"], "instance-id": sys.argv[1:]}}))' "${IDS[@]}")"
aws events put-rule --name "$EC2_DOWN_RULE_NAME" --event-pattern "$EVENT_PATTERN" "${R[@]}" >/dev/null
aws events put-targets --rule "$EC2_DOWN_RULE_NAME" --targets "Id=aiops-alarms-topic,Arn=$ALARMS_TOPIC_ARN" "${R[@]}" >/dev/null
echo "  ✓ Stop/terminate of: ${IDS[*]}"

# -----------------------------------------------------------------------------
echo ""
echo "[5/6] Per-instance log groups and alarms"
# -----------------------------------------------------------------------------
ensure_log_group() {
  aws logs create-log-group --log-group-name "$1" "${R[@]}" 2>/dev/null || true
  aws logs put-retention-policy --log-group-name "$1" --retention-in-days "$LOG_RETENTION_DAYS" "${R[@]}"
}

# True only if the metric exists with EXACTLY these dimensions — CloudWatch
# alarms match the full dimension set, so a near-miss alarm would never fire.
metric_exists() { # namespace metric Name=Value...
  local ns="$1" metric="$2"
  shift 2
  aws cloudwatch list-metrics --namespace "$ns" --metric-name "$metric" "${R[@]}" --output json |
    python3 -c '
import json, sys
want = dict(arg.split("=", 1) for arg in sys.argv[1:])
metrics = json.load(sys.stdin).get("Metrics", [])
sys.exit(0 if any({d["Name"]: d["Value"] for d in m["Dimensions"]} == want for m in metrics) else 1)' "$@"
}

put_alarm() { # name namespace metric statistic period evaluations datapoints threshold comparison missing dims...
  local name="$1" ns="$2" metric="$3" stat="$4" period="$5" evals="$6" dta="$7" threshold="$8" cmp="$9" missing="${10}"
  shift 10
  local dims=()
  (($# == 0)) || dims=(--dimensions "$@")
  aws cloudwatch put-metric-alarm --alarm-name "$name" --namespace "$ns" --metric-name "$metric" \
    --statistic "$stat" --period "$period" --evaluation-periods "$evals" --datapoints-to-alarm "$dta" \
    --threshold "$threshold" --comparison-operator "$cmp" --treat-missing-data "$missing" \
    --alarm-actions "$ALARMS_TOPIC_ARN" ${dims[@]+"${dims[@]}"} "${R[@]}"
}

test_filter() { # pattern should_match_line should_not_match_line
  local matched
  matched="$(aws logs test-metric-filter --filter-pattern "$1" --log-event-messages "$2" "$3" "${R[@]}" \
    --query 'matches[].eventNumber' --output text 2>&1)" || die "Invalid filter pattern '$1': $matched"
  [[ "$matched" == "1" ]]
}

NGINX_ACCESS_SAMPLE_HIT='203.0.113.7 - - [24/Sep/2026:10:15:32 +0000] "GET /api/orders HTTP/1.1" 504 167 "-" "Mozilla/5.0"'
NGINX_ACCESS_SAMPLE_MISS='203.0.113.7 - - [24/Sep/2026:10:15:32 +0000] "GET /api/orders HTTP/1.1" 200 502 "-" "Mozilla/5.0"'
NGINX_ERROR_SAMPLE_HIT='2026/09/24 10:15:32 [error] 31#31: *907 upstream timed out (110: Connection timed out) while reading response header from upstream, client: 203.0.113.7, server: _, request: "GET /api/orders HTTP/1.1", upstream: "http://127.0.0.1:5001/api/orders"'
NGINX_ERROR_SAMPLE_MISS='2026/09/24 10:15:32 [notice] 1#1: signal process started'
if [[ "$ENABLE_NGINX_ALARM" == "true" ]]; then
  test_filter "$NGINX_ACCESS_FILTER_PATTERN" "$NGINX_ACCESS_SAMPLE_HIT" "$NGINX_ACCESS_SAMPLE_MISS" \
    || warn "NGINX_ACCESS_FILTER_PATTERN doesn't behave on a standard 'combined' log line (should match a 504, not a 200 with a 502-byte body). Fine if your log_format differs — verify it against your real lines (README)."
  test_filter "$NGINX_ERROR_FILTER_PATTERN" "$NGINX_ERROR_SAMPLE_HIT" "$NGINX_ERROR_SAMPLE_MISS" \
    || warn "NGINX_ERROR_FILTER_PATTERN doesn't match a standard nginx 'upstream timed out' line."
fi

for ID in "${IDS[@]}"; do
  echo "  $ID"
  put_alarm "aiops-${ID}-status-check-failed" AWS/EC2 StatusCheckFailed Maximum 60 2 2 0 GreaterThanThreshold notBreaching "Name=InstanceId,Value=$ID"
  echo "    ✓ status check failed (2 min)"

  if [[ "$ENABLE_RESOURCE_ALARMS" == "true" ]]; then
    put_alarm "aiops-${ID}-cpu-high" AWS/EC2 CPUUtilization Average 300 3 3 "$CPU_THRESHOLD" GreaterThanThreshold notBreaching "Name=InstanceId,Value=$ID"
    echo "    ✓ CPU > ${CPU_THRESHOLD}% for 15 min"
    if metric_exists CWAgent mem_used_percent "InstanceId=$ID"; then
      put_alarm "aiops-${ID}-memory-high" CWAgent mem_used_percent Average 300 3 3 "$MEM_THRESHOLD" GreaterThanThreshold notBreaching "Name=InstanceId,Value=$ID"
      echo "    ✓ memory > ${MEM_THRESHOLD}% for 15 min"
    else
      warn "$ID: CWAgent mem_used_percent (dimension InstanceId only) not found — memory alarm skipped. Configure CWAgent, wait 5 min, re-run."
    fi
    if metric_exists CWAgent disk_used_percent "InstanceId=$ID" "path=$DISK_PATH"; then
      put_alarm "aiops-${ID}-disk-high" CWAgent disk_used_percent Average 300 2 2 "$DISK_THRESHOLD" GreaterThanThreshold notBreaching "Name=InstanceId,Value=$ID" "Name=path,Value=$DISK_PATH"
      echo "    ✓ disk $DISK_PATH > ${DISK_THRESHOLD}% for 10 min"
    else
      warn "$ID: CWAgent disk_used_percent with exactly InstanceId+path=$DISK_PATH not found — disk alarm skipped. Needs aggregation_dimensions (see cwagent-config.example.json)."
    fi
  fi

  if [[ "$ENABLE_PROCESS_ALARM" == "true" ]]; then
    if metric_exists CWAgent procstat_lookup_pid_count "InstanceId=$ID"; then
      put_alarm "aiops-${ID}-process-down" CWAgent procstat_lookup_pid_count Minimum 60 2 2 1 LessThanThreshold notBreaching "Name=InstanceId,Value=$ID"
      echo "    ✓ monitored process down (2 min)"
    else
      warn "$ID: procstat_lookup_pid_count aggregated to InstanceId not found — process alarm skipped."
    fi
  fi

  for NAME in ${CONTAINERS[@]+"${CONTAINERS[@]}"}; do
    ensure_log_group "${LOG_GROUP_PREFIX}/${ID}/${NAME}"
  done
  ((${#CONTAINERS[@]} == 0)) || echo "    ✓ container log groups: ${CONTAINERS[*]:-} (${LOG_RETENTION_DAYS}-day retention)"

  if [[ "$ENABLE_NGINX_ALARM" == "true" ]]; then
    ACCESS_GROUP="${LOG_GROUP_PREFIX}/${ID}/nginx-access"
    ERROR_GROUP="${LOG_GROUP_PREFIX}/${ID}/nginx-error"
    METRIC="nginx-upstream-errors-${ID}"
    ensure_log_group "$ACCESS_GROUP"
    ensure_log_group "$ERROR_GROUP"
    aws logs put-metric-filter --log-group-name "$ACCESS_GROUP" --filter-name aiops-upstream-5xx \
      --filter-pattern "$NGINX_ACCESS_FILTER_PATTERN" "${R[@]}" \
      --metric-transformations "metricName=$METRIC,metricNamespace=AIOpsNginx,metricValue=1,defaultValue=0"
    aws logs put-metric-filter --log-group-name "$ERROR_GROUP" --filter-name aiops-upstream-errors \
      --filter-pattern "$NGINX_ERROR_FILTER_PATTERN" "${R[@]}" \
      --metric-transformations "metricName=$METRIC,metricNamespace=AIOpsNginx,metricValue=1,defaultValue=0"
    put_alarm "aiops-${ID}-nginx-errors" AIOpsNginx "$METRIC" Sum 60 3 2 "$NGINX_ERROR_THRESHOLD" GreaterThanOrEqualToThreshold notBreaching
    echo "    ✓ nginx: ≥${NGINX_ERROR_THRESHOLD} upstream errors/min in 2 of 3 min"
  fi
done

# -----------------------------------------------------------------------------
echo ""
echo "[6/6] Watcher alarm"
# -----------------------------------------------------------------------------
aws cloudwatch put-metric-alarm --alarm-name "aiops-kira-trigger-failing" \
  --alarm-description "The aiops-trigger-investigation Lambda is failing, so incident reports may not be arriving." \
  --namespace AWS/Lambda --metric-name Errors --dimensions "Name=FunctionName,Value=$TRIGGER_FUNC" \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --alarm-actions "$REPORTS_TOPIC_ARN" "${R[@]}"
echo "  ✓ Emails $ALERT_EMAIL directly if the trigger Lambda errors"

echo ""
if ((WARNINGS > 0)); then
  echo "Done with $WARNINGS warning(s) above — each one is something not yet monitored."
else
  echo "Done."
fi
echo "Test end to end (sends a real investigation + email):"
echo "  aws cloudwatch set-alarm-state --alarm-name aiops-${IDS[0]}-status-check-failed --state-value ALARM --state-reason test --region $MONITOR_REGION"
echo ""
