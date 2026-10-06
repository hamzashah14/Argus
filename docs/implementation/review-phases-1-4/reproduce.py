"""Offline diagnostic reproductions of OPEN review findings, not acceptance tests.

Every cloud boundary is injected; no AWS client or network connection is created.
Exit zero means the documented defects were reproduced, not that they are fixed.
Run from the repository with .venv/bin/python <this-file> --output <json-file>.
"""

import argparse
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from botocore.response import StreamingBody  # noqa: E402

from infra import durable_ops, release  # noqa: E402
from infra.spec import alarm_descriptors, load  # noqa: E402
from infra.verify import VerificationError, coverage  # noqa: E402
from kira import agentcore, observability, pipeline  # noqa: E402
from kira.observation_config import validate  # noqa: E402
from scripts.validate_durable import examples  # noqa: E402
from scripts.validate_observations import fixtures  # noqa: E402

SPEC = load(ROOT / "infra/observability.example.json")
CONFIG = json.loads((ROOT / "infra/durable.example.json").read_text())


class Clock:
    def __init__(self):
        self.now = 0

    def read(self):
        return self.now

    def advance(self, amount):
        self.now += amount


def role_drift():
    spec = {**SPEC, "reference_only": False}  # Only injected clients below.
    stages, bindings, artifacts, versions = examples(spec, CONFIG, include_bindings=True)
    planned = stages["durable-runtime"]
    sts, cfn, client = MagicMock(), MagicMock(), MagicMock()
    sts.get_caller_identity.return_value = {"Account": spec["account_id"]}
    cfn.get_stack_policy.return_value = {"StackPolicyBody": json.dumps(release.SEALED_POLICY)}
    bad_role = f"arn:aws:iam::{spec['account_id']}:role/unreviewed-role"
    by_arn = {}
    for function, artifact in artifacts.items():
        logical = function.removeprefix("incident_").title()
        properties = planned["Resources"][logical]["Properties"]
        by_arn[versions[logical + "VersionArn"]] = {
            "CodeSha256": base64.b64encode(bytes.fromhex(artifact["sha256"])).decode(),
            "Runtime": "python3.12",
            "State": "Active",
            "Environment": properties["Environment"],
            "Role": bad_role,
            **{key: properties[key] for key in ("Timeout", "MemorySize", "Architectures")},
        }
    client.get_function.side_effect = lambda FunctionName: {"Configuration": by_arn[FunctionName]}
    client.get_function_configuration.side_effect = lambda FunctionName: by_arn[FunctionName]

    def concurrency(FunctionName):
        logical = next(
            k.removesuffix("VersionArn") for k, v in versions.items() if v.rsplit(":", 1)[0] == FunctionName
        )
        reserved = planned["Resources"][logical]["Properties"].get("ReservedConcurrentExecutions")
        return {} if reserved is None else {"ReservedConcurrentExecutions": reserved}

    client.get_function_concurrency.side_effect = concurrency
    factory = MagicMock(side_effect=lambda service, region: {"sts": sts, "lambda": client}[service])
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, "durable-runtime.json").write_text(json.dumps(planned))
        bundle = {
            "spec": spec,
            "bindings": {**bindings, "artifacts": artifacts, "versions": versions},
            "directory": directory,
        }
        with (
            patch.object(
                durable_ops,
                "owned_stack",
                return_value=(cfn, {"StackStatus": "CREATE_COMPLETE", "EnableTerminationProtection": True}),
            ),
            patch.object(durable_ops, "collect", return_value=versions),
        ):
            result = durable_ops.verify_runtime(bundle, factory=factory)
    assert result["status"] == "PASS" and not any(call.args[0] == "iam" for call in factory.call_args_list)
    return {"finding": "R01", "observed": "PASS with all six function roles unreviewed; zero IAM checks"}


def sweep_starvation():
    store, clock = MagicMock(), Clock()
    store.expired.return_value = ([{"PK": f"INCIDENT#synthetic{i}"} for i in range(5)], None)
    store.get.return_value = {"PK": "INCIDENT#synthetic"}

    def failing_recovery(*args):
        clock.advance(12)  # Simulated aggregate read/write latency within SDK budgets.
        raise RuntimeError("Synthetic per-row recovery failure")

    store.recover.side_effect = failing_recovery
    attempts = 0
    with (
        patch.object(pipeline, "ledger", return_value=store),
        patch.object(pipeline, "clients", return_value=MagicMock()),
        patch.object(pipeline.time, "monotonic", side_effect=clock.read),
    ):
        for _ in range(3):
            clock.now = 0
            try:
                pipeline.reconcile()
            except RuntimeError:
                attempts += 1
    assert attempts == 3 and store.overdue.call_count == store.pending.call_count == 0
    return {
        "finding": "R02",
        "sweeps": attempts,
        "overdue_queries": 0,
        "pending_queries": 0,
        "recovery_calls": store.recover.call_count,
        "observed": "Earlier scan consumes budget on every sweep; later indexes never queried",
    }


def bootstrap():
    errors = []
    for enabled in (False, True):
        spec = copy.deepcopy(SPEC)
        spec["reference_only"] = False  # Injected fake clients only.
        spec["observability"]["enabled"] = enabled
        descriptors = alarm_descriptors(spec)
        clients = {key: MagicMock() for key in ("sts", "lambda", "ec2", "cloudwatch")}
        clients["sts"].get_caller_identity.return_value = {"Account": spec["account_id"]}
        clients["ec2"].describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": i["id"], "State": {"Name": "running"}} for i in spec["instances"]
                    ]
                }
            ]
        }

        def metrics(**request):
            return {
                "Metrics": [
                    {"Dimensions": [{"Name": key, "Value": value} for key, value in d["dimensions"].items()]}
                    for d in descriptors
                    if d["namespace"] == request["Namespace"]
                    and d["metric_name"] == request["MetricName"]
                    and not d["namespace"].endswith("/Health")
                ]
            }

        clients["cloudwatch"].list_metrics.side_effect = metrics
        try:
            coverage(spec, lambda service, region: clients[service])
        except VerificationError as exc:
            errors.append({"enabled": enabled, "error": str(exc)})
    with (
        patch.object(observability, "settings", return_value=SPEC["observability"]),
        patch.object(
            observability, "clients", side_effect=AssertionError("disabled observer must not create a client")
        ),
    ):
        disabled = observability.observer()
    assert (
        len(errors) == 2
        and all("api-ready" in e["error"] for e in errors)
        and disabled == {"status": "DISABLED"}
    )
    return {
        "finding": "R03",
        "coverage_errors": errors,
        "disabled_observer": disabled,
        "observed": "Promotion requires observer health metrics even before activation and when paused",
    }


def stream_bounds():
    clock = Clock()

    class Trickle(io.BytesIO):
        reads = 0

        def read(self, amount=-1):
            self.reads += 1
            clock.advance(1)  # Simulated time only; no sleeps.
            return super().read(amount)

    raw = Trickle(b"x" * (agentcore.MAX_WIRE_BYTES + 1))
    stream, client = StreamingBody(raw, agentcore.MAX_WIRE_BYTES + 1), MagicMock()
    client.invoke_agent_runtime.return_value = {
        "response": stream,
        "statusCode": 200,
        "contentType": "text/event-stream",
    }
    error = None
    with patch.object(agentcore.time, "time", side_effect=clock.read):
        try:
            agentcore.invoke(
                {"release": "synthetic"},
                arn=f"arn:aws:bedrock-agentcore:{SPEC['bedrock_region']}:{SPEC['account_id']}:runtime/reference-1234567890",
                qualifier="release_reference",
                region=SPEC["bedrock_region"],
                account=SPEC["account_id"],
                session_id="incident_" + "x" * 40,
                deadline=30,
                client=client,
            )
        except RuntimeError as exc:
            error = str(exc)
    assert clock.now > 30 and raw.reads > agentcore.MAX_WIRE_BYTES and raw.closed
    return {
        "finding": "R04",
        "deadline_seconds": 30,
        "simulated_seconds_before_detection": clock.now,
        "stream_read_calls": raw.reads,
        "error": error,
        "observed": "Botocore buffers a whole unterminated line before adapter checks time/size",
    }


def observer_budget():
    config, clock, cw = copy.deepcopy(SPEC["observability"]), Clock(), MagicMock()
    config["enabled"] = True
    config["services"] = [
        {
            **copy.deepcopy(config["services"][0]),
            "id": f"svc{i}",
            "routes": [{**config["services"][0]["routes"][0], "timeout_seconds": 5}],
        }
        for i in range(3)
    ]
    validate(config, SPEC["instances"])

    def probe(route):
        clock.advance(5)
        return {"healthy": False}

    def freshness(*args):
        clock.advance(16)  # Two calls using the current 8-second SDK read budget.
        return False

    context = MagicMock()
    context.get_remaining_time_in_millis.return_value = 60000
    with (
        patch.object(observability, "settings", return_value=config),
        patch.object(observability, "clients", return_value=cw),
        patch.object(observability, "store", return_value=MagicMock()),
        patch.object(observability.probes, "bounded_check", side_effect=probe),
        patch.object(observability, "check_freshness", side_effect=freshness),
        patch.object(observability.time, "monotonic", side_effect=clock.read),
        patch.dict(os.environ, {"MAINTENANCE_MODE": "false"}),
    ):
        try:
            observability.observer(context=context)
        except RuntimeError as exc:
            error = str(exc)
    assert cw.put_metric_data.call_count == 0 and clock.now == 26
    return {
        "finding": "R05",
        "valid_services": 3,
        "simulated_seconds": clock.now,
        "health_publications": 0,
        "error": error,
        "observed": "Accepted inventory aborts before publishing even the already collected health results",
    }


def remote_visibility():
    spec = {**SPEC, "bedrock_region": "us-east-1"}
    stages = fixtures(spec, {**CONFIG, "runtime_target": "agentcore"})
    dashboard = json.loads(stages["observations"]["Resources"]["Dashboard"]["Properties"]["DashboardBody"])
    widgets = dashboard["widgets"]
    model_region = next(w["properties"]["region"] for w in widgets if w["properties"]["title"] == "model")
    host_log_sources = [w for w in widgets if "bedrock-agentcore/runtimes" in json.dumps(w)]
    retained_host_logs = [
        r for r in stages["agentcore-runtime"]["Resources"].values() if r["Type"] == "AWS::Logs::LogGroup"
    ]
    assert model_region != spec["bedrock_region"] and not host_log_sources and not retained_host_logs
    return {
        "finding": "R06",
        "host_region": spec["bedrock_region"],
        "model_widget_region": model_region,
        "host_log_widgets": 0,
        "host_log_retention_resources": 0,
        "observed": "Remote model telemetry is not wired to its region/log group; host retention is not managed",
    }


def exhausted_notification():
    store, sns = MagicMock(), MagicMock()
    store.get.return_value = {"status": "SENDING", "attempts": 3, "lease_until": 0}
    iid = hashlib.sha256(b"reference notification").hexdigest()[:32]
    message = {
        "Records": [
            {
                "messageId": "synthetic",
                "body": f"INCIDENT#{iid}|INTENT#INITIAL#1",
            }
        ]
    }
    env = {"REPORTS_TOPIC_ARN": "synthetic-topic", "STATUS_BASE_URL": "https://status.example.invalid"}
    with (
        patch.object(pipeline, "ledger", return_value=store),
        patch.object(pipeline, "clients", return_value=sns),
        patch.dict(os.environ, env),
    ):
        result = pipeline.notify(message, None, "INITIAL")
    assert (
        result == {"batchItemFailures": [{"itemIdentifier": "synthetic"}]}
        and store.get.call_count == 1
        and store.notification_result.call_count == store.claim_notification.call_count == 0
    )
    return {
        "finding": "R07",
        "result": result,
        "terminal_or_recovery_writes": 0,
        "observed": "Expired third SENDING lease is never finalized or made replayable by the notifier",
    }


def duplicate_receipt():
    config, ledger = SPEC["observability"], MagicMock()
    now, iid = (
        2 * config["canary_interval_minutes"] * 60 + config["receipt_deadline_seconds"] + 1,
        hashlib.sha256(b"reference incident").hexdigest()[:32],
    )
    slot = observability.slot_at(now, config)
    row = {
        "incident_id": iid,
        "due_epoch": now - 1,
        "recipient_received_at": now - 2,
        "recipient_message_id": "first-publication",
        "recipient_fingerprint": observability.recipient_fingerprint(
            "synthetic-topic", "operator@example.invalid"
        ),
        "email_received_at": now - 2,
    }

    def get(pk, sk="META"):
        if pk == f"CANARY#{slot}":
            return row
        if pk == "INCIDENT#" + iid:
            return (
                {"status": "PUBLISHER_ACCEPTED", "publisher_message_id": "second-publication"}
                if sk == "NOTIFICATION#INITIAL"
                else {"canary_slot": slot}
            )
        return None

    ledger.get.side_effect = get
    with patch.dict(
        os.environ, {"REPORTS_TOPIC_ARN": "synthetic-topic", "PRIMARY_EMAIL": "operator@example.invalid"}
    ):
        problem, received, age = observability.verify_canary(ledger, config, now)
    assert problem == ["CANARY_RECEIPT_MISSED"] and not received
    return {
        "finding": "R08",
        "failures": problem,
        "instrumented_delivery": received,
        "observed": "First receipt and accepted retry have different SNS message IDs; valid delivery stays classified as missed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    # Never print handler telemetry or raw envelopes in the public evidence.
    denied = AssertionError("Review diagnostic must never construct an AWS client or open a socket")
    with (
        contextlib.redirect_stdout(io.StringIO()),
        patch("boto3.client", side_effect=denied),
        patch("boto3.resource", side_effect=denied),
        patch("socket.socket.connect", side_effect=denied),
        patch("socket.create_connection", side_effect=denied),
    ):
        findings = [
            fn()
            for fn in (
                role_drift,
                sweep_starvation,
                bootstrap,
                stream_bounds,
                observer_budget,
                remote_visibility,
                exhausted_notification,
                duplicate_receipt,
            )
        ]
    result = {
        "kind": "known_defect_reproduction",
        "network_calls": 0,
        "aws_client_constructions": 0,
        "findings": findings,
        "interpretation": "All eight OPEN defects reproduced; this is not a production or remediation PASS",
    }
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
