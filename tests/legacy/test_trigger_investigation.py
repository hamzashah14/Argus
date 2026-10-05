import json
from unittest.mock import MagicMock, patch

"""Migrated original self-checks; behavior changes are documented in Phase 1 notes."""
from tests.helpers import load_lambda

target = load_lambda("trigger_investigation")

ALARM = {
    "AlarmName": "aiops-i-0123456789abcdef0-nginx-errors",
    "NewStateValue": "ALARM",
    "NewStateReason": "Threshold Crossed",
    "StateChangeTime": "2026-09-24T10:15:32.123+0000",
    "Trigger": {"Dimensions": []},
}


def _configure():
    target.AGENT_ID, target.AGENT_ALIAS_ID, target.REPORTS_TOPIC_ARN = (
        "agent-1",
        "alias-1",
        "arn:aws:sns:x:1:reports",
    )


def _clients(agent_chunks=None, agent_error=None, sns_error=None):
    sns, agent = (MagicMock(), MagicMock())
    if sns_error:
        sns.publish.side_effect = sns_error
    if agent_error:
        agent.invoke_agent.side_effect = agent_error
    else:
        agent.invoke_agent.return_value = {
            "completion": [{"chunk": {"bytes": c.encode()}} for c in agent_chunks or []]
        }
    return (sns, agent, lambda service, **kw: agent if service == "bedrock-agent-runtime" else sns)


def test_parsing():
    assert target.extract_incident({**ALARM, "NewStateValue": "OK"}) == (None, None, None)
    assert target.extract_incident(ALARM)[:2] == ("i-0123456789abcdef0", "2026-09-24 10:15:32")
    dims = {
        **ALARM,
        "AlarmName": "someone-elses-alarm",
        "Trigger": {"Dimensions": [{"name": "InstanceId", "value": "i-0fedcba9876543210"}]},
    }
    assert target.extract_incident(dims)[0] == "i-0fedcba9876543210"
    ec2 = {
        "detail-type": "EC2 Instance State-change Notification",
        "time": "2026-09-24T10:15:32Z",
        "detail": {"instance-id": "i-0123456789abcdef0", "state": "stopping"},
    }
    assert target.extract_incident(ec2) == (None, None, None)
    ec2["detail"]["state"] = "terminated"
    assert target.extract_incident(ec2)[:2] == ("i-0123456789abcdef0", "2026-09-24 10:15:32")
    assert target.extract_incident({**ALARM, "StateChangeTime": "garbage"})[1] is None


def test_success_emails_the_answer():
    _configure()
    sns, _, factory = _clients(agent_chunks=["Root cause: ", "PDF render hung"])
    with patch("boto3.client", side_effect=factory):
        target.lambda_handler({"Records": [{"Sns": {"Message": json.dumps(ALARM)}}]}, None)
    assert "Root cause: PDF render hung" in sns.publish.call_args.kwargs["Message"]


def test_agent_failure_still_emails():
    _configure()
    sns, _, factory = _clients(agent_error=RuntimeError("model access denied"))
    with patch("boto3.client", side_effect=factory):
        target.lambda_handler({"Records": [{"Sns": {"Message": json.dumps(ALARM)}}]}, None)
    assert "failed" in sns.publish.call_args.kwargs["Message"]


def test_deadline_sends_partial_answer_instead_of_dying():
    _configure()
    sns, _, factory = _clients(agent_chunks=["found X", " then Y", " then Z"])
    clock = iter([600, 500, 40, 30, 20])
    with patch("boto3.client", side_effect=factory):
        target.handle_record(ALARM, lambda: next(clock))
    message = sns.publish.call_args.kwargs["Message"]
    assert "[Partial" in message and "found X" in message and ("then Z" not in message)


def test_bad_messages_are_ignored_not_crashing():
    _configure()
    sns, agent, factory = _clients(agent_chunks=["x"])
    with patch("boto3.client", side_effect=factory):
        target.lambda_handler(
            {
                "Records": [
                    {"Sns": {"Message": "not json"}},
                    {"Sns": {"Message": "[1, 2]"}},
                    {"Sns": {"Message": json.dumps({"hello": "world"})}},
                ]
            },
            None,
        )
    agent.invoke_agent.assert_not_called()
    sns.publish.assert_not_called()


def test_sns_failure_raises_so_the_watcher_alarm_fires():
    _configure()
    _, _, factory = _clients(agent_chunks=["x"], sns_error=RuntimeError("AuthorizationError"))
    with patch("boto3.client", side_effect=factory):
        try:
            target.lambda_handler({"Records": [{"Sns": {"Message": json.dumps(ALARM)}}]}, None)
            raise AssertionError("expected a raise")
        except RuntimeError as e:
            assert "not delivered" in str(e)
