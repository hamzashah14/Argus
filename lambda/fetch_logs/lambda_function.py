"""Bedrock Agent tool: list an instance's log groups, or search one around an incident."""
import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

MONITOR_REGION = os.environ.get("MONITOR_REGION") or os.environ.get("AWS_REGION")
LOG_GROUP_PREFIX = (os.environ.get("LOG_GROUP_PREFIX") or "/aiops").rstrip("/")
BOTO_CONFIG = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"})

# Bedrock rejects an action group's Lambda response over 25 KB.
MAX_BODY_BYTES = 20_000
MAX_MESSAGE_CHARS = 500
DEFAULT_LINES, MAX_LINES = 20, 50
DEFAULT_WINDOW_MINUTES, MAX_WINDOW_MINUTES = 30, 180
DEFAULT_HOURS_BACK, MAX_HOURS_BACK = 1, 24
MAX_ACTIVITY_BINS = 60
MIN_GAP_MINUTES = 2
# CloudWatch Logs ingestion can lag a few minutes, so zero-line bins right up
# to "now" aren't evidence of silence.
INGESTION_LAG = timedelta(minutes=3)
TIME_FMT = "%Y-%m-%d %H:%M:%S"
BIN_FMT = "%Y-%m-%d %H:%M"

INSTANCE_ID_RE = re.compile(r"^i-(?:[0-9a-f]{8}|[0-9a-f]{17})$")
LOG_GROUP_RE = re.compile(r"^[A-Za-z0-9_\-./#]+$")
_REGEX_SPECIAL = set(".^$*+?()[]{}|\\/")


class BadInput(ValueError):
    pass


class QueryFailed(RuntimeError):
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


def parse_instance_id(raw):
    if not raw:
        return None
    raw = str(raw).strip()
    if not INSTANCE_ID_RE.match(raw):
        raise BadInput(f"instance_id {raw!r} is not an EC2 instance ID (i- followed by 8 or 17 hex characters).")
    return raw


def parse_log_group(raw):
    if not raw:
        return None
    raw = str(raw).strip()
    if not LOG_GROUP_RE.match(raw) or not raw.startswith(LOG_GROUP_PREFIX + "/"):
        raise BadInput(
            f"log_group_name must be a log group under {LOG_GROUP_PREFIX}/. "
            "Call fetch_logs with only instance_id to list the valid ones."
        )
    return raw


def parse_time(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip().replace("T", " ")[:19], TIME_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        raise BadInput("time_string must be formatted as YYYY-MM-DD HH:MM:SS (UTC).")


def _escape(text):
    return "".join("\\" + c if c in _REGEX_SPECIAL else c for c in text)


def build_text_filter(text):
    """Insights clause for the agent's search text: plain text, "a|b" alternatives,
    or CloudWatch-style ?a ?"b c" OR-terms, always case-insensitive. Empty = all lines."""
    text = (text or "").strip()
    if not text:
        return ""
    if "|" in text:
        alts = text.split("|")
    elif text.startswith("?"):
        alts = [a or b for a, b in re.findall(r'\?"([^"]*)"|\?(\S+)', text)]
    else:
        alts = [text]
    alts = [a.strip().strip('"').strip() for a in alts]
    alts = [a for a in alts if a]
    if not alts:
        return ""
    return f"| filter @message like /(?i)({'|'.join(_escape(a) for a in alts)})/ "


def stream_clause(log_group, instance_id):
    # A group under <prefix>/<instance-id>/ already belongs to that instance, and
    # Docker's awslogs driver names its streams after container IDs, not instance
    # IDs — filtering on the stream there would silently match nothing.
    if not instance_id or log_group.startswith(f"{LOG_GROUP_PREFIX}/{instance_id}/"):
        return ""
    return f"| filter @logStream = '{instance_id}' "


def lines_query(where, order, limit):
    return f"fields @timestamp, @message {where}| sort @timestamp {order} | limit {limit}"


def activity_query(stream, bin_minutes):
    return f"fields @timestamp {stream}| stats count(*) as lines by bin({bin_minutes}m)"


def _row_to_dict(row):
    return {field["field"]: field["value"] for field in row}


def discover_log_groups(client, instance_id):
    prefix = f"{LOG_GROUP_PREFIX}/{instance_id}/"
    names, token = [], None
    for _ in range(5):
        kwargs = {"logGroupNamePrefix": prefix, "limit": 50}
        if token:
            kwargs["nextToken"] = token
        response = client.describe_log_groups(**kwargs)
        names += [g["logGroupName"] for g in response.get("logGroups", [])]
        token = response.get("nextToken")
        if not token:
            break
    if not names:
        return {
            "status": "no_log_groups_found",
            "message": (
                f"No log groups under {prefix}. Nothing on this instance ships logs there yet "
                "(CWAgent/awslogs not configured for this naming), or the instance ID is wrong."
            ),
        }
    return {"status": "log_groups_found", "instance_id": instance_id, "log_groups": names}


def run_queries(client, log_group, queries, deadline):
    """Start every query at once, then poll until all finish or the deadline passes.
    queries: {name: (query_string, start_dt, end_dt)} -> {name: [row dict, ...]}"""
    ids = {}
    try:
        for name, (query, start, end) in queries.items():
            ids[name] = client.start_query(
                logGroupName=log_group,
                startTime=int(start.timestamp()),
                endTime=int(end.timestamp()),
                queryString=query,
            )["queryId"]
        results, pending = {}, dict(ids)
        while pending:
            for name, query_id in list(pending.items()):
                response = client.get_query_results(queryId=query_id)
                status = response["status"]
                if status == "Complete":
                    results[name] = [_row_to_dict(row) for row in response.get("results", [])]
                    del pending[name]
                elif status in ("Failed", "Cancelled", "Timeout", "Unknown"):
                    raise QueryFailed(f"Logs Insights query {status.lower()}.")
            if pending:
                if time.monotonic() > deadline:
                    raise QueryFailed("Logs Insights didn't finish in time — try a smaller window_minutes.")
                time.sleep(1)
        return results
    except Exception:
        for query_id in ids.values():
            try:
                client.stop_query(queryId=query_id)
            except Exception:
                pass
        raise


def summarize_activity(rows, start, end, bin_minutes, now):
    """Log lines per bin across the whole window, and runs of empty bins
    (a frozen process usually shows up as silence, not as an error line)."""
    counts = {}
    for row in rows:
        bucket = next((v for k, v in row.items() if k.startswith("bin(")), None)
        if bucket:
            counts[bucket[:16]] = counts.get(bucket[:16], 0) + int(float(row.get("lines", 0)))

    step = bin_minutes * 60
    bins, t = [], int(start.timestamp()) // step * step
    while t < end.timestamp():
        key = datetime.fromtimestamp(t, timezone.utc).strftime(BIN_FMT)
        bins.append((key, counts.get(key, 0)))
        t += step

    gaps, run = [], []
    for key, n in bins + [(None, 1)]:
        if key is not None and n == 0:
            run.append(key)
            continue
        if run and len(run) * bin_minutes >= MIN_GAP_MINUTES:
            gap_end =datetime.strptime(run[-1], BIN_FMT).replace(tzinfo=timezone.utc) + timedelta(minutes=bin_minutes)
            gap = {"from": run[0], "to": gap_end.strftime(BIN_FMT), "minutes": len(run) * bin_minutes}
            if gap_end >= now - INGESTION_LAG:
                gap["note"] = "reaches the present — may just be log ingestion delay, not silence"
            gaps.append(gap)
        run = []

    return {
        "bin_minutes": bin_minutes,
        "total_lines": sum(n for _, n in bins),
        "silent_gaps": gaps,
        "lines_per_bin": " ".join(f"{k[11:]}={n}" for k, n in bins),
    }


def _format_lines(rows):
    lines = []
    for row in rows:
        message = (row.get("@message") or "").strip()
        if len(message) > MAX_MESSAGE_CHARS:
            message = message[:MAX_MESSAGE_CHARS] + " …[truncated]"
        lines.append({"timestamp": (row.get("@timestamp") or "")[:19], "message": message})
    return lines


def fit_to_budget(result):
    """Serialize, dropping the lines farthest from the incident until it fits."""
    body = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
    while len(body.encode("utf-8")) > MAX_BODY_BYTES:
        trimmed = False
        for key, index in (("lines_before", 0), ("lines_after", -1), ("lines", 0)):
            if result.get(key):
                result[key].pop(index)
                trimmed = True
        if not trimmed:
            break
        result["truncated"] = "some lines dropped to fit the response size limit"
        body = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
    return body


def search(params, deadline):
    instance_id = parse_instance_id(params.get("instance_id"))
    log_group = parse_log_group(params.get("log_group_name"))
    client = boto3.client("logs", region_name=MONITOR_REGION, config=BOTO_CONFIG)

    if not log_group:
        if not instance_id:
            raise BadInput("Pass log_group_name, or instance_id on its own to list that instance's log groups.")
        return discover_log_groups(client, instance_id)

    filter_text = params.get("filter_text", params.get("filter_pattern", ""))
    text_clause = build_text_filter(filter_text)
    limit = _int_param(params, "lines", DEFAULT_LINES, 1, MAX_LINES)
    anchor = parse_time(params.get("time_string"))
    now = datetime.now(timezone.utc)
    stream = stream_clause(log_group, instance_id)
    where = stream + text_clause

    if anchor:
        if anchor > now:
            raise BadInput(f"time_string {anchor.strftime(TIME_FMT)} is in the future (now is {now.strftime(TIME_FMT)} UTC).")
        window = _int_param(params, "window_minutes", DEFAULT_WINDOW_MINUTES, 1, MAX_WINDOW_MINUTES)
        start, end = anchor - timedelta(minutes=window), min(anchor + timedelta(minutes=window), now)
        queries = {"before": (lines_query(where, "desc", limit), start, anchor)}
        if end > anchor:
            queries["after"] = (lines_query(where, "asc", limit), anchor, end)
    else:
        hours = _int_param(params, "hours_back", DEFAULT_HOURS_BACK, 1, MAX_HOURS_BACK)
        start, end = now - timedelta(hours=hours), now
        queries = {"recent": (lines_query(where, "desc", limit), start, end)}

    bin_minutes = max(1, math.ceil((end - start).total_seconds() / 60 / MAX_ACTIVITY_BINS))
    queries["activity"] = (activity_query(stream, bin_minutes), start, end)
    rows = run_queries(client, log_group, queries, deadline)

    result = {
        "status": "ok",
        "log_group": log_group,
        "instance_id": instance_id,
        "filter_text": filter_text or None,
        "window_start": start.strftime(TIME_FMT),
        "window_end": end.strftime(TIME_FMT),
        "activity_all_lines": summarize_activity(rows["activity"], start, end, bin_minutes, now),
    }
    if anchor:
        result["incident_time"] = anchor.strftime(TIME_FMT)
        result["lines_before"] = _format_lines(reversed(rows["before"]))
        result["lines_after"] = _format_lines(rows.get("after", []))
        found = result["lines_before"] or result["lines_after"]
    else:
        result["lines"] = _format_lines(reversed(rows["recent"]))
        found = result["lines"]
    if not found:
        result["status"] = "no_matching_lines"
        result["message"] = "No lines matched in this window; activity_all_lines still shows whether anything was logged."
    return result


def _envelope(event, body):
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": 200,
            "responseBody": {"application/json": {"body": body}},
        },
    }


def lambda_handler(event, context):
    params = {p.get("name"): p.get("value") for p in event.get("parameters", [])}
    budget_s = context.get_remaining_time_in_millis() / 1000 - 5 if context else 25
    deadline = time.monotonic() + max(5, budget_s)
    try:
        result = search(params, deadline)
    except (BadInput, QueryFailed) as e:
        result = {"status": "error", "message": str(e)}
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "ResourceNotFoundException":
            result = {"status": "error", "message": f"Log group {params.get('log_group_name')!r} doesn't exist in {MONITOR_REGION}."}
        else:
            result = {"status": "error", "message": f"{code}: {e.response.get('Error', {}).get('Message', '')}"}
    except Exception as e:
        result = {"status": "error", "message": f"{type(e).__name__}: {e}"}
    return _envelope(event, fit_to_budget(result))


if __name__ == "__main__":
    from unittest.mock import MagicMock, patch

    IID = "i-0123456789abcdef0"

    def _body(response):
        return json.loads(response["response"]["responseBody"]["application/json"]["body"])

    def _call(params, client):
        event = {"parameters": [{"name": k, "value": v} for k, v in params.items()]}
        with patch("boto3.client", return_value=client):
            return _body(lambda_handler(event, None))

    def _fake_insights(rows_for):
        """Mock client whose Insights results depend on the query text."""
        client = MagicMock()
        started = {}

        def start_query(**kw):
            qid = f"q{len(started)}"
            started[qid] = kw
            return {"queryId": qid}

        def get_query_results(queryId):
            kind = ("activity" if "stats" in started[queryId]["queryString"]
                    else "after" if "asc" in started[queryId]["queryString"] else "before")
            return {"status": "Complete", "results": rows_for(kind, started[queryId])}

        client.start_query.side_effect = start_query
        client.get_query_results.side_effect = get_query_results
        client.started = started
        return client

    def _row(**fields):
        return [{"field": k, "value": v} for k, v in fields.items()]

    def test_text_filter_forms():
        assert build_text_filter("") == ""
        assert build_text_filter("ERROR") == "| filter @message like /(?i)(ERROR)/ "
        assert build_text_filter("error|timeout") == "| filter @message like /(?i)(error|timeout)/ "
        assert build_text_filter('?ERROR ?"connect() failed"') == "| filter @message like /(?i)(ERROR|connect\\(\\) failed)/ "
        assert build_text_filter("a/b.c") == "| filter @message like /(?i)(a\\/b\\.c)/ "
        # a single quote used to break the Insights query string; inside /regex/ it's inert
        assert build_text_filter("can't connect") == "| filter @message like /(?i)(can't connect)/ "

    def test_validation():
        for bad in ("i-123", "i-XYZ0123456789abcd", "x' or 1=1"):
            try:
                parse_instance_id(bad)
                raise AssertionError(bad)
            except BadInput:
                pass
        assert parse_instance_id(IID) == IID
        try:
            parse_log_group("/var/secret/logs")
            raise AssertionError("group outside prefix accepted")
        except BadInput:
            pass

    def test_stream_filter_skipped_for_instance_scoped_group():
        assert stream_clause(f"/aiops/{IID}/mobilebff", IID) == ""
        assert stream_clause("/aiops/shared/app", IID) == f"| filter @logStream = '{IID}' "

    def test_discovery():
        client = MagicMock()
        client.describe_log_groups.return_value = {"logGroups": [{"logGroupName": f"/aiops/{IID}/webbff"}]}
        body = _call({"instance_id": IID}, client)
        assert body["status"] == "log_groups_found" and body["log_groups"] == [f"/aiops/{IID}/webbff"]
        assert client.describe_log_groups.call_args.kwargs["logGroupNamePrefix"] == f"/aiops/{IID}/"

    def test_anchored_search_splits_before_after_and_finds_gap():
        anchor = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(second=0, microsecond=0)

        def rows_for(kind, _):
            if kind == "before":  # returned newest-first
                return [_row(**{"@timestamp": (anchor - timedelta(minutes=m)).strftime(TIME_FMT), "@message": f"b{m}"})
                        for m in (1, 2, 3)]
            if kind == "after":
                return [_row(**{"@timestamp": (anchor + timedelta(minutes=9)).strftime(TIME_FMT), "@message": "a9"})]
            bins = [anchor + timedelta(minutes=m) for m in range(-10, 11) if not 0 <= m < 9]
            return [_row(**{"bin(1m)": b.strftime(TIME_FMT) + ".000", "lines": "4"}) for b in bins]

        client = _fake_insights(rows_for)
        body = _call({"log_group_name": f"/aiops/{IID}/webbff", "instance_id": IID,
                      "time_string": anchor.strftime(TIME_FMT), "window_minutes": "10", "filter_text": ""}, client)
        assert body["status"] == "ok", body
        assert [line["message"] for line in body["lines_before"]] == ["b3", "b2", "b1"]  # chronological
        assert body["lines_after"][0]["message"] == "a9"
        gaps = body["activity_all_lines"]["silent_gaps"]
        assert gaps == [{"from": anchor.strftime(BIN_FMT), "to": (anchor + timedelta(minutes=9)).strftime(BIN_FMT),
                         "minutes": 9}], gaps
        assert all("@logStream" not in kw["queryString"] for kw in client.started.values())

    def test_window_never_extends_past_now():
        anchor = datetime.now(timezone.utc) - timedelta(minutes=5)
        client = _fake_insights(lambda kind, _: [])
        body = _call({"log_group_name": f"/aiops/{IID}/sso", "time_string": anchor.strftime(TIME_FMT)}, client)
        assert max(kw["endTime"] for kw in client.started.values()) <= int(datetime.now(timezone.utc).timestamp()) + 1
        assert body["status"] == "no_matching_lines"
        assert all("note" in g for g in body["activity_all_lines"]["silent_gaps"] if g["to"] >= body["window_end"][:16])

    def test_response_stays_under_bedrock_limit():
        big = "x" * 5000
        client = _fake_insights(lambda kind, _: [] if kind == "activity" else
                                [_row(**{"@timestamp": "2026-01-01 00:00:00", "@message": big})] * 50)
        anchor = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(TIME_FMT)
        event = {"parameters": [{"name": "log_group_name", "value": f"/aiops/{IID}/sso"},
                                {"name": "time_string", "value": anchor}, {"name": "lines", "value": "50"}]}
        with patch("boto3.client", return_value=client):
            raw = lambda_handler(event, None)["response"]["responseBody"]["application/json"]["body"]
        assert len(raw.encode()) <= MAX_BODY_BYTES
        assert json.loads(raw)["truncated"]

    def test_bad_inputs_return_errors_not_crashes():
        client = MagicMock()
        for params in ({"log_group_name": f"/aiops/{IID}/sso", "hours_back": "two"},
                       {"log_group_name": f"/aiops/{IID}/sso", "time_string": "yesterday"},
                       {"log_group_name": f"/aiops/{IID}/sso", "time_string": "2999-01-01 00:00:00"},
                       {}):
            assert _call(params, client)["status"] == "error", params

    def test_query_timeout_stops_queries():
        client = MagicMock()
        client.start_query.return_value = {"queryId": "q"}
        client.get_query_results.return_value = {"status": "Running", "results": []}
        with patch("time.sleep"):
            try:
                run_queries(client, "/aiops/x/y", {"a": ("q", datetime.now(timezone.utc), datetime.now(timezone.utc))},
                            deadline=time.monotonic() - 1)
                raise AssertionError("no timeout")
            except QueryFailed:
                pass
        assert client.stop_query.called

    for test in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        test()
    print("fetch_logs self-check OK")
