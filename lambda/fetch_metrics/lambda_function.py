"""Bedrock Agent tool: one CloudWatch metric for one EC2 instance, around an incident."""
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

MONITOR_REGION = os.environ.get("MONITOR_REGION") or os.environ.get("AWS_REGION")
BOTO_CONFIG = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"})

# Metrics AWS publishes itself under AWS/EC2; anything else is assumed to be CWAgent.
EC2_METRICS = {
    "CPUUtilization", "CPUCreditBalance", "CPUCreditUsage", "CPUSurplusCreditBalance", "CPUSurplusCreditsCharged",
    "NetworkIn", "NetworkOut", "NetworkPacketsIn", "NetworkPacketsOut",
    "DiskReadBytes", "DiskWriteBytes", "DiskReadOps", "DiskWriteOps",
    "EBSReadOps", "EBSWriteOps", "EBSReadBytes", "EBSWriteBytes", "EBSIOBalance%", "EBSByteBalance%",
    "StatusCheckFailed", "StatusCheckFailed_Instance", "StatusCheckFailed_System", "StatusCheckFailed_AttachedEBS",
    "MetadataNoToken",
}
STATISTICS = {"Average", "Maximum", "Minimum", "Sum", "SampleCount"}
MAX_DATAPOINTS = 60
DEFAULT_WINDOW_MINUTES, MAX_WINDOW_MINUTES = 30, 180
DEFAULT_HOURS_BACK, MAX_HOURS_BACK = 1, 72
TIME_FMT = "%Y-%m-%d %H:%M:%S"

INSTANCE_ID_RE = re.compile(r"^i-(?:[0-9a-f]{8}|[0-9a-f]{17})$")
METRIC_RE = re.compile(r"^[A-Za-z0-9_\-.%]{1,255}$")
NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_\-./]{1,255}$")
PATH_RE = re.compile(r"^/[\w\-./]*$")


class BadInput(ValueError):
    pass


def _int_param(params, name, default, lo, hi):
    raw = params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        raise BadInput(f"{name} must be a number, got {raw!r}.")
    return max(lo, min(hi, value))


def _match(params, name, pattern, what, default=None):
    raw = params.get(name)
    if raw in (None, ""):
        return default
    raw = str(raw).strip()
    if not pattern.match(raw):
        raise BadInput(f"{name} {raw!r} is not a valid {what}.")
    return raw


def resolve_window(params, now):
    raw_time = params.get("time_string")
    if raw_time:
        try:
            anchor = datetime.strptime(str(raw_time).strip().replace("T", " ")[:19], TIME_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            raise BadInput("time_string must be formatted as YYYY-MM-DD HH:MM:SS (UTC).")
        if anchor > now:
            raise BadInput(f"time_string is in the future (now is {now.strftime(TIME_FMT)} UTC).")
        window = timedelta(minutes=_int_param(params, "window_minutes", DEFAULT_WINDOW_MINUTES, 1, MAX_WINDOW_MINUTES))
        return anchor - window, min(anchor + window, now)
    hours = _int_param(params, "hours_back", DEFAULT_HOURS_BACK, 1, MAX_HOURS_BACK)
    return now - timedelta(hours=hours), now


def pick_period(start, end, requested_minutes, now):
    """Seconds per datapoint: at least what was asked, few enough points to keep the
    response small, and coarse enough for CloudWatch's retention on older data
    (1-minute points only exist for 15 days, 5-minute points for 63)."""
    period = max(60, requested_minutes * 60, math.ceil((end - start).total_seconds() / MAX_DATAPOINTS / 60) * 60)
    age = now - start
    if age > timedelta(days=63):
        return math.ceil(period / 3600) * 3600
    if age > timedelta(days=15):
        return math.ceil(period / 300) * 300
    return period


def fetch(params):
    instance_id = _match(params, "instance_id", INSTANCE_ID_RE, "EC2 instance ID")
    if not instance_id:
        raise BadInput("instance_id is required.")
    metric_name = _match(params, "metric_name", METRIC_RE, "metric name", default="CPUUtilization")
    namespace = _match(params, "namespace", NAMESPACE_RE, "namespace") or (
        "AWS/EC2" if metric_name in EC2_METRICS else "CWAgent")
    statistic = params.get("statistic") or "Average"
    if statistic not in STATISTICS:
        raise BadInput(f"statistic must be one of {sorted(STATISTICS)}.")
    path = _match(params, "path", PATH_RE, "filesystem path")

    now = datetime.now(timezone.utc)
    start, end = resolve_window(params, now)
    period = pick_period(start, end, _int_param(params, "period_minutes", 1, 1, 1440), now)

    dimensions = [{"Name": "InstanceId", "Value": instance_id}]
    if path:
        dimensions.append({"Name": "path", "Value": path})

    client = boto3.client("cloudwatch", region_name=MONITOR_REGION, config=BOTO_CONFIG)
    response = client.get_metric_statistics(
        Namespace=namespace, MetricName=metric_name, Dimensions=dimensions,
        StartTime=start, EndTime=end, Period=period, Statistics=[statistic],
    )
    datapoints = sorted(response.get("Datapoints", []), key=lambda d: d["Timestamp"])
    base = {
        "metric": metric_name, "namespace": namespace, "instance_id": instance_id, "path": path,
        "statistic": statistic, "period_seconds": period,
        "window_start": start.strftime(TIME_FMT), "window_end": end.strftime(TIME_FMT),
    }
    if not datapoints:
        hint = ("CWAgent metrics need the agent running on this instance with append_dimensions.InstanceId "
                "(and aggregation_dimensions for disk metrics)." if namespace == "CWAgent" else
                "The instance may have been stopped during this window.")
        return {"status": "no_data", **base, "message": f"No datapoints in this window. {hint}"}

    values = [dp[statistic] for dp in datapoints]
    return {
        "status": "ok", **base,
        "unit": datapoints[0].get("Unit", "None"),
        "summary": {
            "first": round(values[0], 2), "last": round(values[-1], 2),
            "average": round(sum(values) / len(values), 2),
            "maximum": round(max(values), 2), "minimum": round(min(values), 2),
        },
        "datapoints": [[dp["Timestamp"].strftime("%Y-%m-%d %H:%M"), round(dp[statistic], 2)] for dp in datapoints],
    }


def _envelope(event, result):
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": 200,
            "responseBody": {"application/json": {"body": json.dumps(result, separators=(",", ":"))}},
        },
    }


def lambda_handler(event, context):
    params = {p.get("name"): p.get("value") for p in event.get("parameters", [])}
    try:
        result = fetch(params)
    except BadInput as e:
        result = {"status": "error", "message": str(e)}
    except ClientError as e:
        err = e.response.get("Error", {})
        result = {"status": "error", "message": f"{err.get('Code', '')}: {err.get('Message', '')}"}
    except Exception as e:
        result = {"status": "error", "message": f"{type(e).__name__}: {e}"}
    return _envelope(event, result)


if __name__ == "__main__":
    from unittest.mock import MagicMock, patch

    IID = "i-0123456789abcdef0"

    def _call(response=None, **params):
        params.setdefault("instance_id", IID)
        event = {"parameters": [{"name": k, "value": v} for k, v in params.items() if v is not None]}
        client = MagicMock()
        client.get_metric_statistics.return_value = response or {"Datapoints": []}
        with patch("boto3.client", return_value=client):
            body = json.loads(lambda_handler(event, None)["response"]["responseBody"]["application/json"]["body"])
        return body, client

    def _kwargs(client):
        return client.get_metric_statistics.call_args.kwargs

    def test_namespace_inference():
        for metric, ns in (("CPUUtilization", "AWS/EC2"), ("CPUCreditBalance", "AWS/EC2"),
                           ("StatusCheckFailed_System", "AWS/EC2"), ("mem_used_percent", "CWAgent")):
            _, client = _call(metric_name=metric)
            assert _kwargs(client)["Namespace"] == ns, metric
        _, client = _call(metric_name="CPUUtilization", namespace="Custom/App")
        assert _kwargs(client)["Namespace"] == "Custom/App"

    def test_disk_path_dimension():
        _, client = _call(metric_name="disk_used_percent", path="/")
        assert _kwargs(client)["Dimensions"] == [{"Name": "InstanceId", "Value": IID}, {"Name": "path", "Value": "/"}]

    def test_period_keeps_points_bounded_and_respects_retention():
        now = datetime.now(timezone.utc)
        assert pick_period(now - timedelta(hours=72), now, 1, now) == 72 * 3600 // 60
        three_weeks = now - timedelta(days=21)
        assert pick_period(three_weeks, three_weeks + timedelta(hours=1), 1, now) % 300 == 0
        old = now - timedelta(days=90)
        assert pick_period(old, old + timedelta(hours=1), 1, now) % 3600 == 0

    def test_window_clamped_to_now():
        body, client = _call(time_string=(datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(TIME_FMT))
        assert _kwargs(client)["EndTime"] <= datetime.now(timezone.utc)
        assert body["status"] == "no_data"

    def test_summary():
        ts = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
        points = [{"Timestamp": ts + timedelta(minutes=i), "Average": v, "Unit": "Percent"} for i, v in enumerate([10, 50, 30])]
        body, _ = _call(response={"Datapoints": list(reversed(points))})
        assert body["summary"] == {"first": 10, "last": 30, "average": 30.0, "maximum": 50, "minimum": 10}
        assert body["datapoints"][0] == ["2026-09-24 10:00", 10]

    def test_bad_inputs_are_errors_not_crashes():
        for params in ({"instance_id": ""}, {"instance_id": "i-bad"}, {"hours_back": "lots"},
                       {"statistic": "p99"}, {"time_string": "2999-01-01 00:00:00"}, {"path": "../etc"},
                       {"metric_name": "cpu; drop"}):
            body, client = _call(**params)
            assert body["status"] == "error", params
            client.get_metric_statistics.assert_not_called()

    for test in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        test()
    print("fetch_metrics self-check OK")
