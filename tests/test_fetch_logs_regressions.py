"""Migrated original self-checks; behavior changes are documented in Phase 1 notes."""

import json
from unittest.mock import MagicMock, patch

from tests.helpers import load_lambda

target = load_lambda("fetch_logs")

IID = "i-0123456789abcdef0"


def _body(response):
    return json.loads(response["response"]["responseBody"]["application/json"]["body"])


def _call(params, client):
    event = {"parameters": [{"name": k, "value": v} for k, v in params.items()]}
    with patch("boto3.client", return_value=client):
        return _body(target.lambda_handler(event, None))


def _fake_insights(rows_for):
    """Mock client whose Insights results depend on the query text."""
    client = MagicMock()
    started = {}

    def start_query(**kw):
        qid = f"q{len(started)}"
        started[qid] = kw
        return {"queryId": qid}

    def get_query_results(queryId):
        kind = (
            "activity"
            if "stats" in started[queryId]["queryString"]
            else "after"
            if "asc" in started[queryId]["queryString"]
            else "before"
        )
        return {"status": "Complete", "results": rows_for(kind, started[queryId])}

    client.start_query.side_effect = start_query
    client.get_query_results.side_effect = get_query_results
    client.started = started
    return client


def _row(**fields):
    return [{"field": k, "value": v} for k, v in fields.items()]


def test_text_filter_forms():
    assert target.build_text_filter("") == ""
    assert target.build_text_filter("ERROR") == "| filter @message like /(?i)(ERROR)/ "
    assert target.build_text_filter("error|timeout") == "| filter @message like /(?i)(error|timeout)/ "
    assert (
        target.build_text_filter('?ERROR ?"connect() failed"')
        == "| filter @message like /(?i)(ERROR|connect\\(\\) failed)/ "
    )
    assert target.build_text_filter("a/b.c") == "| filter @message like /(?i)(a\\/b\\.c)/ "
    assert target.build_text_filter("can't connect") == "| filter @message like /(?i)(can't connect)/ "


def test_validation():
    for bad in ("i-123", "i-XYZ0123456789abcd", "x' or 1=1"):
        try:
            target.parse_instance_id(bad)
            raise AssertionError(bad)
        except target.BadInput:
            pass
    assert target.parse_instance_id(IID) == IID
    try:
        target.parse_log_group("/var/secret/logs")
        raise AssertionError("group outside prefix accepted")
    except target.BadInput:
        pass


def test_stream_filter_skipped_for_instance_scoped_group():
    assert target.stream_clause(f"/aiops/{IID}/mobilebff", IID) == ""
    assert target.stream_clause("/aiops/shared/app", IID) == f"| filter @logStream = '{IID}' "


def test_discovery():
    client = MagicMock()
    client.describe_log_groups.return_value = {"logGroups": [{"logGroupName": f"/aiops/{IID}/webbff"}]}
    body = _call({"instance_id": IID}, client)
    assert body["status"] == "log_groups_found" and body["log_groups"] == [f"/aiops/{IID}/webbff"]
    assert client.describe_log_groups.call_args.kwargs["logGroupNamePrefix"] == f"/aiops/{IID}/"


def test_anchored_search_splits_before_after_and_finds_gap():
    anchor = (target.datetime.now(target.timezone.utc) - target.timedelta(hours=2)).replace(
        second=0, microsecond=0
    )

    def rows_for(kind, _):
        if kind == "before":
            return [
                _row(
                    **{
                        "@timestamp": (anchor - target.timedelta(minutes=m)).strftime(target.TIME_FMT),
                        "@message": f"b{m}",
                    }
                )
                for m in (1, 2, 3)
            ]
        if kind == "after":
            return [
                _row(
                    **{
                        "@timestamp": (anchor + target.timedelta(minutes=9)).strftime(target.TIME_FMT),
                        "@message": "a9",
                    }
                )
            ]
        bins = [anchor + target.timedelta(minutes=m) for m in range(-10, 11) if not 0 <= m < 9]
        return [_row(**{"bin(1m)": b.strftime(target.TIME_FMT) + ".000", "lines": "4"}) for b in bins]

    client = _fake_insights(rows_for)
    body = _call(
        {
            "log_group_name": f"/aiops/{IID}/webbff",
            "instance_id": IID,
            "time_string": anchor.strftime(target.TIME_FMT),
            "window_minutes": "10",
            "filter_text": "",
        },
        client,
    )
    assert body["status"] == "ok", body
    assert [line["message"] for line in body["lines_before"]] == ["b3", "b2", "b1"]
    assert body["lines_after"][0]["message"] == "a9"
    gaps = body["activity_all_lines"]["silent_gaps"]
    assert gaps == [
        {
            "from": anchor.strftime(target.BIN_FMT),
            "to": (anchor + target.timedelta(minutes=9)).strftime(target.BIN_FMT),
            "minutes": 9,
        }
    ], gaps
    assert all(("@logStream" not in kw["queryString"] for kw in client.started.values()))


def test_window_never_extends_past_now():
    anchor = target.datetime.now(target.timezone.utc) - target.timedelta(minutes=5)
    client = _fake_insights(lambda kind, _: [])
    body = _call(
        {"log_group_name": f"/aiops/{IID}/sso", "time_string": anchor.strftime(target.TIME_FMT)}, client
    )
    assert (
        max((kw["endTime"] for kw in client.started.values()))
        <= int(target.datetime.now(target.timezone.utc).timestamp()) + 1
    )
    assert body["status"] == "no_matching_lines"
    assert all(
        ("note" in g for g in body["activity_all_lines"]["silent_gaps"] if g["to"] >= body["window_end"][:16])
    )


def test_response_stays_under_bedrock_limit():
    big = "x" * 5000
    client = _fake_insights(
        lambda kind, _: (
            []
            if kind == "activity"
            else [_row(**{"@timestamp": "2026-01-01 00:00:00", "@message": big})] * 50
        )
    )
    anchor = (target.datetime.now(target.timezone.utc) - target.timedelta(hours=3)).strftime(target.TIME_FMT)
    event = {
        "parameters": [
            {"name": "log_group_name", "value": f"/aiops/{IID}/sso"},
            {"name": "time_string", "value": anchor},
            {"name": "lines", "value": "50"},
        ]
    }
    with patch("boto3.client", return_value=client):
        raw = target.lambda_handler(event, None)["response"]["responseBody"]["application/json"]["body"]
    assert len(raw.encode()) <= target.MAX_BODY_BYTES
    assert json.loads(raw)["truncated"]


def test_bad_inputs_return_errors_not_crashes():
    client = MagicMock()
    for params in (
        {"log_group_name": f"/aiops/{IID}/sso", "hours_back": "two"},
        {"log_group_name": f"/aiops/{IID}/sso", "time_string": "yesterday"},
        {"log_group_name": f"/aiops/{IID}/sso", "time_string": "2999-01-01 00:00:00"},
        {},
    ):
        assert _call(params, client)["status"] == "error", params


def test_query_timeout_stops_queries():
    client = MagicMock()
    client.start_query.return_value = {"queryId": "q"}
    client.get_query_results.return_value = {"status": "Running", "results": []}
    with patch("time.sleep"):
        try:
            target.run_queries(
                client,
                "/aiops/x/y",
                {
                    "a": (
                        "q",
                        target.datetime.now(target.timezone.utc),
                        target.datetime.now(target.timezone.utc),
                    )
                },
                deadline=target.time.monotonic() - 1,
            )
            raise AssertionError("no timeout")
        except target.QueryFailed:
            pass
    client.start_query.assert_not_called()
    client.get_query_results.assert_not_called()
