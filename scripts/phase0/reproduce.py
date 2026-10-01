"""Capture known baseline defects with synthetic data and mocked AWS clients.

This deliberately separate diagnostic is not a permanently failing CI suite.
NO_LONGER_REPRODUCED means review the evidence and add the corrected regression
to Phase 1/3 tests; it does not automatically close a finding.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "lambda" / name / "lambda_function.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases(fixture):
    logs, metrics, trigger = (load(name) for name in ("fetch_logs", "fetch_metrics", "trigger_investigation"))
    iid = fixture["instance_id"]
    trigger.AGENT_ID, trigger.AGENT_ALIAS_ID = "synthetic-agent", "synthetic-alias"
    trigger.REPORTS_TOPIC_ARN = "arn:aws:sns:us-east-1:000000000000:synthetic-reports"
    rows = []

    def record(case_id, finding, reproduced, observed, expected):
        rows.append({"case": case_id, "finding": finding, "status": "REPRODUCED" if reproduced else "NO_LONGER_REPRODUCED",
                     "observed": observed, "expected_corrected_behavior": expected})

    record_event = {"Sns": {"MessageId": fixture["sns_message_id"], "Message": json.dumps(fixture["alarm"])}}
    with patch.object(trigger, "investigate", return_value=("Synthetic report", True)) as agent, \
            patch.object(trigger, "publish_report") as publish:
        trigger.lambda_handler({"Records": [record_event, record_event]}, None)
        record("R01", "F03", agent.call_count == 2 and publish.call_count == 2,
               {"investigations": agent.call_count, "publications": publish.call_count},
               "Duplicate event claims produce one logical investigation and notification intent; ambiguous delivery remains reconcilable.")

    remaining = [fixture["stream_start_remaining_seconds"]]

    def blocked_stream():
        remaining[0] -= fixture["stream_block_seconds"]
        yield {"chunk": {"bytes": b"Synthetic late partial answer"}}

    client = MagicMock()
    client.invoke_agent.return_value = {"completion": blocked_stream()}
    publication_remaining = []
    with patch.object(trigger.boto3, "client", return_value=client), \
            patch.object(trigger, "publish_report", side_effect=lambda *args: publication_remaining.append(remaining[0])):
        trigger.handle_record(fixture["alarm"], lambda: remaining[0])
    record("R02", "F01", bool(publication_remaining and publication_remaining[0] < 0),
           {"publication_remaining_seconds": publication_remaining, "simulation": "fake clock advances while stream blocks; no real sleep"},
           "Initial alert independent of model; deadline stops or external reconciliation produces degraded status before the overall deadline.")

    sns = MagicMock()
    with patch.object(trigger.boto3, "client", return_value=sns):
        trigger.publish_report(iid, "2026-09-24 10:15:32", "Synthetic alert", fixture["unicode_character"] * fixture["unicode_repeat"])
    message = sns.publish.call_args.kwargs["Message"]
    record("R03", "F13", len(message.encode("utf-8")) > 262144,
           {"characters": len(message), "utf8_bytes": len(message.encode("utf-8")), "transport_limit_bytes": 262144},
           "Complete UTF-8 message with metadata and truncation marker stays within the configured byte budget; subject is valid.")

    expected = datetime.fromisoformat(fixture["time_expected_utc"])
    anchor = logs.parse_time(fixture["time_input"])
    start, end = metrics.resolve_window({"time_string": fixture["time_input"], "window_minutes": 30}, datetime.fromisoformat(fixture["now"]))
    center = start + (end - start) / 2
    record("R04", "F14", anchor != expected and center != expected,
           {"logs_anchor": anchor.isoformat(), "metrics_anchor": center.isoformat(), "correct_anchor": expected.isoformat()},
           "Equivalent offset timestamps normalize to identical UTC windows.")
    malformed = trigger._format_alarm_time(fixture["malformed_time"])
    record("R05", "F14", malformed != fixture["malformed_time"],
           {"raw": fixture["malformed_time"], "substitutes_processing_time": bool(malformed)},
           "Malformed source time preserves the raw input and produces explicit uncertainty/degraded status, never silent now substitution.")

    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}
    with patch.object(metrics.boto3, "client", return_value=cloudwatch):
        metrics.fetch({"instance_id": iid, "namespace": "AIOpsNginx", "metric_name": fixture["alarm"]["Trigger"]["MetricName"], "statistic": "Sum"})
    dimensions = cloudwatch.get_metric_statistics.call_args.kwargs["Dimensions"]
    record("R06", "F12", dimensions != [], {"alarm_dimensions": [], "requested_dimensions": dimensions},
           "Allowlisted dimensionless Nginx metric uses exactly []; configured instance/path/process/volume metrics preserve exact dimensions.")

    prefix = f"/aiops/{iid}/"
    names = [(prefix + f"service-{i:04d}-").ljust(fixture["discovery_name_length"], "x") for i in range(fixture["discovery_group_count"])]
    pages = [{"logGroups": [{"logGroupName": name} for name in names[offset:offset + 50]],
              **({"nextToken": f"synthetic-page-{offset + 50}"} if offset + 50 < len(names) else {})}
             for offset in range(0, len(names), 50)]
    cloudlogs = MagicMock()
    cloudlogs.describe_log_groups.side_effect = pages
    discovery = logs.discover_log_groups(cloudlogs, iid)
    body = logs.fit_to_budget(discovery)
    envelope_bytes = len(json.dumps(logs._envelope({}, body), separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    record("R07", "F15", len(discovery["log_groups"]) < len(names) and not discovery.get("next_token"),
           {"available": len(names), "returned": len(discovery["log_groups"]), "pages_read": cloudlogs.describe_log_groups.call_count, "keys": sorted(discovery)},
           "Caller can traverse all 300 groups through bounded pages with scope-bound continuation and completeness markers.")
    record("R08", "F15", envelope_bytes > logs.MAX_BODY_BYTES,
           {"body_bytes": len(body.encode("utf-8")), "envelope_bytes": envelope_bytes, "configured_budget_bytes": logs.MAX_BODY_BYTES},
           "Budget applies to the full serialized UTF-8 envelope, including discovery, metadata and error results.")

    # Copy only the config reader into a disposable fixture tree. Never execute
    # any deploy script or source the user's private config.
    with tempfile.TemporaryDirectory(prefix="kira-phase0-") as temp:
        temp_root = Path(temp)
        (temp_root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/common.sh", temp_root / "scripts/common.sh")
        (temp_root / "config.env").write_text("".join(f"{key}={value}\n" for key, value in fixture["minimal_config"].items()))
        probe = temp_root / "probe.py"
        probe.write_text('import json,os\nprint(json.dumps({"child_agent_name":os.environ.get("AGENT_NAME")}))\n')
        command = 'source "$1"; "$2" "$3"'
        run = subprocess.run(["bash", "-c", command, "phase0", str(temp_root / "scripts/common.sh"), sys.executable, str(probe)],
                             env={"PATH": os.defpath}, capture_output=True, text=True, check=True)
        observed = json.loads(run.stdout)
    record("R09", "F16", observed["child_agent_name"] is None, observed,
           "Required-only configuration exports the validated default AGENT_NAME to the Python child before any cloud mutation.")

    schema = json.loads((ROOT / "schemas/fetch_metrics.json").read_text())
    missing = []

    def visit(value, path="$"):
        if isinstance(value, dict):
            if value.get("type") == "array" and "items" not in value:
                missing.append(path)
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                visit(child, f"{path}[{i}]")

    visit(schema)
    record("R10", "F20", bool(missing), {"array_schemas_without_items": missing, "validation_scope": "targeted invariant, not full OpenAPI validation"},
           "All array schemas specify items; full OpenAPI and actual response contract validation pass.")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture_path = ROOT / "docs/implementation/phase-0/fixtures.json"
    fixture = json.loads(fixture_path.read_text())
    with patch.dict(os.environ, {"AWS_EC2_METADATA_DISABLED": "true"}, clear=True), \
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in reproductions")), \
            patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden in reproductions")):
        rows = cases(fixture)
    sources = ["scripts/phase0/reproduce.py", "scripts/common.sh", "schemas/fetch_metrics.json",
               "docs/implementation/phase-0/fixtures.json"] + [
                   f"lambda/{name}/lambda_function.py" for name in
                   ("fetch_logs", "fetch_metrics", "trigger_investigation")]
    result = {"mode": "baseline-defect-observation", "synthetic": True, "cloud_calls": 0, "cases": rows,
              "command": ".venv/bin/python scripts/phase0/reproduce.py --output docs/implementation/evidence/phase-0/regressions.json",
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(f"{row['case']} {row['finding']}: {row['status']}")


if __name__ == "__main__":
    main()
