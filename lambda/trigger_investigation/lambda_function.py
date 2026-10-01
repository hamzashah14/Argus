"""
Subscribed to the aiops-alarms SNS topic. For each actionable CloudWatch alarm
or EC2 stop/terminate event, asks the same Bedrock Agent the chat UI uses to
investigate at the exact incident time, and emails the result through the
aiops-incident-reports topic. Always emails something — even a failure or a
partial answer — unless SNS itself is failing, in which case the invocation
errors and the watcher alarm set up by setup-alerts.sh emails instead.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION") or REGION
AGENT_ID = os.environ.get("BEDROCK_AGENT_ID")
AGENT_ALIAS_ID = os.environ.get("BEDROCK_AGENT_ALIAS_ID")
REPORTS_TOPIC_ARN = os.environ.get("REPORTS_TOPIC_ARN")

SNS_CONFIG = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"})
# Stop reading the agent's answer this long before Lambda would kill us, so
# there is always time left to publish what we have.
SAFETY_MARGIN_S = 45
MAX_MESSAGE_CHARS = 200_000  # SNS caps messages at 256 KB
TIME_FMT = "%Y-%m-%d %H:%M:%S"
DOWN_STATES = {"stopped", "terminated"}
ALARM_NAME_INSTANCE_RE = re.compile(r"^aiops-(i-[0-9a-f]+)-")


def _utc_now():
    return datetime.now(timezone.utc).strftime(TIME_FMT)


def _format_alarm_time(value):
    # CloudWatch alarm messages: "2026-09-24T10:15:32.123+0000"
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(timezone.utc).strftime(TIME_FMT)
    except (TypeError, ValueError):
        return _utc_now()


def _format_event_time(value):
    # EventBridge events: "2026-09-24T10:15:32Z"
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime(TIME_FMT)
    except (TypeError, ValueError):
        return _utc_now()


def _instance_id_from_alarm(msg):
    # Every alarm this project creates is named "aiops-<instance-id>-<suffix>".
    # Metric-filter alarms (Nginx) have no InstanceId dimension at all, so the
    # name is the only place the ID lives; dimensions are a fallback.
    match = ALARM_NAME_INSTANCE_RE.match(msg.get("AlarmName", ""))
    if match:
        return match.group(1)
    dims = {d.get("name"): d.get("value") for d in (msg.get("Trigger") or {}).get("Dimensions", [])}
    return dims.get("InstanceId")


def parse_alarm_message(msg):
    if msg.get("NewStateValue") != "ALARM":
        return None, None, None
    reason = f"CloudWatch alarm '{msg.get('AlarmName')}' entered ALARM: {msg.get('NewStateReason', '')}"
    return _instance_id_from_alarm(msg), _format_alarm_time(msg.get("StateChangeTime")), reason


def parse_ec2_state_change(msg):
    detail = msg.get("detail") or {}
    state = detail.get("state")
    if state not in DOWN_STATES:
        return None, None, None
    return detail.get("instance-id"), _format_event_time(msg.get("time")), f"EC2 instance entered state '{state}'"


def extract_incident(message_body):
    """(instance_id, incident_time, reason), or (None, None, None) if not actionable."""
    if "AlarmName" in message_body:
        return parse_alarm_message(message_body)
    if message_body.get("detail-type") == "EC2 Instance State-change Notification":
        return parse_ec2_state_change(message_body)
    return None, None, None


def build_prompt(instance_id, time_str, reason):
    return (
        f"Automated alert for EC2 instance {instance_id}: {reason}. "
        f"Incident time: {time_str} UTC — pass it as time_string on every tool call. "
        "Discover this instance's log groups first, then check the relevant ones (Nginx error log and "
        "every application container for an outage or 5xx alert) with filter_text empty, and the "
        "relevant metrics. Report root cause, evidence, immediate fix and prevention."
    )


def investigate(instance_id, time_str, reason, remaining_s):
    """Returns (answer_text, complete). Never runs past the Lambda deadline."""
    read_timeout = max(30, int(remaining_s() - SAFETY_MARGIN_S))
    client = boto3.client(
        "bedrock-agent-runtime", region_name=BEDROCK_REGION,
        config=Config(connect_timeout=10, read_timeout=read_timeout, retries={"max_attempts": 2, "mode": "standard"}),
    )
    response = client.invoke_agent(
        agentId=AGENT_ID, agentAliasId=AGENT_ALIAS_ID,
        sessionId=str(uuid.uuid4()), inputText=build_prompt(instance_id, time_str, reason),
    )
    parts = []
    for event in response["completion"]:
        chunk = event.get("chunk") or {}
        if "bytes" in chunk:
            parts.append(chunk["bytes"].decode("utf-8", errors="replace"))
        if remaining_s() < SAFETY_MARGIN_S:
            return "".join(parts), False
    return "".join(parts), True


def publish_report(instance_id, time_str, reason, body):
    message = f"Instance: {instance_id}\nTrigger: {reason}\nIncident time: {time_str} UTC\n\n{body}"
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS] + "\n\n[truncated]"
    boto3.client("sns", region_name=REGION, config=SNS_CONFIG).publish(
        TopicArn=REPORTS_TOPIC_ARN, Subject=f"[Kira] Incident on {instance_id}", Message=message,
    )


def handle_record(message_body, remaining_s):
    instance_id, time_str, reason = extract_incident(message_body)
    if not instance_id:
        return
    if not REPORTS_TOPIC_ARN:
        raise RuntimeError("REPORTS_TOPIC_ARN is not set; cannot deliver incident reports.")
    if not (AGENT_ID and AGENT_ALIAS_ID):
        publish_report(instance_id, time_str, reason,
                       "Automatic investigation skipped: BEDROCK_AGENT_ID / BEDROCK_AGENT_ALIAS_ID are not set on "
                       "the aiops-trigger-investigation Lambda. Re-run setup-alerts.sh after setting them in config.env.")
        return
    try:
        answer, complete = investigate(instance_id, time_str, reason, remaining_s)
        if not answer.strip():
            answer = "The agent returned an empty answer. Investigate manually, starting at the incident time above."
        elif not complete:
            answer = ("[Partial — the investigation ran out of time. What Kira had found so far:]\n\n" + answer)
    except Exception as e:
        answer = (f"Automatic investigation failed: {type(e).__name__}: {e}\n\n"
                  "Investigate manually, starting at the incident time above.")
    publish_report(instance_id, time_str, reason, answer)


def lambda_handler(event, context):
    remaining_s = (lambda: context.get_remaining_time_in_millis() / 1000) if context else (lambda: 600.0)
    failures = []
    for record in event.get("Records", []):
        raw = (record.get("Sns") or {}).get("Message", "")
        try:
            body = json.loads(raw)
        except (TypeError, ValueError):
            print(f"Ignoring non-JSON SNS message: {str(raw)[:200]!r}")
            continue
        if not isinstance(body, dict):
            print(f"Ignoring unexpected SNS message shape: {str(raw)[:200]!r}")
            continue
        try:
            handle_record(body, remaining_s)
        except Exception as e:
            failures.append(f"{type(e).__name__}: {e}")
            print(f"Could not deliver incident report: {failures[-1]}")
    if failures:
        # Surfaces in the Lambda's Errors metric, which the watcher alarm emails about.
        raise RuntimeError(f"{len(failures)} incident report(s) not delivered: {failures}")


if __name__ == "__main__":
    from unittest.mock import MagicMock, patch

    ALARM = {"AlarmName": "aiops-i-0123456789abcdef0-nginx-errors", "NewStateValue": "ALARM",
             "NewStateReason": "Threshold Crossed", "StateChangeTime": "2026-09-24T10:15:32.123+0000",
             "Trigger": {"Dimensions": []}}

    def _configure():
        global AGENT_ID, AGENT_ALIAS_ID, REPORTS_TOPIC_ARN
        AGENT_ID, AGENT_ALIAS_ID, REPORTS_TOPIC_ARN = "agent-1", "alias-1", "arn:aws:sns:x:1:reports"

    def _clients(agent_chunks=None, agent_error=None, sns_error=None):
        sns, agent = MagicMock(), MagicMock()
        if sns_error:
            sns.publish.side_effect = sns_error
        if agent_error:
            agent.invoke_agent.side_effect = agent_error
        else:
            agent.invoke_agent.return_value = {"completion": [{"chunk": {"bytes": c.encode()}} for c in agent_chunks or []]}
        return sns, agent, (lambda service, **kw: agent if service == "bedrock-agent-runtime" else sns)

    def test_parsing():
        assert extract_incident({**ALARM, "NewStateValue": "OK"}) == (None, None, None)
        assert extract_incident(ALARM)[:2] == ("i-0123456789abcdef0", "2026-09-24 10:15:32")
        dims = {**ALARM, "AlarmName": "someone-elses-alarm",
                "Trigger": {"Dimensions": [{"name": "InstanceId", "value": "i-0fedcba9876543210"}]}}
        assert extract_incident(dims)[0] == "i-0fedcba9876543210"
        ec2 = {"detail-type": "EC2 Instance State-change Notification", "time": "2026-09-24T10:15:32Z",
               "detail": {"instance-id": "i-0123456789abcdef0", "state": "stopping"}}
        assert extract_incident(ec2) == (None, None, None)
        ec2["detail"]["state"] = "terminated"
        assert extract_incident(ec2)[:2] == ("i-0123456789abcdef0", "2026-09-24 10:15:32")
        assert extract_incident({**ALARM, "StateChangeTime": "garbage"})[1]  # falls back to now, doesn't raise

    def test_success_emails_the_answer():
        _configure()
        sns, _, factory = _clients(agent_chunks=["Root cause: ", "PDF render hung"])
        with patch("boto3.client", side_effect=factory):
            lambda_handler({"Records": [{"Sns": {"Message": json.dumps(ALARM)}}]}, None)
        assert "Root cause: PDF render hung" in sns.publish.call_args.kwargs["Message"]

    def test_agent_failure_still_emails():
        _configure()
        sns, _, factory = _clients(agent_error=RuntimeError("model access denied"))
        with patch("boto3.client", side_effect=factory):
            lambda_handler({"Records": [{"Sns": {"Message": json.dumps(ALARM)}}]}, None)
        assert "failed" in sns.publish.call_args.kwargs["Message"]

    def test_deadline_sends_partial_answer_instead_of_dying():
        _configure()
        sns, _, factory = _clients(agent_chunks=["found X", " then Y", " then Z"])
        clock = iter([600, 500, 40, 30, 20])  # time left: plenty, then under the safety margin
        with patch("boto3.client", side_effect=factory):
            handle_record(ALARM, lambda: next(clock))
        message = sns.publish.call_args.kwargs["Message"]
        assert "[Partial" in message and "found X" in message and "then Z" not in message

    def test_bad_messages_are_ignored_not_crashing():
        _configure()
        sns, agent, factory = _clients(agent_chunks=["x"])
        with patch("boto3.client", side_effect=factory):
            lambda_handler({"Records": [{"Sns": {"Message": "not json"}}, {"Sns": {"Message": "[1, 2]"}},
                                        {"Sns": {"Message": json.dumps({"hello": "world"})}}]}, None)
        agent.invoke_agent.assert_not_called()
        sns.publish.assert_not_called()

    def test_sns_failure_raises_so_the_watcher_alarm_fires():
        _configure()
        _, _, factory = _clients(agent_chunks=["x"], sns_error=RuntimeError("AuthorizationError"))
        with patch("boto3.client", side_effect=factory):
            try:
                lambda_handler({"Records": [{"Sns": {"Message": json.dumps(ALARM)}}]}, None)
                raise AssertionError("expected a raise")
            except RuntimeError as e:
                assert "not delivered" in str(e)

    for test in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        test()
    print("trigger_investigation self-check OK")
