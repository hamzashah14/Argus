import json
from unittest.mock import MagicMock, patch

"""Migrated original self-checks; behavior changes are documented in Phase 1 notes."""
from tests.helpers import load_lambda

target = load_lambda("fetch_metrics")

IID = "i-0123456789abcdef0"


def _call(response=None, **params):
    params.setdefault("instance_id", IID)
    event = {"parameters": [{"name": k, "value": v} for k, v in params.items() if v is not None]}
    client = MagicMock()
    client.get_metric_statistics.return_value = response or {"Datapoints": []}
    with patch("boto3.client", return_value=client):
        body = json.loads(
            target.lambda_handler(event, None)["response"]["responseBody"]["application/json"]["body"]
        )
    return (body, client)


def _kwargs(client):
    return client.get_metric_statistics.call_args.kwargs


def test_namespace_inference():
    for metric, ns in (
        ("CPUUtilization", "AWS/EC2"),
        ("CPUCreditBalance", "AWS/EC2"),
        ("StatusCheckFailed_System", "AWS/EC2"),
        ("mem_used_percent", "CWAgent"),
    ):
        _, client = _call(metric_name=metric)
        assert _kwargs(client)["Namespace"] == ns, metric
    body, client = _call(metric_name="CPUUtilization", namespace="Custom/App")
    assert body["status"] == "error"
    client.get_metric_statistics.assert_not_called()


def test_disk_path_dimension():
    _, client = _call(metric_name="disk_used_percent", path="/")
    assert _kwargs(client)["Dimensions"] == [
        {"Name": "InstanceId", "Value": IID},
        {"Name": "path", "Value": "/"},
    ]


def test_period_keeps_points_bounded_and_respects_retention():
    now = target.datetime.now(target.timezone.utc)
    assert target.pick_period(now - target.timedelta(hours=72), now, 1, now) == 72 * 3600 // 60
    three_weeks = now - target.timedelta(days=21)
    assert target.pick_period(three_weeks, three_weeks + target.timedelta(hours=1), 1, now) % 300 == 0
    old = now - target.timedelta(days=90)
    assert target.pick_period(old, old + target.timedelta(hours=1), 1, now) % 3600 == 0


def test_window_clamped_to_now():
    body, client = _call(
        time_string=(target.datetime.now(target.timezone.utc) - target.timedelta(minutes=2)).strftime(
            target.TIME_FMT
        )
    )
    assert _kwargs(client)["EndTime"] <= target.datetime.now(target.timezone.utc)
    assert body["status"] == "no_data"


def test_summary():
    ts = target.datetime(2026, 9, 24, 10, 0, tzinfo=target.timezone.utc)
    points = [
        {"Timestamp": ts + target.timedelta(minutes=i), "Average": v, "Unit": "Percent"}
        for i, v in enumerate([10, 50, 30])
    ]
    body, _ = _call(response={"Datapoints": list(reversed(points))})
    assert body["summary"] == {"first": 10, "last": 30, "average": 30.0, "maximum": 50, "minimum": 10}
    assert body["datapoints"][0] == {"timestamp": "2026-09-24T10:00:00Z", "value": 10}


def test_bad_inputs_are_errors_not_crashes():
    for params in (
        {"instance_id": ""},
        {"instance_id": "i-bad"},
        {"hours_back": "lots"},
        {"statistic": "p99"},
        {"time_string": "2999-01-01 00:00:00"},
        {"path": "../etc"},
        {"metric_name": "cpu; drop"},
    ):
        body, client = _call(**params)
        assert body["status"] == "error", params
        client.get_metric_statistics.assert_not_called()
