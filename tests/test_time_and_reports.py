import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from kira.time import parse_utc
from kira.transport import SNS_MESSAGE_BYTES
from tests.helpers import load_lambda

logs = load_lambda("fetch_logs")
metrics = load_lambda("fetch_metrics")
trigger = load_lambda("trigger_investigation")
FIXTURE = json.loads(
    (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "docs/implementation/phase-0/fixtures.json"
    ).read_text()
)


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-09-24T15:00:00+05:00",
        "2026-09-24T050000-05:00".replace("050000", "05:00:00"),
        "2026-09-24T10:00:00Z",
        "2026-09-24 10:00:00",
        "2026-09-24T15:00:00+0500",
    ],
)
def test_equivalent_times(stamp):
    expected = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)
    assert parse_utc(stamp) == logs.parse_time(stamp) == expected
    start, end = metrics.resolve_window({"time_string": stamp}, datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert start + (end - start) / 2 == expected


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-09-24",
        "garbage",
        "2026-09-24T15:00:00+24:00",
        "2026-09-24T15:00:00+00:60",
        "2026-09-24 10:00:00injected",
        None,
    ],
)
def test_invalid_times_rejected(stamp):
    with pytest.raises(ValueError):
        parse_utc(stamp)


def test_invalid_alarm_is_degraded_with_raw_time_and_no_investigation(monkeypatch):
    monkeypatch.setattr(trigger, "REPORTS_TOPIC_ARN", "synthetic-topic")
    client = MagicMock()
    alarm = {**FIXTURE["alarm"], "StateChangeTime": "malformed-time"}
    with patch.object(trigger, "investigate") as investigate, patch("boto3.client", return_value=client):
        trigger.handle_record(alarm, lambda: 600, "2026-10-01T11:00:00Z")
    investigate.assert_not_called()
    message = client.publish.call_args.kwargs["Message"]
    assert "degraded" in message and "malformed-time" in message and '"incident_time":null' in message
    assert '"received_at":"2026-10-01T11:00:00Z"' in message


def test_alarm_descriptor_and_clock_meanings_reach_prompt():
    context = trigger.incident_context(FIXTURE["alarm"], "2026-10-01T11:00:00Z")
    prompt = trigger.build_prompt(FIXTURE["instance_id"], "2026-09-24 10:15:32", "alarm", context)
    assert '"Dimensions":[]' in prompt and '"Namespace":"AIOpsNginx"' in prompt
    assert context["incident_time_basis"] == "alarm_state_change"
    assert context["raw_source_time"] == FIXTURE["alarm"]["StateChangeTime"]
    assert context["state_change_time"] != context["received_at"]


@pytest.mark.parametrize(
    "text", ["a" * 262000, "a" * 300000, "界" * 100000, "🙂" * 100000, "", None, {"wrong": "type"}]
)
def test_sns_full_payload_bytes(text):
    sns = MagicMock()
    with patch("boto3.client", return_value=sns):
        trigger.publish_report(FIXTURE["instance_id"], "2026-09-24 10:15:32", "原因" * 4000, text)
    payload = sns.publish.call_args.kwargs
    assert 0 < len(payload["Message"].encode("utf-8")) <= SNS_MESSAGE_BYTES
    assert len(payload["Subject"]) < 100
    if text and isinstance(text, str) and len(text.encode()) > SNS_MESSAGE_BYTES:
        assert payload["Message"].endswith("[truncated; additional evidence omitted]")


@pytest.mark.parametrize("instance", ["x" * 100, "injected\nsubject", "control\x7f"])
def test_invalid_subject_never_published(instance):
    with patch("boto3.client") as client, pytest.raises(ValueError):
        trigger.publish_report(instance, "time", "reason", "report")
    client.assert_not_called()
