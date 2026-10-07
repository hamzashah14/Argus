"""security hostile inputs, concurrency, erasure and private operations; no AWS."""

import copy
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from infra import chat as chat_infra
from infra import durable_templates, owned_runtime, security_ops
from infra.verify import VerificationError
from kira import chat_gateway, diagnosis, execution, identity, runtime, safety, work_policy
from kira.quotas import Quotas
from scripts import evaluate_diagnostics
from tests.test_identity import ACTOR, IID, RELEASE
from tests.test_identity import setup as identity_fixture
from tests.test_identity_wiring import CONFIG, SPEC, bindings
from tests.test_runtime import answer, drive


@pytest.fixture
def setup(monkeypatch, tmp_path):
    return identity_fixture.__wrapped__(monkeypatch, tmp_path)


@pytest.mark.parametrize(
    "raw,forbidden",
    [
        ("password=fixture-sensitive-marker", "fixture-sensitive-marker"),
        ('{"password":"fixture-sensitive-marker"}', "fixture-sensitive-marker"),
        ("Bearer fixture-auth-marker", "fixture-auth-marker"),
        ("https://user:fixture-password@service.invalid/path", "fixture-password"),
        ("password%253Dfixture-sensitive-marker", "fixture-sensitive-marker"),
        ("person@example.invalid 203.0.113.7", "person@example.invalid"),
        ("-----BEGIN PRIVATE KEY-----\nfixture-key\n-----END PRIVATE KEY-----", "fixture-key"),
    ],
)
def test_redaction_is_idempotent_and_removes_synthetic_sensitive_values(raw, forbidden):
    cleaned = safety.text(raw)
    assert forbidden not in cleaned and safety.text(cleaned) == cleaned


def test_nested_json_remains_valid_and_pagination_token_survives():
    raw = {
        "authorization": "fixture-sensitive-marker",
        "next_token": "opaque-cursor",
        "lines": ['{"api_key":"fixture-secret"}'],
    }
    cleaned = safety.bounded(raw)
    assert cleaned["next_token"] == "opaque-cursor"
    assert json.loads(cleaned["lines"][0])["api_key"] == "[redacted]"
    assert "fixture-secret" not in json.dumps(cleaned)


def test_boundaries_reject_excessive_depth_size_and_nonfinite_numbers():
    with pytest.raises(ValueError):
        safety.bounded({"value": "x" * 128001})
    with pytest.raises(ValueError):
        safety.bounded({"value": float("nan")})
    value = {}
    for _ in range(22):
        value = {"nested": value}
    with pytest.raises(ValueError):
        safety.bounded(value)


class AtomicDatabase:
    """Independent transactional store fake: all conditions before any mutation."""

    def __init__(self):
        self.name = "synthetic"
        self.rows, self.lock = {}, threading.Lock()

    @staticmethod
    def unpack(value):
        return {k: TypeDeserializer().deserialize(v) for k, v in value.items()}

    def transact_write_items(self, TransactItems, **kwargs):
        with self.lock:
            updates = []
            for write in TransactItems:
                if "Update" in write:
                    op = write["Update"]
                    key = self.unpack(op["Key"])["PK"]
                    values = self.unpack(op["ExpressionAttributeValues"])
                    row = self.rows.get(key, {"requests": 0, "tokens": 0})
                    allowed = row["requests"] <= values[":cap"] and row["tokens"] <= values.get(
                        ":token_cap", float("inf")
                    )
                    updates.append(
                        (
                            key,
                            {
                                **row,
                                "requests": row["requests"] + 1,
                                "tokens": row["tokens"] + values.get(":tokens", 0),
                            },
                        )
                    )
                else:
                    op = write["Put"]
                    row = self.unpack(op["Item"])
                    key = row["PK"]
                    previous = self.rows.get(key)
                    allowed = (
                        previous is None
                        or previous["until"] <= self.unpack(op["ExpressionAttributeValues"])[":now"]
                    )
                    updates.append((key, row))
                if not allowed:
                    raise ClientError(
                        {
                            "Error": {"Code": "TransactionCanceledException"},
                            "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
                        },
                        "TransactWriteItems",
                    )
            self.rows.update(updates)

    def delete_item(self, Key, **kwargs):
        with self.lock:
            previous = self.rows.get(Key["PK"])
            if not previous or previous["owner"] != kwargs["ExpressionAttributeValues"][":owner"]:
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "DeleteItem")
            self.rows.pop(Key["PK"])


@pytest.fixture
def quotas(monkeypatch):
    monkeypatch.setenv("KIRA_WORK_POLICY", json.dumps(work_policy.DEFAULT))
    db = AtomicDatabase()
    now = [7200]
    return Quotas(db, clock=lambda: now[0], client=db), db, now


def actor(n):
    return hashlib.sha256(str(n).encode()).hexdigest()


def test_concurrent_users_cannot_overcharge_shared_budget(quotas):
    q, db, _ = quotas

    def admit(n):
        try:
            lease = q.admit(actor(n % 5), "chat")
            q.release(lease)
            return True
        except runtime.RuntimeStop:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        successes = sum(pool.map(admit, range(100)))
    shared = db.rows["QUOTA#chat#global#2"]
    assert 1 <= successes <= 8 and shared["requests"] == successes
    assert (
        shared["tokens"]
        == successes * work_policy.DEFAULT["chat_limits"]["tokens_reserved"]
        <= work_policy.DEFAULT["tokens_global"]
    )
    assert all(
        v["requests"] <= 4 for k, v in db.rows.items() if k.startswith("QUOTA#chat#") and "global" not in k
    )


def test_capacity_lease_no_refund_and_foreign_release_cannot_unlock(quotas):
    q, db, _ = quotas
    first, second = q.admit(actor(1), "chat"), q.admit(actor(2), "chat")
    with pytest.raises(runtime.RuntimeStop):
        q.admit(actor(1), "chat")
    with pytest.raises(runtime.RuntimeStop):
        q.admit(actor(3), "chat")
    q.release({**first, "owner": "foreign"})
    assert "SLOT#" + actor(1) in db.rows
    q.release(first)
    third = q.admit(actor(3), "chat")
    assert db.rows["QUOTA#chat#global#2"]["requests"] == 3
    q.release(second)
    q.release(third)


def test_abandoned_slot_expiry_does_not_refund_prior_hour_charges(quotas):
    q, db, now = quotas
    q.admit(actor(1), "chat")
    now[0] += 241
    q.admit(actor(1), "chat")
    assert db.rows["QUOTA#chat#global#2"]["requests"] == 2


def test_login_budgets_are_distributed_and_no_chat_slot_is_used(quotas):
    q, db, _ = quotas
    for _ in range(10):
        q.admit(actor(1), "login")
    with pytest.raises(runtime.RuntimeStop):
        q.admit(actor(1), "login")
    assert db.rows["QUOTA#login#global#2"]["requests"] == 10
    assert not any(k.startswith("SLOT#") for k in db.rows)


@pytest.mark.parametrize(
    "code,reasons",
    [
        ("ProvisionedThroughputExceededException", []),
        ("TransactionCanceledException", []),
        ("TransactionCanceledException", [{"Code": "TransactionConflict"}]),
        ("TransactionCanceledException", [{"Code": "None"}]),
    ],
)
def test_ambiguous_admission_is_not_retried(code, reasons, monkeypatch):
    monkeypatch.setenv("KIRA_WORK_POLICY", json.dumps(work_policy.DEFAULT))
    client = Mock()
    client.transact_write_items.side_effect = ClientError(
        {"Error": {"Code": code}, "CancellationReasons": reasons}, "TransactWriteItems"
    )
    with pytest.raises(runtime.RuntimeStop, match="ADMISSION_UNAVAILABLE"):
        Quotas(SimpleNamespace(name="synthetic"), client=client).admit(actor(1), "chat")
    assert client.transact_write_items.call_count == 1


@pytest.mark.parametrize(
    "key,value", [("chat_user", 0), ("tokens_global", True), ("audit_days", 91), ("chat_global", 1)]
)
def test_work_policy_invalid_allowances_fail_closed(key, value):
    with pytest.raises(ValueError):
        work_policy.validate({**work_policy.DEFAULT, key: value})


def test_access_audit_is_retained_scoped_and_contains_no_claims(setup, capsys):
    ticket = setup.sessions.issue(setup.claims)
    setup.sessions.authorize(ticket, "report", IID)
    rows = [v for k, v in setup.table.rows.items() if k.startswith("AUDIT#")]
    assert rows and rows[-1]["actor"] == ACTOR and rows[-1]["instance_id"] == IID
    assert rows[-1]["ttl"] == setup.now[0] + 30 * 86400
    rendered = json.dumps(rows) + capsys.readouterr().out
    assert (
        ticket not in rendered
        and setup.claims["email"] not in rendered
        and setup.claims["sub"] not in rendered
    )


def test_audit_outage_blocks_login_and_report_access(setup, monkeypatch):
    ticket = setup.sessions.issue(setup.claims)
    monkeypatch.setattr(setup.sessions, "record", Mock(side_effect=RuntimeError("synthetic")))
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "report", IID)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.issue(setup.claims)


def test_key_rotation_and_grant_epoch_disable_old_sessions(setup, monkeypatch):
    ticket = setup.sessions.issue(setup.claims)
    monkeypatch.setenv("KIRA_SESSION_SIGNING_KEY", "rotated-fixture-" * 8)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")
    new = setup.sessions.issue(setup.claims)
    setup.table.rows["IDENTITY#" + ACTOR]["epoch"] += 1
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(new, "chat")


@pytest.mark.parametrize("target", ["standalone", "agentcore"])
def test_chat_ui_and_automatic_capacity_and_iam_are_independent(target):
    cfg = {**CONFIG, "runtime_target": target}
    data = bindings(target=target)
    artifact = {"bucket": "synthetic", "key": "fixture.zip", "version_id": "synthetic", "sha256": "a" * 64}
    t = chat_infra.runtime(SPEC, cfg, data, artifact)
    assert t["Resources"]["Chat"]["Properties"]["ReservedConcurrentExecutions"] == 1
    assert t["Resources"]["Chat"]["Properties"]["Environment"]["Variables"]["EXECUTION_PURPOSE"] == "chat"
    routing = durable_templates.active_routing(
        SPEC,
        data["foundation"],
        data["versions"],
        config=cfg,
        owned_bindings=data,
    )
    grants = routing["Resources"]["UiRole"]["Properties"]["Policies"][0]["PolicyDocument"]
    assert "bedrock:InvokeModel" not in json.dumps(
        grants
    ) and "bedrock-agentcore:InvokeAgentRuntime" not in json.dumps(grants)
    assert chat_infra.version(SPEC, data) in json.dumps(grants)
    if target == "agentcore":
        remote = owned_runtime.agentcore_release(SPEC, cfg, data, artifact, purpose="chat")
        env = remote["Resources"]["Runtime"]["Properties"]["EnvironmentVariables"]
        assert env["EXECUTION_PURPOSE"] == "chat" and "INCIDENT_TABLE" not in env
        assert data["agentcore_chat"]["RuntimeArn"] != data["agentcore"]["RuntimeArn"]
        assert data["foundation"]["TableArn"] not in json.dumps(remote)
    assert not owned_runtime.identity_permissions(SPEC, cfg, data)


def test_wrong_execution_purpose_cannot_reach_model_or_store(setup, monkeypatch):
    monkeypatch.setenv("EXECUTION_PURPOSE", "incident")
    monkeypatch.setattr(execution, "run", Mock())
    with pytest.raises(runtime.RuntimeStop, match="PURPOSE_MISMATCH"):
        execution.execute({"version": 1, "release": RELEASE, "mode": "chat"})
    execution.run.assert_not_called()


def test_gateway_closes_stream_and_requires_exact_release_without_retry():
    payload = {"release": RELEASE}
    result = {
        "version": 1,
        "release": RELEASE,
        "complete": False,
        "text": "Operator review",
        "code": "ADMISSION_UNAVAILABLE",
        "tools": [],
        "evidence": [],
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    stream = BytesIO(json.dumps(result).encode())
    client = Mock()
    client.invoke.return_value = {"StatusCode": 200, "Payload": stream}
    got = chat_gateway.invoke(
        payload,
        arn="arn:aws:lambda:eu-central-1:123456789012:function:chat:1",
        region="eu-central-1",
        account="123456789012",
        deadline=time.time() + 30,
        client=client,
    )
    assert got["code"] == "ADMISSION_UNAVAILABLE" and stream.closed and client.invoke.call_count == 1


@pytest.mark.parametrize("case", evaluate_diagnostics.suite()[0]["cases"], ids=lambda c: c["id"])
def test_versioned_diagnosis_reference_controls(case):
    catalog = [{**e, "result": safety.bounded(e["result"])} for e in case["catalog"]]
    got = diagnosis.validate(safety.text(json.dumps(case["candidate"])), catalog)
    assert got["status"] == case["expected"]


def test_hang_rejects_metrics_outside_gap_and_different_service():
    case = next(c for c in evaluate_diagnostics.suite()[0]["cases"] if c["id"] == "correlated-hang")
    for change in ("timestamp", "service"):
        catalog = copy.deepcopy(case["catalog"])
        metric = next(
            e
            for e in catalog
            if e["tool"] == "fetch_metrics" and e["result"]["descriptor"]["metric_name"] == "Availability"
        )
        if change == "timestamp":
            metric["result"]["datapoints"][0]["timestamp"] = "2026-10-01T10:14:00Z"
        else:
            next(d for d in metric["result"]["descriptor"]["dimensions"] if d["Name"] == "Service")[
                "Value"
            ] = "another-service"
        assert diagnosis.validate(json.dumps(case["candidate"]), catalog)["status"] == "REJECTED"


def test_model_draft_and_secret_never_enter_checkpoint_or_later_model_request(monkeypatch):
    monkeypatch.setenv("KIRA_DIAGNOSTIC_POLICY", diagnosis.VERSION)
    client, tools, saved = Mock(), Mock(), []
    client.count_tokens.return_value = {"inputTokens": 100}
    tools.invoke.return_value = (
        {
            "status": "ok",
            "complete": True,
            "instance_id": IID,
            "log_group": "/synthetic/application",
            "window_start": "2026-10-01T10:00:00Z",
            "window_end": "2026-10-01T10:15:00Z",
            "lines": ["password=fixture-sensitive-marker"],
        },
        True,
    )
    draft = "Unsupported causal draft password=fixture-sensitive-marker"
    report = {
        "version": 1,
        "findings": [{"kind": "insufficient_data", "statement": "Coverage insufficient", "evidence_ids": []}],
        "facts": [],
        "hypotheses": [],
        "limitations": ["No independent corroboration"],
        "recommendations": ["Operator review"],
    }
    client.converse.side_effect = [
        answer(
            stop="tool_use",
            blocks=[
                {"text": draft},
                {"toolUse": {"toolUseId": "one", "name": "fetch_logs", "input": {"instance_id": IID}}},
            ],
        ),
        answer(json.dumps(report)),
    ]
    result, _, _ = drive(
        client,
        tools=tools,
        checkpoint=saved.append,
        history=[{"role": "user", "content": "password=fixture-sensitive-marker"}],
    )
    assert result["complete"] and result["diagnosis"]["status"] == "VALID"
    assert saved and "Unsupported causal draft" not in "".join(saved)
    assert (
        "fixture-sensitive-marker"
        not in json.dumps(client.converse.call_args_list) + "".join(saved) + result["text"]
    )
    assert "Sources and observation windows" in result["text"]


def test_unstructured_model_final_never_becomes_a_complete_diagnosis(monkeypatch):
    monkeypatch.setenv("KIRA_DIAGNOSTIC_POLICY", diagnosis.VERSION)
    client = Mock()
    client.converse.return_value = answer("Definitely fixed; root cause guessed")
    result, _, _ = drive(client)
    assert not result["complete"] and result["code"] == "UNSUPPORTED_DIAGNOSIS"
    assert "guessed" not in result["text"]


def test_fixture_cross_scope_tool_is_denied_without_any_aws_calls():
    tool = evaluate_diagnostics.FixtureTools([])
    with pytest.raises(runtime.RuntimeStop):
        tool.invoke("fetch_logs", {"instance_id": "i-11111111111111111"}, time.time() + 30)
    with pytest.raises(runtime.RuntimeStop):
        tool.invoke("execute_command", {"instance_id": IID}, time.time() + 30)


def test_default_evaluation_records_model_not_run_and_passes():
    result = evaluate_diagnostics.offline()
    assert result["status"] == "PASS" and result["model"] is None and len(result["cases"]) == 16
    assert result["live_model_evaluation"] == "NOT_RUN"


def test_paid_evaluation_aggregate_budget_is_enforced():
    budget = evaluate_diagnostics.EvaluationBudget(20)
    budget.reserve({"tokens_reserved": 15})
    with pytest.raises(runtime.RuntimeStop):
        budget.reserve({"tokens_reserved": 6})
    assert budget.used["tokens_reserved"] == 15


@pytest.mark.parametrize(
    "command", ["access-review", "erase-plan", "erase-apply", "recipients-plan", "recipients-apply"]
)
def test_synthetic_security_cli_denies_before_aws(command, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(security_ops.durable_ops, "read_bundle", lambda *a: {"spec": SPEC, "config": CONFIG})
    monkeypatch.setattr(
        __import__("sys"),
        "argv",
        [
            "security_ops",
            command,
            "--bundle",
            str(tmp_path),
            "--review-hash",
            "synthetic",
            "--output",
            str(tmp_path / "private.json"),
        ],
    )
    assert security_ops.main() == 2 and not (tmp_path / "private.json").exists()
    assert "failed" in capsys.readouterr().err


class EraseTable:
    def __init__(self):
        self.pk = "INCIDENT#" + "b" * 32
        self.rows = {
            (self.pk, "META"): {
                "PK": self.pk,
                "SK": "META",
                "status": "COMPLETE",
                "fencing_token": 2,
                "deadline_epoch": 100,
                "lease_until": 150,
                "event_id": "c" * 64,
                "report_version": "old",
            },
            (self.pk, "EVIDENCE#old"): {"PK": self.pk, "SK": "EVIDENCE#old", "key": "private", "ttl": 99999},
            ("EVENT#" + "c" * 64, "META"): {
                "PK": "EVENT#" + "c" * 64,
                "SK": "META",
                "incident_id": "b" * 32,
                "event": {"original_event": "synthetic raw data"},
            },
        }
        self.deletes = []

    def query(self, **kwargs):
        assert kwargs["ConsistentRead"] is True
        return {"Items": copy.deepcopy([r for (pk, _), r in self.rows.items() if pk == self.pk])}

    def get_item(self, Key, **kwargs):
        return {"Item": copy.deepcopy(self.rows.get((Key["PK"], Key["SK"])))}

    def update_item(self, Key, **kwargs):
        row = self.rows[(Key["PK"], Key["SK"])]
        values = kwargs["ExpressionAttributeValues"]
        assert row["status"] == values[":before"] and row["fencing_token"] == values[":fence"]
        row.update(status="DELETING", purge_ref=values[":ref"], fencing_token=row["fencing_token"] + 1)
        row.pop("report_version", None)

    def delete_item(self, Key):
        self.deletes.append(Key)
        self.rows.pop((Key["PK"], Key["SK"]), None)

    def put_item(self, Item, **kwargs):
        previous = self.rows.get((Item["PK"], Item["SK"]))
        if Item["PK"].startswith("INCIDENT#"):
            assert (
                previous["status"] == "DELETING"
                and previous["purge_ref"] == kwargs["ExpressionAttributeValues"][":ref"]
            )
        self.rows[(Item["PK"], Item["SK"])] = copy.deepcopy(Item)


class EraseS3:
    def __init__(self):
        self.objects = [
            {"Key": f"incidents/{'b' * 32}/reports/2.txt", "VersionId": v} for v in ("current", "noncurrent")
        ]
        self.marker = {"Key": f"incidents/{'b' * 32}/reports/2.txt", "VersionId": "delete-marker"}
        self.fail = False
        self.deleted = []

    def list_object_versions(self, **kwargs):
        assert kwargs["ExpectedBucketOwner"] == SPEC["account_id"]
        assert kwargs["Prefix"] == f"incidents/{'b' * 32}/"
        return {
            "Versions": self.objects,
            "DeleteMarkers": [self.marker] if self.marker else [],
            "IsTruncated": False,
        }

    def delete_objects(self, **kwargs):
        assert kwargs["ExpectedBucketOwner"] == SPEC["account_id"]
        if self.fail:
            return {"Errors": [{"Code": "AccessDenied"}]}
        objects = kwargs["Delete"]["Objects"]
        self.deleted.extend(objects)
        self.objects = [o for o in self.objects if o not in objects]
        if self.marker in objects:
            self.marker = None
        return {}


@pytest.fixture
def eraser():
    from kira.governance import Erasure

    table, s3 = EraseTable(), EraseS3()
    return Erasure(table, s3, "synthetic", SPEC["account_id"], clock=lambda: 5000), table, s3


def test_erasure_removes_current_noncurrent_markers_and_raw_event_but_retains_tombstones(eraser):
    erase, table, s3 = eraser
    plan = erase.plan("b" * 32)
    assert "synthetic raw data" not in json.dumps(plan) and len(plan["objects"]) == 3
    result = erase.apply(plan)
    assert result["status"] == "DELETED" and result["restore_exclusion_required"]
    assert len(s3.deleted) == 3 and not s3.objects and s3.marker is None
    incident = table.rows[(table.pk, "META")]
    event = table.rows[("EVENT#" + "c" * 64, "META")]
    assert incident["status"] == "DELETED" and incident["fencing_token"] == 3
    assert event["deleted"] is True and "event" not in event
    assert all(k[1] == "META" for k in table.rows)
    assert incident["ttl"] == 5000 + 35 * 86400


def test_partial_erasure_failure_retains_tombstone_and_supports_reviewed_retry(eraser):
    erase, table, s3 = eraser
    plan = erase.plan("b" * 32)
    s3.fail = True
    with pytest.raises(ValueError):
        erase.apply(plan)
    assert table.rows[(table.pk, "META")]["status"] == "DELETING"
    assert not table.deletes and len(s3.objects) == 2
    s3.fail = False
    assert erase.apply(erase.plan("b" * 32))["status"] == "DELETED"


def test_erasure_stale_review_and_active_delivery_deny_before_deletion(eraser):
    erase, table, s3 = eraser
    plan = erase.plan("b" * 32)
    table.rows[(table.pk, "META")]["fencing_token"] += 1
    with pytest.raises(ValueError, match="changed"):
        erase.apply(plan)
    assert not s3.deleted and table.rows[(table.pk, "META")]["status"] == "COMPLETE"
    table.rows[(table.pk, "NOTIFICATION#REPORT")] = {
        "PK": table.pk,
        "SK": "NOTIFICATION#REPORT",
        "status": "SENDING",
    }
    with pytest.raises(ValueError, match="delivery"):
        erase.plan("b" * 32)


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "RETRY"])
def test_erasure_cannot_cancel_or_delete_active_investigations(eraser, status):
    erase, table, s3 = eraser
    table.rows[(table.pk, "META")]["status"] = status
    with pytest.raises(ValueError):
        erase.plan("b" * 32)
    assert not s3.deleted


def test_erasure_quiescence_grace_and_all_s3_pages(eraser):
    erase, table, _ = eraser
    table.rows[(table.pk, "META")]["deadline_epoch"] = 4999
    with pytest.raises(ValueError):
        erase.plan("b" * 32)
    s3 = Mock()
    s3.list_object_versions.side_effect = [
        {
            "Versions": [{"Key": f"incidents/{'b' * 32}/one", "VersionId": "1"}],
            "IsTruncated": True,
            "NextKeyMarker": "one",
            "NextVersionIdMarker": "1",
        },
        {"DeleteMarkers": [{"Key": f"incidents/{'b' * 32}/two", "VersionId": "2"}], "IsTruncated": False},
    ]
    erase.s3 = s3
    assert len(erase.versions("b" * 32)) == 2
    assert s3.list_object_versions.call_args.kwargs["VersionIdMarker"] == "1"


def test_notification_replay_and_status_access_refuse_erased_incident(monkeypatch):
    from kira.ledger import Ledger
    from kira.status import load

    table, client = Mock(), Mock()
    table.get_item.side_effect = lambda **kw: {"Item": {"status": "DELETED", "ttl": 4102444800}}
    with pytest.raises(ValueError):
        Ledger("synthetic", client, table).notification_replay_plan("b" * 32, "REPORT")
    client.transact_write_items.assert_not_called()
    monkeypatch.setenv("INCIDENT_TABLE", "synthetic")
    monkeypatch.setenv("MONITOR_REGION", "eu-central-1")
    monkeypatch.setattr(
        __import__("boto3"), "resource", lambda *a, **kw: SimpleNamespace(Table=lambda name: table)
    )
    assert load("b" * 32) is None


def test_access_review_paginates_only_grants_and_requires_human_attestation(monkeypatch):
    from infra.identity_ops import pack

    bundle = {"spec": {**SPEC, "reference_only": False}, "config": CONFIG, "bindings": bindings()}
    expected = [
        SPEC["environment"],
        SPEC["account_id"],
        owned_runtime.fingerprint(SPEC, CONFIG, bundle["bindings"]),
    ]
    ddb = Mock()
    ddb.scan.side_effect = [
        {
            "Items": [
                pack(
                    {
                        "PK": "IDENTITY#" + actor(1),
                        "SK": "META",
                        "role": "viewer",
                        "epoch": 1,
                        "enabled": True,
                        "instance_ids": [IID],
                        "binding": expected,
                    }
                )
            ],
            "LastEvaluatedKey": {"PK": {"S": "continuation"}},
        },
        {
            "Items": [
                pack(
                    {
                        "PK": "IDENTITY#" + actor(2),
                        "SK": "META",
                        "role": "viewer",
                        "epoch": 2,
                        "enabled": False,
                        "instance_ids": [IID],
                        "binding": ["retired"],
                    }
                )
            ]
        },
    ]
    monkeypatch.setattr(security_ops, "assert_account", Mock())
    result = security_ops.access_review(bundle, factory=lambda *args: ddb)
    assert result["status"] == "REVIEW_REQUIRED" and len(result["grants"]) == 2
    assert not result["automatic_revocation"] and {r["current_release"] for r in result["grants"]} == {
        True,
        False,
    }
    assert ddb.scan.call_args.kwargs["ExclusiveStartKey"] == {"PK": {"S": "continuation"}}
    ddb.put_item.assert_not_called()


def test_private_operation_output_is_owner_only_and_symlinks_are_denied(tmp_path):
    path = tmp_path / "evidence.json"
    security_ops.private_write(path, {"classification": "restricted"})
    assert path.stat().st_mode & 0o777 == 0o600
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(OSError):
        security_ops.private_write(link, {"unsafe": True})
    assert json.loads(path.read_text()) == {"classification": "restricted"}


@pytest.fixture
def audit_factory():
    from datetime import datetime, timezone

    from infra import evidence_audit

    desired = durable_templates.foundation(SPEC, CONFIG)["Resources"]
    props = desired["AccessAuditTrail"]["Properties"]
    s3, trail = Mock(), Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            k: True
            for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
        }
    }
    s3.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }
    }
    s3.get_bucket_policy.return_value = {
        "Policy": json.dumps(desired["AccessAuditPolicy"]["Properties"]["PolicyDocument"])
    }
    s3.get_bucket_lifecycle_configuration.return_value = {
        "Rules": [{"Expiration": {"Days": 30}, "NoncurrentVersionExpiration": {"NoncurrentDays": 30}}]
    }
    trail.get_trail.return_value = {
        "Trail": {
            "TrailARN": f"arn:aws:cloudtrail:{SPEC['monitor_region']}:{SPEC['account_id']}:trail/{props['TrailName']}",
            "S3BucketName": props["S3BucketName"],
            "IsMultiRegionTrail": False,
            "LogFileValidationEnabled": True,
        }
    }
    trail.get_trail_status.return_value = {
        "IsLogging": True,
        "LatestDeliveryTime": datetime.now(timezone.utc),
    }
    trail.get_event_selectors.return_value = {"AdvancedEventSelectors": props["AdvancedEventSelectors"]}
    return (
        evidence_audit,
        {"spec": SPEC, "config": CONFIG},
        lambda service, region: {"s3": s3, "cloudtrail": trail}[service],
        s3,
        trail,
    )


def test_audit_configuration_and_retention_are_verified_with_private_destination(audit_factory):
    audit, bundle, factory, s3, _ = audit_factory
    audit.verify(bundle, factory)
    assert s3.get_bucket_policy.call_args.kwargs["ExpectedBucketOwner"] == SPEC["account_id"]


@pytest.mark.parametrize(
    "drift", ["public", "unencrypted", "retention", "policy", "stopped", "delivery_error", "selectors"]
)
def test_audit_drift_is_not_accepted_as_qualified(audit_factory, drift):
    audit, bundle, factory, s3, trail = audit_factory
    if drift == "public":
        s3.get_public_access_block.return_value["PublicAccessBlockConfiguration"]["BlockPublicPolicy"] = False
    elif drift == "unencrypted":
        s3.get_bucket_encryption.return_value["ServerSideEncryptionConfiguration"]["Rules"][0][
            "ApplyServerSideEncryptionByDefault"
        ]["SSEAlgorithm"] = "none"
    elif drift == "retention":
        s3.get_bucket_lifecycle_configuration.return_value["Rules"][0]["Expiration"]["Days"] = 365
    elif drift == "policy":
        s3.get_bucket_policy.return_value = {"Policy": json.dumps({"Statement": []})}
    elif drift == "stopped":
        trail.get_trail_status.return_value["IsLogging"] = False
    elif drift == "delivery_error":
        trail.get_trail_status.return_value["LatestDeliveryError"] = "synthetic"
    else:
        trail.get_event_selectors.return_value = {"AdvancedEventSelectors": []}
    with pytest.raises(VerificationError):
        audit.verify(bundle, factory)


@pytest.mark.parametrize(
    "raw",
    [
        '{"password":"fixture-sensitive-marker\\"suffix"}',
        "password%25253Dfixture-sensitive-marker",
        "2001:db8::1 person@example.invalid",
        "Bearer fixture-auth-marker\npassword=fixture-sensitive-marker",
    ],
)
def test_encoded_escaped_and_ipv6_fixture_profiles_remain_redacted(raw):
    cleaned = safety.text(raw)
    assert "fixture-sensitive-marker" not in cleaned and "suffix" not in cleaned
    assert "2001:db8::1" not in cleaned and "person@example.invalid" not in cleaned
    assert safety.text(cleaned) == cleaned


@pytest.fixture
def recipients(monkeypatch):
    from infra.spec import topic_arn

    bundle = {
        "spec": {**SPEC, "reference_only": False},
        "config": CONFIG,
        "bindings": bindings(),
        "review_hash": "synthetic-review",
        "stages": {s: {} for s in ("routing", "durable-foundation", "observation-foundation")},
    }
    metadata, by_stage = {}, {}
    for stage, suffix in (
        ("routing", "reports"),
        ("durable-foundation", "incident-fallback"),
        ("observation-foundation", "observation-fallback"),
    ):
        topic = topic_arn(SPEC, suffix)
        arn = topic + ":synthetic-removed"
        metadata[arn] = {"Protocol": "email", "TopicArn": topic, "Endpoint": "former@example.invalid"}
        by_stage[stage] = [
            {
                "ResourceType": "AWS::SNS::Subscription",
                "ResourceStatus": "CREATE_COMPLETE",
                "PhysicalResourceId": arn,
            }
        ]
    sns, cfn = Mock(), Mock()

    def attributes(SubscriptionArn):
        if SubscriptionArn not in metadata:
            raise ClientError({"Error": {"Code": "NotFound"}}, "GetSubscriptionAttributes")
        return {"Attributes": metadata[SubscriptionArn]}

    sns.get_subscription_attributes.side_effect = attributes
    sns.unsubscribe.side_effect = lambda SubscriptionArn: metadata.pop(SubscriptionArn, None)
    cfn.get_paginator.return_value.paginate.side_effect = lambda StackName: [
        {"StackResourceSummaries": by_stage[StackName]}
    ]
    monkeypatch.setattr(security_ops, "assert_account", Mock())
    monkeypatch.setattr(security_ops.durable_ops, "require_reviewed_source", Mock())
    monkeypatch.setattr(
        security_ops.durable_ops, "owned_stack", lambda spec, stage, **kw: (cfn, {"StackId": stage})
    )
    return bundle, lambda service, region: sns if service == "sns" else cfn, sns, metadata, by_stage


def test_recipient_offboarding_covers_primary_and_both_fallbacks(recipients):
    bundle, factory, sns, metadata, _ = recipients
    plan = security_ops.recipient_plan(bundle, factory)
    assert len(plan["retire"]) == 3
    assert security_ops.retire_recipients(bundle, plan, factory)["status"] == "RETIRED"
    assert not metadata and sns.unsubscribe.call_count == 3


def test_recipient_stale_plan_cannot_remove_new_or_unowned_subscription(recipients):
    bundle, factory, sns, metadata, _ = recipients
    plan = security_ops.recipient_plan(bundle, factory)
    metadata[plan["retire"][0]["arn"]]["Endpoint"] = "changed@example.invalid"
    with pytest.raises(VerificationError, match="changed"):
        security_ops.retire_recipients(bundle, plan, factory)
    sns.unsubscribe.assert_not_called()


def test_offboarding_does_not_treat_api_failure_as_confirmed_removal(recipients):
    bundle, factory, sns, _, _ = recipients
    plan = security_ops.recipient_plan(bundle, factory)
    sns.unsubscribe.side_effect = None
    with pytest.raises(VerificationError, match="still exists"):
        security_ops.retire_recipients(bundle, plan, factory)
    assert sns.unsubscribe.call_count == 1


def test_pending_owned_recipient_requires_explicit_resolution(recipients):
    bundle, factory, sns, _, by_stage = recipients
    by_stage["routing"][0]["PhysicalResourceId"] = "PendingConfirmation"
    with pytest.raises(VerificationError, match="unconfirmed"):
        security_ops.recipient_plan(bundle, factory)
    sns.unsubscribe.assert_not_called()


def test_real_low_level_sdk_accepts_typed_admission_parameters_without_double_serialization(monkeypatch):
    import boto3
    from botocore.stub import Stubber

    monkeypatch.setenv("KIRA_WORK_POLICY", json.dumps(work_policy.DEFAULT))
    # Explicit synthetic credentials and Stubber ensure no credential-chain/AWS access.
    client = boto3.session.Session().client(
        "dynamodb",
        region_name="eu-central-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    observed = []
    client.meta.events.register(
        "before-parameter-build.dynamodb.TransactWriteItems",
        lambda params, **kw: observed.append(copy.deepcopy(params)),
    )
    with Stubber(client) as stub:
        stub.add_response("transact_write_items", {})
        q = Quotas(SimpleNamespace(name="synthetic"), client=client, clock=lambda: 7200)
        q.admit(actor(1), "chat")
    op = observed[0]["TransactItems"][0]["Update"]
    assert op["Key"]["PK"] == {"S": f"QUOTA#chat#{actor(1)}#2"}
    assert op["ExpressionAttributeValues"][":tokens"] == {"N": "24000"}


def test_restored_old_grants_and_sessions_remain_denied_after_new_release_binding(setup, monkeypatch):
    ticket = setup.sessions.issue(setup.claims)
    new_release = "b" * 64
    monkeypatch.setenv("RUNTIME_RELEASE", new_release)
    setup.policy = copy.deepcopy(setup.policy)
    setup.policy["binding"][2] = new_release
    setup.path.write_text(json.dumps(setup.policy))
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "report", IID)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.issue(setup.claims)


def test_production_missing_diagnostic_policy_fails_before_creating_model_client(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("KIRA_DIAGNOSTIC_POLICY", raising=False)
    with pytest.raises(runtime.RuntimeStop, match="DIAGNOSTIC_POLICY_UNAVAILABLE"):
        drive()


def test_erasure_does_not_remove_foreign_object_versions_even_with_prefix_response_corruption(eraser):
    erase, _, s3 = eraser
    s3.objects.append({"Key": "unrelated/customer-object", "VersionId": "foreign"})
    with pytest.raises(ValueError):
        erase.plan("b" * 32)
    assert not s3.deleted


def test_erasure_decimal_plan_roundtrip_is_reviewable_and_applies(eraser, tmp_path):
    from decimal import Decimal

    erase, table, _ = eraser
    meta = table.rows[(table.pk, "META")]
    for key in ("fencing_token", "deadline_epoch", "lease_until"):
        meta[key] = Decimal(meta[key])
    plan = erase.plan("b" * 32)
    path = tmp_path / "private-plan.json"
    security_ops.private_write(path, plan)
    reviewed = json.loads(path.read_text())
    assert reviewed == plan
    assert erase.apply(reviewed)["status"] == "DELETED"


def test_canary_without_individual_identity_rejects_before_any_aws_client():
    from infra import owned_ops

    factory = Mock()
    with pytest.raises(VerificationError, match="identity-enabled"):
        owned_ops.canary(
            {"spec": {"environment": "staging"}, "config": {}},
            factory,
            allow_model_invocation=True,
            access_ticket="synthetic",
        )
    factory.assert_not_called()


@pytest.mark.parametrize("field", ["token", "access_ticket", "aws_secret_access_key", "session_token"])
def test_named_credentials_are_redacted_but_continuations_are_preserved(field):
    raw = {field: "fixture-sensitive-marker", "next_token": "opaque-continuation"}
    got = safety.bounded(raw)
    assert got[field] == "[redacted]" and got["next_token"] == "opaque-continuation"
    assert json.loads(safety.text(json.dumps(raw))) == got


@pytest.mark.parametrize("case", evaluate_diagnostics.suite()[0]["cases"], ids=lambda c: c["id"])
def test_evaluation_evidence_matches_real_tool_response_contracts(case):
    for entry in case["catalog"]:
        schema = runtime.operation(entry["tool"])["responses"]["200"]["content"]["application/json"]["schema"]
        runtime.validate(entry["result"], schema)


def test_default_chat_budget_allows_full_corroborated_hang_with_discovery(monkeypatch):
    monkeypatch.setenv("KIRA_DIAGNOSTIC_POLICY", diagnosis.VERSION)
    case = copy.deepcopy(
        next(c for c in evaluate_diagnostics.suite()[0]["cases"] if c["id"] == "correlated-hang")
    )
    policy = runtime.Limits(**work_policy.DEFAULT["chat_limits"])
    budget = runtime.MemoryBudget(policy)
    tools = evaluate_diagnostics.FixtureTools(case["catalog"], budget.reserve)
    turns = []
    calls = [("fetch_logs", {"instance_id": IID})]
    mapping = {}
    for index, entry in enumerate(case["catalog"], 1):
        args = {"instance_id": IID, "time_string": "2026-10-01T10:07:30Z", "window_minutes": "8"}
        args.update(
            {"log_group_name": entry["result"]["log_group"]}
            if entry["tool"] == "fetch_logs"
            else {"metric_id": entry["result"]["descriptor"]["metric_id"]}
        )
        calls.append((entry["tool"], args))
        mapping[entry["id"]] = diagnosis.catalog_entry(entry["tool"], safety.bounded(entry["result"]), index)[
            "id"
        ]
    for index, (name, args) in enumerate(calls):
        turns.append(
            answer(
                stop="tool_use", blocks=[{"toolUse": {"toolUseId": str(index), "name": name, "input": args}}]
            )
        )
    report = case["candidate"]
    for field in ("findings", "hypotheses"):
        for item in report[field]:
            item["evidence_ids"] = [mapping[i] for i in item["evidence_ids"]]
    for fact in report["facts"]:
        fact["evidence_id"] = mapping[fact["evidence_id"]]
    turns.append(answer(json.dumps(report)))
    client = Mock()
    client.converse.side_effect = turns
    client.count_tokens.return_value = {"inputTokens": 2000}
    result = runtime.run(
        case["prompt"],
        model_id="synthetic",
        region="eu-central-1",
        tools=tools,
        reserve=budget.reserve,
        limits=policy,
        deadline=time.time() + 180,
        client=client,
        require_evidence=True,
    )
    assert result["complete"] and result["diagnosis"]["status"] == "VALID"
    assert result["diagnosis"]["report"]["findings"][0]["kind"] == "hang_correlated"
    assert budget.used["model_steps"] == 6 and budget.used["tool_calls"] == 5
    assert budget.used["tokens_reserved"] == 18144


def test_fixture_tool_rejects_cross_scope_and_charges_work_before_returns():
    policy = runtime.Limits(**work_policy.DEFAULT["chat_limits"])
    budget = runtime.MemoryBudget(policy)
    case = evaluate_diagnostics.suite()[0]["cases"][0]
    tools = evaluate_diagnostics.FixtureTools(case["catalog"], budget.reserve)
    response, complete = tools.invoke("fetch_logs", {"instance_id": IID}, time.time() + 5)
    runtime.validate(
        response, runtime.operation("fetch_logs")["responses"]["200"]["content"]["application/json"]["schema"]
    )
    assert complete and response["metric_catalog"][0]["metric_id"]
    assert budget.used["tool_calls"] == 1
    with pytest.raises(runtime.RuntimeStop, match="UNAUTHORIZED"):
        tools.invoke("fetch_logs", {"instance_id": "i-fffffffffffffffff"}, time.time() + 5)
    assert budget.used["tool_calls"] == 1
