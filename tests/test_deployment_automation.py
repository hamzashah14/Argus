import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from infra import automation, deployment_preflight, durable, identity, identity_ops, owned_runtime
from infra.spec import name, prefix
from infra.verify import VerificationError
from scripts.dev.validate_durable import examples
from tests.helpers import ROOT


def configuration(
    tmp_path,
    target="standalone",
    observations=False,
    environment="staging",
    *,
    identity=True,
    model_api=False,
):
    spec = json.loads(
        (
            ROOT
            / ("examples/observability.example.json" if observations else "examples/deployment.example.json")
        ).read_text()
    )
    spec["environment"] = environment
    if model_api:
        spec.pop("model_arns")
        spec["model_provider"] = "model_api"
        spec["model_api"] = {"protocol": "openai", "base_url": "https://models.example.invalid/v1"}
    config = json.loads(
        (
            ROOT / ("examples/identity.example.json" if identity else "examples/durable.example.json")
        ).read_text()
    )
    config["runtime_target"] = target
    (tmp_path / "deployment.json").write_text(json.dumps(spec))
    (tmp_path / "runtime.json").write_text(json.dumps(config))
    (tmp_path / "automation.json").write_text(
        json.dumps(
            {
                "version": 1,
                "spec": "deployment.json",
                "runtime_config": "runtime.json",
                "profile": None,
                "wheelhouse": str(ROOT / ".build/wheels"),
                "initial_access": [
                    {
                        "subject": "synthetic-operator",
                        "enabled": True,
                        "role": "investigator",
                        "instance_ids": [spec["instances"][0]["id"]],
                    }
                ]
                if identity
                else [],
            }
        )
    )
    return automation.plan(tmp_path / "automation.json")


def test_dry_run_plan_no_aws_and_settings_change_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "factory", Mock(side_effect=AssertionError("AWS forbidden")))
    planned = configuration(tmp_path)
    assert planned["spec"]["reference_only"] and not planned["automatic_activation"]
    assert "AWS::SQS::Queue" in planned["resources"]["durable-foundation"]["resource_types"]
    assert "staging-canary" in planned["stages"]
    assert planned == automation.plan(tmp_path / "automation.json")
    p = tmp_path / "runtime.json"
    config = json.loads(p.read_text())
    config["retention_days"] += 1
    p.write_text(json.dumps(config))
    assert planned["plan_hash"] != automation.plan(tmp_path / "automation.json")["plan_hash"]


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "missing",
        "bad_profile",
        "bad_grant",
        "duplicate_subject",
        "unknown_instance",
        "unpaused",
        "access_without_identity",
    ],
)
def test_bad_settings_fail_without_clients(tmp_path, mutation):
    configuration(tmp_path)
    p = tmp_path / "automation.json"
    value = json.loads(p.read_text())
    if mutation == "unknown":
        value["credentials"] = "rejected"
    if mutation == "missing":
        del value["version"]
    if mutation == "bad_profile":
        value["profile"] = "../unsafe"
    if mutation == "bad_grant":
        value["initial_access"][0]["enabled"] = "yes"
    if mutation == "duplicate_subject":
        value["initial_access"] *= 2
    if mutation == "unknown_instance":
        value["initial_access"][0]["instance_ids"] = ["i-foreign"]
    if mutation in {"unpaused", "access_without_identity"}:
        r = tmp_path / "runtime.json"
        config = json.loads(r.read_text())
        if mutation == "unpaused":
            config["investigation_paused"] = False
        else:
            config.pop("identity")
            config.pop("security")
        r.write_text(json.dumps(config))
    p.write_text(json.dumps(value))
    with pytest.raises((VerificationError, ValueError)):
        automation.plan(p)


def test_private_state_atomic_and_lock(tmp_path):
    path = tmp_path / "state.json"
    automation.private_json(path, {"status": "WAITING"})
    assert path.stat().st_mode & 0o777 == 0o600
    with automation.locked(tmp_path):
        with pytest.raises(VerificationError, match="Another deployment"):
            with automation.locked(tmp_path):
                pass
    with automation.locked(tmp_path):
        pass
    link = tmp_path / "state.json.tmp"
    link.symlink_to(path)
    with pytest.raises(OSError):
        automation.private_json(path, {"status": "corrupt"})
    assert json.loads(path.read_text()) == {"status": "WAITING"}


@pytest.mark.parametrize("target", ["standalone", "agentcore"])
@pytest.mark.parametrize("observations", [False, True])
def test_order_and_separate_runtime_candidates(tmp_path, target, observations):
    p = configuration(tmp_path, target, observations)
    stages = p["stages"]
    assert (
        stages.index("identity-foundation-bound")
        < stages.index("owned-tools")
        < stages.index("durable-runtime")
    )
    assert stages.index("chat-runtime") < stages.index("staging-canary") < stages.index("routing")
    if target == "agentcore":
        assert stages.index("agentcore-chat-endpoint") < stages.index("durable-runtime")
    if observations:
        assert stages.index("health-bootstrap") < stages.index("staging-canary")


class FakeDriver(automation.Driver):
    """Real staged renderer; synthetic SDK/build adapters only."""

    def __init__(self, planned, directory, monkeypatch):
        self.plan, self.directory = planned, directory
        spec, config = planned["spec"], planned["runtime_config"]
        # The example outputs (foundation, tools, versions) do not depend on the model provider.
        bedrock_spec = {k: v for k, v in spec.items() if k not in {"model_provider", "model_api"}}
        bedrock_spec.setdefault(
            "model_arns", json.loads((ROOT / "examples/deployment.example.json").read_text())["model_arns"]
        )
        _, self.outputs, artifacts, versions = examples(
            bedrock_spec,
            {k: v for k, v in config.items() if k not in {"identity", "security"}},
            include_bindings=True,
        )
        self.outputs["versions"] = versions
        self.outputs["identity"] = {
            "SigningSecretArn": f"arn:aws:secretsmanager:{spec['bedrock_region']}:{spec['account_id']}:secret:{identity.secret_name(spec)}-123abc",
            "SigningSecretVersion": "a" * 32,
        }
        self.outputs["secret"] = {
            "arn": f"arn:aws:secretsmanager:{spec['bedrock_region']}:{spec['account_id']}:secret:kira-staging/log-cursor-123abc",
            "version_id": "a" * 32,
        }
        self.outputs["model_secret"] = {
            "arn": f"arn:aws:secretsmanager:{spec['bedrock_region']}:{spec['account_id']}:secret:{prefix(spec)}/model-api-key-123abc",
            "version_id": "a" * 32,
        }
        self.missing_model_secret = False
        self.artifacts = artifacts
        self.clients = Mock(side_effect=AssertionError("No live SDK"))
        self.preflight = {"status": "SIMULATED"}
        self.calls = []
        self.grants = {}
        self.canaries = 0
        from infra import observations, release
        from scripts.build_lambdas import PIPELINE_FUNCTIONS

        def manifest(functions):
            return {"functions": {f: {"sha256": "b" * 64} for f in functions}}

        monkeypatch.setattr(
            durable,
            "checked_build",
            lambda path, **kw: manifest(kw.get("expected_functions", PIPELINE_FUNCTIONS)),
        )
        monkeypatch.setattr(release, "checked_build", lambda *a: manifest(("fetch_logs", "fetch_metrics")))
        monkeypatch.setattr(
            observations,
            "checked_build",
            lambda *a: manifest(("observation_probe", "observation_canary", "observation_receipt")),
        )
        monkeypatch.setattr(deployment_preflight, "check", lambda *a, **kw: self.preflight)

    def build(self):
        self.calls.append("build")

    def inspect_stack(self, *a):
        return None

    def stage(self, bundle, stage, record, save, **kw):
        assert stage in bundle["stages"]
        assert (
            record.get("template_hash", bundle["stages"][stage]["template_hash"])
            == bundle["stages"][stage]["template_hash"]
        )
        record.update(status="COMPLETE", template_hash=bundle["stages"][stage]["template_hash"])
        save()
        self.calls.append(stage)

    def op(self, bundle, command, **kw):
        spec = self.plan["spec"]
        stage = kw.get("stage")
        self.calls.append(command + (":" + stage if stage else ""))
        if command == "collect":
            if stage == "durable-foundation":
                return self.outputs["foundation"]
            if stage == "owned-tools":
                return self.outputs["tools"]
            if stage == "durable-runtime":
                return self.outputs["versions"]
            if stage == "chat-runtime":
                return {
                    "ChatVersionArn": f"arn:aws:lambda:{spec['monitor_region']}:{spec['account_id']}:function:{name(spec, 'chat-investigate', True)}:1"
                }
            if stage == "observation-runtime":
                return {
                    logical
                    + "VersionArn": f"arn:aws:lambda:{spec['monitor_region']}:{spec['account_id']}:function:{name(spec, function.replace('_', '-'), True)}:1"
                    for function, logical in __import__(
                        "infra.observation_templates", fromlist=["FUNCTIONS"]
                    ).FUNCTIONS.items()
                }
            if stage == "identity-foundation":
                return {"SessionIssuerRoleArn": f"arn:aws:iam::{spec['account_id']}:role/kira/staging/issuer"}
            if stage == "routing":
                return {"UiRoleArn": f"arn:aws:iam::{spec['account_id']}:role/kira/staging/ui"}
            if stage.endswith("-runtime"):
                suffix = stage[:-8]
                runtime_id = name(spec, suffix, True).replace("-", "_") + "-1234567890"
                return {
                    "RuntimeId": runtime_id,
                    "RuntimeVersion": "1",
                    "RuntimeArn": f"arn:aws:bedrock-agentcore:{spec['bedrock_region']}:{spec['account_id']}:runtime/{runtime_id}",
                }
            if stage.endswith("-endpoint"):
                suffix = stage[:-9]
                runtime_id = name(spec, suffix, True).replace("-", "_") + "-1234567890"
                arn = f"arn:aws:bedrock-agentcore:{spec['bedrock_region']}:{spec['account_id']}:runtime/{runtime_id}"
                endpoint = "release_" + spec["release_id"].replace("-", "_")
                return {
                    "RuntimeArn": arn,
                    "RuntimeVersion": "1",
                    "EndpointName": endpoint,
                    "EndpointArn": arn + "/runtime-endpoint/" + endpoint + "-1234567890",
                }
        if command == "identity-version":
            return self.outputs["identity"]
        if command == "cursor-version":
            return self.outputs["secret"]
        if command == "model-secret-version":
            if self.missing_model_secret:
                raise VerificationError("Model API key secret has no unique current version")
            return self.outputs["model_secret"]
        if command == "upload":
            from infra import templates

            kind = kw["artifact_kind"]
            functions = {
                "tools": ("fetch_logs", "fetch_metrics"),
                "pipeline": tuple(self.artifacts),
                "observation": ("observation_probe", "observation_canary", "observation_receipt"),
                "host": ("incident_investigate",),
            }[kind]
            artifacts = {
                f: {
                    "sha256": "b" * 64,
                    "bucket": templates.bucket_name(
                        spec, "tools" if kind in {"tools", "host"} else "monitor"
                    ),
                    "key": f"releases/{spec['release_id']}/" + "b" * 64 + ".zip",
                    "version_id": "synthetic-version",
                }
                for f in functions
            }
            return artifacts["incident_investigate"] if kind == "host" else artifacts
        if command == "canary":
            self.canaries += 1
            self.canary_ticket = kw.get("access_ticket_file")
            return {
                "status": "PASS",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "bundle_hash": bundle["review_hash"],
                "canary_tools": ["fetch_logs", "fetch_metrics"],
                "runtime_target": self.plan["runtime_config"]["runtime_target"],
                "runtime_release": owned_runtime.fingerprint(
                    spec, self.plan["runtime_config"], bundle["bindings"]
                ),
            }
        if command == "retirement-plan":
            return {"disable_alarms": [], "unsubscribe": []}
        return {"status": "PASS"}

    def command(self, module, args, output=None):
        if module == "infra.identity_ops" and args[0] == "grant-plan":
            request = json.loads(Path(args[args.index("--request") + 1]).read_text())
            bundle = json.loads((self.directory / "bundle/bundle.json").read_text())
            diff = identity_ops.change(bundle, request, self.grants.get(request["subject"]))
            automation.private_json(output, diff)
            return diff
        if module == "infra.identity_ops" and args[0] == "grant-apply":
            request = json.loads(Path(args[args.index("--request") + 1]).read_text())
            diff = json.loads(Path(args[args.index("--grant-plan") + 1]).read_text())
            self.grants[request["subject"]] = diff["after"]
        return {"status": "PASS"}


@pytest.mark.parametrize("target", ["standalone", "agentcore"])
@pytest.mark.parametrize("observations", [False, True])
def test_complete_orchestration_with_real_renderer_and_resume(tmp_path, monkeypatch, target, observations):
    p = configuration(tmp_path, target, observations)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(p, directory, monkeypatch)
    result = automation.deploy(p, directory, driver)
    assert result["status"] == "WAITING" and not result["auto_resume"]
    assert "configure OIDC" in result["next"]
    assert driver.canaries == 0 and "routing" not in result["completed_stages"]
    epoch = driver.grants["synthetic-operator"]["epoch"]
    result = automation.deploy(p, directory, driver, allow_model=True, ticket=tmp_path / "ticket")
    assert result["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING"
    assert "routing" in result["completed_stages"] and driver.canaries == 1
    assert driver.grants["synthetic-operator"]["epoch"] == epoch
    assert json.loads((directory / "ui-connection.json").read_text())["ui_role_arn"]
    result = automation.deploy(p, directory, driver, allow_model=True, ticket=tmp_path / "ticket")
    assert result["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING" and driver.canaries == 1


def test_changed_plan_rejected_before_operations(tmp_path):
    p = configuration(tmp_path)
    directory = tmp_path / "work"
    directory.mkdir()
    automation.private_json(directory / "state.json", {"version": 1, "plan_hash": "changed"})
    with pytest.raises(VerificationError, match="Configuration/source changed"):
        automation.deploy(p, directory, Mock())


def test_paid_canary_ambiguity_never_retried(tmp_path, monkeypatch):
    p = configuration(tmp_path)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(p, directory, monkeypatch)
    automation.deploy(p, directory, driver)
    state = json.loads((directory / "state.json").read_text())
    state["canary_requested"] = True
    automation.private_json(directory / "state.json", state)
    result = automation.deploy(p, directory, driver, allow_model=True, ticket=tmp_path / "ticket")
    assert result["status"] == "WAITING" and "ambiguous" in result["next"] and driver.canaries == 0
    result = automation.deploy(
        p, directory, driver, allow_model=True, ticket=tmp_path / "ticket", retry_canary=True
    )
    assert result["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING" and driver.canaries == 1


@pytest.mark.parametrize(
    "decision,context", [("implicitDeny", []), ("explicitDeny", []), ("allowed", ["missing-condition"])]
)
def test_permission_denials_and_missing_context_are_not_success(decision, context):
    iam = Mock()
    iam.simulate_principal_policy.return_value = {
        "EvaluationResults": [
            {"EvalActionName": "iam:PassRole", "EvalDecision": decision, "MissingContextValues": context}
        ]
    }
    result = deployment_preflight.simulate(
        iam,
        {
            "principal": "arn:aws:iam::123456789012:role/operator",
            "actions": ["iam:PassRole"],
            "resource": "arn:aws:iam::123456789012:role/deploy",
            "region": "eu-central-1",
            "context": {"iam:PassedToService": "cloudformation.amazonaws.com"},
        },
    )
    assert result[0]["decision"] == decision and result[0]["missing_context"] == context


def test_permission_pagination_and_omitted_result():
    iam = Mock()
    iam.simulate_principal_policy.side_effect = [
        {"EvaluationResults": [], "IsTruncated": True, "Marker": "next"},
        {"EvaluationResults": [{"EvalActionName": "a", "EvalDecision": "allowed"}]},
    ]
    request = {"principal": "p", "region": "r", "resource": "*", "actions": ["a"], "context": {}}
    assert deployment_preflight.simulate(iam, request)[0]["decision"] == "allowed"
    assert iam.simulate_principal_policy.call_args.kwargs["Marker"] == "next"
    iam.simulate_principal_policy.side_effect = None
    iam.simulate_principal_policy.return_value = {"EvaluationResults": []}
    with pytest.raises(VerificationError, match="omitted"):
        deployment_preflight.simulate(iam, request)


def test_synthetic_preflight_no_clients(tmp_path):
    p = configuration(tmp_path)
    client = Mock(side_effect=AssertionError("AWS forbidden"))
    with pytest.raises(VerificationError, match="Synthetic"):
        deployment_preflight.check(p, client)
    client.assert_not_called()


def test_wrong_account_no_iam_or_write(tmp_path):
    p = configuration(tmp_path)
    p["spec"]["reference_only"] = False
    sts = Mock()
    sts.get_caller_identity.return_value = {"Account": "999999999999"}
    factory = Mock(return_value=sts)
    with pytest.raises(VerificationError, match="Wrong AWS"):
        deployment_preflight.check(p, factory)
    assert factory.call_count == 1


def test_existing_stack_access_denial_not_absence(tmp_path):
    p = configuration(tmp_path)
    driver = object.__new__(automation.Driver)
    driver.plan = p
    cfn = Mock()
    cfn.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "private"}}, "DescribeStacks"
    )
    driver.clients = Mock(return_value=cfn)
    bundle = {"stages": {"routing": {"stack": "example", "region": "eu-central-1"}}, "spec": p["spec"]}
    with pytest.raises(ClientError):
        driver.inspect_stack(bundle, "routing")


@pytest.mark.parametrize("status", ["CREATE_IN_PROGRESS", "ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"])
def test_in_progress_and_rollback_not_success(tmp_path, status):
    p = configuration(tmp_path)
    driver = object.__new__(automation.Driver)
    driver.clients = Mock()
    driver.inspect_stack = Mock(return_value={"StackStatus": status})
    driver.template_matches = Mock(return_value=False)
    driver.op = Mock()
    bundle = {
        "stages": {
            "owned-tools": {
                "stack": "example",
                "region": "eu-central-1",
                "create_only": True,
                "template_hash": "hash",
            }
        },
        "spec": p["spec"],
    }
    error = automation.Waiting if status == "CREATE_IN_PROGRESS" else VerificationError
    with pytest.raises(error):
        driver.stage(bundle, "owned-tools", {}, Mock())
    driver.op.assert_not_called()


def test_review_in_progress_continues_exact_change_set(tmp_path):
    p = configuration(tmp_path)
    driver = object.__new__(automation.Driver)
    driver.directory = tmp_path
    cfn = Mock()
    cfn.describe_change_set.return_value = {"Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE"}
    driver.clients = Mock(return_value=cfn)
    driver.inspect_stack = Mock(return_value={"StackStatus": "REVIEW_IN_PROGRESS"})
    driver.op = Mock(
        return_value={
            "changes": [{"Type": "Resource", "ResourceChange": {"Action": "Add"}}],
            "change_set": "cs",
            "review_hash": "diff",
        }
    )
    bundle = {
        "review_hash": "a" * 64,
        "stages": {
            "owned-tools": {
                "stack": "example",
                "region": "eu-central-1",
                "create_only": True,
                "template_hash": "hash",
            }
        },
        "spec": p["spec"],
    }
    record = {}
    with pytest.raises(automation.Waiting) as exc:
        driver.stage(bundle, "owned-tools", record, Mock())
    assert exc.value.automatic and record["status"] == "EXECUTION_INTENT"
    assert [c.args[1] for c in driver.op.call_args_list] == ["inspect", "execute"]


@pytest.mark.parametrize(
    "action,replacement", [("Remove", "False"), ("Modify", "True"), ("Modify", "Conditional")]
)
def test_destructive_change_sets_never_execute(tmp_path, action, replacement):
    p = configuration(tmp_path)
    driver = object.__new__(automation.Driver)
    driver.directory = tmp_path
    cfn = Mock()
    cfn.describe_change_set.return_value = {"Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE"}
    driver.clients = Mock(return_value=cfn)
    driver.inspect_stack = Mock(return_value={"StackStatus": "UPDATE_COMPLETE"})
    driver.template_matches = Mock(return_value=False)
    driver.op = Mock(
        return_value={
            "changes": [
                {"Type": "Resource", "ResourceChange": {"Action": action, "Replacement": replacement}}
            ]
        }
    )
    bundle = {
        "review_hash": "a" * 64,
        "stages": {
            "routing": {
                "stack": "example",
                "region": "eu-central-1",
                "create_only": False,
                "template_hash": "hash",
            }
        },
        "spec": p["spec"],
    }
    with pytest.raises(VerificationError, match="deletes/replaces"):
        driver.stage(bundle, "routing", {}, Mock())
    assert driver.op.call_count == 1


def test_profile_does_not_inherit_static_credentials(tmp_path, monkeypatch):
    planned = configuration(tmp_path)
    planned["profile"] = "customer-sso"
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dummy")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dummy")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "dummy")
    monkeypatch.setattr(automation, "factory", Mock())
    driver = automation.Driver(planned, tmp_path)
    assert driver.env["AWS_PROFILE"] == "customer-sso"
    assert not {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"} & driver.env.keys()
    assert os.environ["AWS_ACCESS_KEY_ID"] == "dummy"


def preflight_factory(planned, decision="allowed"):
    spec = planned["spec"]
    sts = Mock()
    sts.get_caller_identity.return_value = {
        "Account": spec["account_id"],
        "Arn": f"arn:aws:sts::{spec['account_id']}:assumed-role/customer-ci/synthetic-session",
    }
    iam = Mock()

    def role(**kw):
        return {
            "Role": {
                "RoleName": kw["RoleName"],
                "Arn": f"arn:aws:iam::{spec['account_id']}:role/{kw['RoleName']}",
                "AssumeRolePolicyDocument": {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "cloudformation.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ]
                },
            }
        }

    iam.get_role.side_effect = role
    iam.simulate_principal_policy.side_effect = lambda **kw: {
        "EvaluationResults": [
            {"EvalActionName": a, "EvalDecision": decision, "MissingContextValues": []}
            for a in kw["ActionNames"]
        ]
    }
    ec2 = Mock()
    ec2.describe_regions.return_value = {
        "Regions": [{"RegionName": spec["monitor_region"], "OptInStatus": "opt-in-not-required"}]
    }
    ec2.describe_instances.return_value = {
        "Reservations": [
            {"Instances": [{"InstanceId": i["id"], "State": {"Name": "running"}} for i in spec["instances"]]}
        ]
    }
    lamb = Mock()
    lamb.get_account_settings.return_value = {"AccountLimit": {"UnreservedConcurrentExecutions": 110}}
    bedrock = Mock()
    bedrock.get_foundation_model.return_value = {
        "modelDetails": {"modelArn": spec.get("model_arns", ["unused-for-model-api"])[0]}
    }
    return {"sts": sts, "iam": iam, "ec2": ec2, "lambda": lamb, "bedrock": bedrock}


@pytest.mark.parametrize("decision", ["allowed", "implicitDeny", "explicitDeny"])
def test_complete_account_roles_inventory_capacity_permissions_preflight(tmp_path, decision):
    planned = configuration(tmp_path)
    planned["spec"]["reference_only"] = False
    clients = preflight_factory(planned, decision)
    result = deployment_preflight.check(planned, lambda service, region: clients[service])
    assert result["status"] == ("SIMULATED" if decision == "allowed" else "BLOCKED")
    assert bool(result["blockers"]) == (decision != "allowed")
    calls = clients["iam"].simulate_principal_policy.call_args_list
    assert calls and all(
        c.kwargs["PolicySourceArn"]
        in {planned["spec"]["ci_principal_arn"], planned["spec"]["deployment_role_arn"]}
        for c in calls
    )
    assert any(entry["ContextKeyType"] == "stringList" for c in calls for entry in c.kwargs["ContextEntries"])
    clients["bedrock"].get_foundation_model.assert_called_once()


@pytest.mark.parametrize("failure", ["wrong_role", "quota", "missing_ec2", "region_disabled", "wrong_trust"])
def test_account_prerequisites_fail_before_simulated_or_real_writes(tmp_path, failure):
    planned = configuration(tmp_path)
    planned["spec"]["reference_only"] = False
    clients = preflight_factory(planned)
    if failure == "wrong_role":
        clients["sts"].get_caller_identity.return_value["Arn"] = (
            "arn:aws:sts::123456789012:assumed-role/unrelated/session"
        )
    if failure == "quota":
        clients["lambda"].get_account_settings.return_value["AccountLimit"][
            "UnreservedConcurrentExecutions"
        ] = 10
    if failure == "missing_ec2":
        clients["ec2"].describe_instances.return_value = {"Reservations": []}
    if failure == "region_disabled":
        clients["ec2"].describe_regions.return_value = {"Regions": []}
    if failure == "wrong_trust":
        clients["iam"].get_role.side_effect = lambda **kw: {
            "Role": {
                "RoleName": kw["RoleName"],
                "Arn": f"arn:aws:iam::123456789012:role/{kw['RoleName']}",
                "AssumeRolePolicyDocument": {"Statement": []},
            }
        }
    with pytest.raises(VerificationError):
        deployment_preflight.check(planned, lambda service, region: clients[service])
    clients["iam"].simulate_principal_policy.assert_not_called()


def test_cli_synthetic_check_rejected_without_session(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "private_dir", lambda path: path)
    directory = tmp_path / ".local/customer"
    directory.mkdir(parents=True)
    configuration(directory)
    factory = Mock(side_effect=AssertionError("AWS forbidden"))
    monkeypatch.setattr(automation, "factory", factory)
    monkeypatch.setattr(
        "sys.argv",
        ["automation", "check", "--config", str(directory / "automation.json"), "--work-dir", str(directory)],
    )
    assert automation.main() == 1
    factory.assert_not_called()


def test_generated_ui_launch_uses_scoped_role_not_deployer(tmp_path, monkeypatch):
    from scripts.run_customer_ui import environment

    path = tmp_path / "ui.json"
    automation.private_json(
        path,
        {
            "environment": {
                "EXPECTED_ACCOUNT_ID": "123456789012",
                "MONITOR_REGION": "eu-central-1",
                "ENVIRONMENT": "staging",
            },
            "ui_role_arn": "arn:aws:iam::123456789012:role/kira/staging/ui",
        },
    )
    session = Mock()
    session.return_value.client.return_value.get_caller_identity.return_value = {
        "Account": "123456789012",
        "Arn": "arn:aws:sts::123456789012:assumed-role/ui/private-session",
    }
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dummy")
    result = environment(path, "customer-ui", session_factory=session)
    assert result["AWS_PROFILE"] == "customer-ui" and result["PYTHON_DOTENV_DISABLED"] == "1"
    assert "AWS_SECRET_ACCESS_KEY" not in result
    session.return_value.client.return_value.get_caller_identity.return_value["Arn"] = (
        "arn:aws:sts::123456789012:assumed-role/customer-ci/private-session"
    )
    with pytest.raises(ValueError, match="UI profile"):
        environment(path, "customer-ci", session_factory=session)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        environment(path, "customer-ui", session_factory=session)


@pytest.mark.parametrize(
    "interrupted",
    [
        "identity-foundation",
        "owned-tools",
        "agentcore-runtime",
        "agentcore-chat-endpoint",
        "durable-runtime",
        "chat-runtime",
        "observation-runtime",
        "routing",
    ],
)
def test_resume_at_interrupted_stage_reconciles_real_bindings(tmp_path, monkeypatch, interrupted):
    planned = configuration(tmp_path, "agentcore", True)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    original = driver.stage
    hit = False

    def once(bundle, stage, record, save, **kwargs):
        nonlocal hit
        if stage == interrupted and not hit:
            hit = True
            record.update(status="INTENT", template_hash=bundle["stages"][stage]["template_hash"])
            save()
            raise automation.Waiting("Injected asynchronous AWS boundary", automatic=True)
        return original(bundle, stage, record, save, **kwargs)

    driver.stage = once
    for _ in range(3):
        result = automation.deploy(planned, directory, driver, allow_model=True, ticket=tmp_path / "ticket")
        if result["status"] != "WAITING":
            break
    assert hit and result["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING"
    assert driver.canaries == 1


def test_production_candidate_does_not_bypass_staging_gate(tmp_path, monkeypatch):
    planned = configuration(tmp_path, environment="production")
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    driver.outputs["secret"]["arn"] = (
        "arn:aws:secretsmanager:eu-central-1:123456789012:secret:kira-production/log-cursor-123abc"
    )
    result = automation.deploy(planned, directory, driver, allow_model=True, ticket=tmp_path / "ticket")
    assert result["status"] == "WAITING" and "Production candidates provisioned" in result["next"]
    assert driver.canaries == 0 and "routing" not in result["completed_stages"]


def test_mid_run_configuration_change_rejected_before_render(tmp_path, monkeypatch):
    planned = configuration(tmp_path)
    driver = FakeDriver(planned, tmp_path / "work", monkeypatch)
    path = tmp_path / "runtime.json"
    config = json.loads(path.read_text())
    config["retention_days"] += 1
    path.write_text(json.dumps(config))
    with pytest.raises(VerificationError, match="changed during deployment"):
        driver.render({})


def test_reservation_reconciliation_waits_for_complete_stack(tmp_path, monkeypatch):
    planned = configuration(tmp_path)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    automation.deploy(planned, directory, driver)
    driver.inspect_stack = Mock(return_value={"StackStatus": "CREATE_IN_PROGRESS"})
    driver.template_matches = Mock(side_effect=AssertionError("No completed stack template yet"))
    result = automation.deploy(planned, directory, driver)
    assert result["status"] == "WAITING"
    driver.clients.assert_not_called()
    driver.template_matches.assert_not_called()


def test_operator_wrapper_binds_one_explicit_sdk_session(monkeypatch):
    from infra import operator

    setup = Mock()
    run = Mock()
    monkeypatch.setattr(operator.boto3, "setup_default_session", setup)
    monkeypatch.setattr(operator.runpy, "run_module", run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "operator",
            "--profile",
            "customer-sso",
            "--module",
            "infra.durable_ops",
            "--",
            "collect",
            "--bundle",
            ".local/customer/bundle",
        ],
    )
    operator.main()
    setup.assert_called_once_with(profile_name="customer-sso")
    run.assert_called_once_with("infra.durable_ops", run_name="__main__")
    assert __import__("sys").argv == ["infra.durable_ops", "collect", "--bundle", ".local/customer/bundle"]


# Pre-change stage lists of the opt-in identity plan (captured from the code before default mode existed).
IDENTITY_STAGES = {
    ("standalone", False): [
        "foundation-tools",
        "foundation-monitor",
        "durable-foundation",
        "identity-foundation",
        "identity-secret",
        "identity-foundation-bound",
        "owned-tools",
        "durable-runtime",
        "chat-runtime",
        "candidate-verification",
        "initial-access",
        "staging-canary",
        "routing",
        "registration-verification",
        "manual-acceptance",
    ],
    ("standalone", True): [
        "foundation-tools",
        "foundation-monitor",
        "durable-foundation",
        "identity-foundation",
        "identity-secret",
        "identity-foundation-bound",
        "owned-tools",
        "durable-runtime",
        "chat-runtime",
        "observation-foundation",
        "observation-runtime",
        "health-bootstrap",
        "candidate-verification",
        "initial-access",
        "staging-canary",
        "routing",
        "observations",
        "registration-verification",
        "manual-acceptance",
    ],
    ("agentcore", False): [
        "foundation-tools",
        "foundation-monitor",
        "durable-foundation",
        "identity-foundation",
        "identity-secret",
        "identity-foundation-bound",
        "owned-tools",
        "agentcore-runtime",
        "agentcore-endpoint",
        "agentcore-chat-runtime",
        "agentcore-chat-endpoint",
        "durable-runtime",
        "chat-runtime",
        "candidate-verification",
        "initial-access",
        "staging-canary",
        "routing",
        "registration-verification",
        "manual-acceptance",
    ],
    ("agentcore", True): [
        "foundation-tools",
        "foundation-monitor",
        "durable-foundation",
        "identity-foundation",
        "identity-secret",
        "identity-foundation-bound",
        "owned-tools",
        "agentcore-runtime",
        "agentcore-endpoint",
        "agentcore-chat-runtime",
        "agentcore-chat-endpoint",
        "durable-runtime",
        "chat-runtime",
        "observation-foundation",
        "observation-runtime",
        "health-bootstrap",
        "candidate-verification",
        "initial-access",
        "staging-canary",
        "routing",
        "observations",
        "registration-verification",
        "manual-acceptance",
    ],
}
IDENTITY_ONLY = {
    "identity-foundation",
    "identity-secret",
    "identity-foundation-bound",
    "chat-runtime",
    "agentcore-chat-runtime",
    "agentcore-chat-endpoint",
    "initial-access",
}


@pytest.mark.parametrize("target,observations", IDENTITY_STAGES)
def test_opt_in_identity_plan_stages_unchanged(tmp_path, target, observations):
    planned = configuration(tmp_path, target, observations)
    assert planned["stages"] == IDENTITY_STAGES[target, observations]
    assert "model-secret" not in planned["stages"]
    assert {"identity-foundation", "identity-secret"} <= set(planned["bootstrap_templates"])
    assert any("OIDC" in item for item in planned["manual"])


@pytest.mark.parametrize("target,observations", IDENTITY_STAGES)
def test_default_plan_drops_exactly_the_identity_stages(tmp_path, target, observations):
    planned = configuration(tmp_path, target, observations, identity=False)
    assert planned["stages"] == [s for s in IDENTITY_STAGES[target, observations] if s not in IDENTITY_ONLY]
    assert planned["initial_access"] == [] and "identity" not in planned["runtime_config"]
    assert not {"identity-foundation", "identity-secret"} & set(planned["bootstrap_templates"])
    assert not {"identity-foundation", "identity-secret"} & set(planned["resources"])
    assert not any("OIDC" in item for item in planned["manual"])
    assert "staging-canary" in planned["stages"] and "durable-runtime" in planned["stages"]


@pytest.mark.parametrize("target", ["standalone", "agentcore"])
@pytest.mark.parametrize("observations", [False, True])
def test_default_mode_reaches_canary_without_identity_or_ticket(tmp_path, monkeypatch, target, observations):
    (tmp_path / "identity").mkdir()
    reference = configuration(tmp_path / "identity", target, observations)
    ref_dir = tmp_path / "ref-work"
    ref_dir.mkdir()
    ref_driver = FakeDriver(reference, ref_dir, monkeypatch)
    automation.deploy(reference, ref_dir, ref_driver)
    ref = automation.deploy(reference, ref_dir, ref_driver, allow_model=True, ticket=tmp_path / "ticket")
    assert ref["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING"

    (tmp_path / "local").mkdir()
    planned = configuration(tmp_path / "local", target, observations, identity=False)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    result = automation.deploy(planned, directory, driver)
    assert result["status"] == "WAITING" and not result["auto_resume"]
    assert "--allow-model-invocation" in result["next"] and "OIDC" not in result["next"]
    assert "ticket" not in result["next"] and driver.canaries == 0
    result = automation.deploy(planned, directory, driver, allow_model=True)
    assert result["status"] == ref["status"] and driver.canaries == 1 and driver.canary_ticket is None
    assert result["completed_stages"] == [s for s in ref["completed_stages"] if s not in IDENTITY_ONLY]
    state = json.loads((directory / "state.json").read_text())
    assert "identity" not in state["bindings"] and "model_secret" not in state["bindings"]
    assert not any(
        c.startswith("identity") or "identity-foundation" in c or c.startswith("chat-runtime")
        for c in driver.calls
    )
    assert not any("chat" in c for c in driver.calls)
    connection = json.loads((directory / "ui-connection.json").read_text())
    assert set(connection) == {"environment", "ui_role_arn"}
    assert "KIRA_AUTH_MODE" not in connection["environment"]
    assert (
        automation.deploy(planned, directory, driver, allow_model=True)["status"] == ref["status"]
        and driver.canaries == 1
    )


def test_default_mode_paid_canary_retry_needs_authorization_not_ticket(tmp_path, monkeypatch):
    planned = configuration(tmp_path, identity=False)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    automation.deploy(planned, directory, driver)
    state = json.loads((directory / "state.json").read_text())
    state["canary_requested"] = True
    automation.private_json(directory / "state.json", state)
    with pytest.raises(VerificationError, match="authorization"):
        automation.deploy(planned, directory, driver, retry_canary=True)
    result = automation.deploy(planned, directory, driver, allow_model=True)
    assert result["status"] == "WAITING" and "ambiguous" in result["next"] and driver.canaries == 0
    result = automation.deploy(planned, directory, driver, allow_model=True, retry_canary=True)
    assert result["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING" and driver.canaries == 1


@pytest.mark.parametrize("identity_mode", [True, False])
def test_reserved_concurrency_counts_only_what_the_templates_reserve(tmp_path, monkeypatch, identity_mode):
    planned = configuration(tmp_path, identity=identity_mode)
    initial = planned["runtime_config"]["initial_reserved_concurrency"]
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    seen = []

    def check(plan, clients, **kw):
        seen.append(kw["remaining_reserved"])
        return {"status": "SIMULATED"}

    monkeypatch.setattr(deployment_preflight, "check", check)
    driver.preflight = None
    automation.deploy(planned, directory, driver)
    assert seen == [initial + (3 if identity_mode else 0)]
    # Resume: every reservation the plan makes is verified live and leaves nothing to reserve.
    names = {
        driver.outputs["versions"]["InitialVersionArn"].rsplit(":", 1)[0]: initial,
        driver.op(None, "collect", stage="chat-runtime")["ChatVersionArn"].rsplit(":", 1)[0]: 1,
    }
    if identity_mode:
        names[driver.outputs["versions"]["InvestigateVersionArn"].rsplit(":", 1)[0]] = 2
    lambda_client = Mock()
    lambda_client.get_function_concurrency.side_effect = lambda FunctionName: (
        {"ReservedConcurrentExecutions": names[FunctionName]} if FunctionName in names else {}
    )
    driver.clients = Mock(return_value=lambda_client)
    driver.inspect_stack = Mock(return_value={"StackStatus": "CREATE_COMPLETE"})
    driver.template_matches = Mock(return_value=True)
    driver.preflight = None
    automation.deploy(planned, directory, driver)
    assert seen[-1] == 0


@pytest.mark.parametrize("identity_mode", [True, False])
def test_preflight_capacity_follows_reservations_the_plan_makes(tmp_path, identity_mode):
    planned = configuration(tmp_path, identity=identity_mode)
    planned["spec"]["reference_only"] = False
    clients = preflight_factory(planned)
    # 103 unreserved leaves 3 reservable: the three identity functions' 5 do not fit, 2 do.
    clients["lambda"].get_account_settings.return_value["AccountLimit"]["UnreservedConcurrentExecutions"] = (
        103
    )
    if identity_mode:
        with pytest.raises(VerificationError, match="unreserved capacity"):
            deployment_preflight.check(planned, lambda service, region: clients[service])
    else:
        result = deployment_preflight.check(planned, lambda service, region: clients[service])
        assert result["status"] == "SIMULATED"


# model_api plans insert exactly one read-only secret-version stage; Bedrock plans do not.
@pytest.mark.parametrize("identity_mode", [True, False])
@pytest.mark.parametrize("target", ["standalone", "agentcore"])
def test_model_api_stage_order_pure(target, identity_mode):
    config = {"runtime_target": target, **({"identity": {}} if identity_mode else {})}
    for spec in ({}, {"model_provider": "bedrock"}):
        assert "model-secret" not in automation.stage_order(spec, config)
    stages = automation.stage_order({"model_provider": "model_api"}, config)
    assert stages.count("model-secret") == 1
    assert stages.index("durable-foundation") < stages.index("model-secret") < stages.index("owned-tools")
    assert [s for s in stages if s != "model-secret"] == automation.stage_order({}, config)


@pytest.mark.parametrize("identity_mode", [True, False])
def test_model_api_plan_and_resumable_secret_binding(tmp_path, monkeypatch, identity_mode):
    planned = configuration(tmp_path, identity=identity_mode, model_api=True)
    assert planned["stages"].count("model-secret") == 1
    assert "model-secret" not in planned["resources"]
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    ticket = tmp_path / "ticket" if identity_mode else None
    automation.deploy(planned, directory, driver)
    result = automation.deploy(planned, directory, driver, allow_model=True, ticket=ticket)
    assert result["status"] == "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING" and driver.canaries == 1
    state = json.loads((directory / "state.json").read_text())
    assert state["bindings"]["model_secret"] == driver.outputs["model_secret"]
    assert driver.calls.count("model-secret-version") == 1  # pinned once, never re-resolved on resume
    assert driver.calls.index("collect:durable-foundation") < driver.calls.index("model-secret-version")
    assert driver.calls.index("model-secret-version") < driver.calls.index("owned-tools")


def test_bedrock_deploy_never_resolves_a_model_secret(tmp_path, monkeypatch):
    planned = configuration(tmp_path)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    automation.deploy(planned, directory, driver)
    assert "model-secret-version" not in driver.calls
    assert "model_secret" not in json.loads((directory / "state.json").read_text())["bindings"]


@pytest.mark.parametrize("identity_mode", [True, False])
def test_missing_model_secret_fails_closed_before_any_runtime_or_model_call(
    tmp_path, monkeypatch, identity_mode
):
    planned = configuration(tmp_path, identity=identity_mode, model_api=True)
    directory = tmp_path / "work"
    directory.mkdir()
    driver = FakeDriver(planned, directory, monkeypatch)
    driver.missing_model_secret = True
    ticket = tmp_path / "ticket" if identity_mode else None
    with pytest.raises(VerificationError, match="Model API key secret"):
        automation.deploy(planned, directory, driver, allow_model=True, ticket=ticket)
    assert driver.calls[-1] == "model-secret-version" and driver.canaries == 0
    assert not {"owned-tools", "durable-runtime", "chat-runtime", "upload", "canary"} & set(driver.calls)
    state = json.loads((directory / "state.json").read_text())
    assert state["status"] == "FAILED" and "model_secret" not in state["bindings"]


def model_api_preflight(tmp_path, secret):
    planned = configuration(tmp_path, identity=False)
    planned["spec"]["reference_only"] = False
    planned["spec"].pop("model_arns")
    planned["spec"]["model_provider"] = "model_api"
    clients = preflight_factory(planned)
    clients["secretsmanager"] = Mock()
    if isinstance(secret, Exception):
        clients["secretsmanager"].describe_secret.side_effect = secret
    else:
        clients["secretsmanager"].describe_secret.return_value = secret
    return planned, clients


def test_model_api_preflight_checks_secret_by_name_not_catalog_or_value(tmp_path):
    secret = {"VersionIdsToStages": {"v1": ["AWSPREVIOUS"], "v2": ["AWSCURRENT"]}}
    planned, clients = model_api_preflight(tmp_path, secret)
    clients["bedrock"] = Mock(side_effect=AssertionError("Bedrock catalog does not apply"))
    result = deployment_preflight.check(planned, lambda service, region: clients[service])
    assert result["status"] == "SIMULATED"
    assert result["model_catalog_visible"] is None and result["model_secret_present"] is True
    assert any("not read" in item for item in result["limitations"])
    spec = planned["spec"]
    clients["secretsmanager"].describe_secret.assert_called_once_with(
        SecretId=prefix(spec) + "/model-api-key"
    )
    assert not clients["secretsmanager"].get_secret_value.called


@pytest.mark.parametrize("failure", ["absent", "no_current", "no_versions", "two_current", "denied"])
def test_model_api_preflight_secret_failures_block_before_simulation(tmp_path, failure):
    error = {
        "absent": ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"),
        "denied": ClientError({"Error": {"Code": "AccessDeniedException"}}, "DescribeSecret"),
        "no_current": {"VersionIdsToStages": {"v1": ["AWSPREVIOUS"]}},
        "no_versions": {},
        "two_current": {"VersionIdsToStages": {"v1": ["AWSCURRENT"], "v2": ["AWSCURRENT"]}},
    }[failure]
    planned, clients = model_api_preflight(tmp_path, error)
    expected = ClientError if failure == "denied" else VerificationError
    with pytest.raises(expected):
        deployment_preflight.check(planned, lambda service, region: clients[service])
    clients["iam"].simulate_principal_policy.assert_not_called()


def test_bedrock_preflight_report_keys_unchanged(tmp_path):
    planned = configuration(tmp_path)
    planned["spec"]["reference_only"] = False
    clients = preflight_factory(planned)
    result = deployment_preflight.check(planned, lambda service, region: clients[service])
    assert result["model_catalog_visible"] is True and "model_secret_present" not in result
    assert not any("secret" in item for item in result["limitations"])


def run_main(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["automation", *map(str, argv)])
    return automation.main()


@pytest.mark.parametrize("flag", [None, "--identity"])
def test_init_copies_default_or_identity_runtime_and_plans(tmp_path, monkeypatch, capsys, flag):
    monkeypatch.setattr(automation, "private_dir", lambda path: path)
    assert run_main(monkeypatch, "init", "--work-dir", tmp_path, *([flag] if flag else [])) == 0
    source = "identity" if flag else "durable"
    assert (tmp_path / "runtime.json").read_bytes() == (ROOT / f"examples/{source}.example.json").read_bytes()
    assert (tmp_path / "runtime.json").stat().st_mode & 0o777 == 0o600
    assert json.loads((tmp_path / "automation.json").read_text())["initial_access"] == []
    assert "docs/DEPLOY.md" in capsys.readouterr().out
    assert (
        run_main(monkeypatch, "dry-run", "--config", tmp_path / "automation.json", "--work-dir", tmp_path)
        == 0
    )
    stages = json.loads(capsys.readouterr().out)["stages"]
    assert ("identity-foundation-bound" in stages) == bool(flag) and "staging-canary" in stages
    assert ("initial-access" in stages) == bool(flag)
    # Init never overwrites what the customer already filled in.
    assert run_main(monkeypatch, "init", "--work-dir", tmp_path) == 1


def test_identity_flag_belongs_to_init_only(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "private_dir", lambda path: path)
    with pytest.raises(SystemExit):
        run_main(
            monkeypatch,
            "dry-run",
            "--identity",
            "--config",
            tmp_path / "automation.json",
            "--work-dir",
            tmp_path,
        )


@pytest.mark.parametrize(
    "identity_mode,flags,accepted",
    [
        (False, ["--allow-model-invocation"], True),
        (False, ["--allow-model-invocation", "--retry-canary"], True),
        (False, ["--allow-model-invocation", "--access-ticket-file", "TICKET"], False),
        (True, ["--allow-model-invocation", "--access-ticket-file", "TICKET"], True),
        (True, ["--allow-model-invocation", "--retry-canary", "--access-ticket-file", "TICKET"], True),
        (True, ["--allow-model-invocation", "--retry-canary"], False),
    ],
)
def test_ticket_options_exist_only_with_identity(
    tmp_path, monkeypatch, capsys, identity_mode, flags, accepted
):
    monkeypatch.setattr(automation, "private_dir", lambda path: path)
    planned = configuration(tmp_path, identity=identity_mode)
    planned["spec"]["reference_only"] = False
    ticket = tmp_path / "ticket"
    ticket.write_text("synthetic")
    ticket.chmod(0o600)
    tmp_path.chmod(0o700)
    monkeypatch.setattr(automation, "plan", lambda path: planned)
    monkeypatch.setattr(automation.subprocess, "check_output", lambda *a, **kw: "")
    driver = Mock()
    monkeypatch.setattr(automation, "Driver", driver)
    deploy = Mock(
        return_value={"status": "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING", "auto_resume": False}
    )
    monkeypatch.setattr(automation, "deploy", deploy)
    argv = ["apply", "--config", tmp_path / "automation.json", "--work-dir", tmp_path]
    argv += ["--plan-hash", planned["plan_hash"], *[ticket if f == "TICKET" else f for f in flags]]
    assert run_main(monkeypatch, *argv) == (0 if accepted else 1)
    assert deploy.called is accepted and driver.called is accepted
    if not accepted:
        assert "ticket" in capsys.readouterr().err
    else:
        assert deploy.call_args.kwargs["ticket"] == (ticket if "TICKET" in flags else None)


def launcher_connection(tmp_path, **extra):
    from scripts.run_customer_ui import environment

    path = tmp_path / "ui.json"
    automation.private_json(
        path,
        {
            "environment": {
                "EXPECTED_ACCOUNT_ID": "123456789012",
                "MONITOR_REGION": "eu-central-1",
                "ENVIRONMENT": "staging",
                **extra,
            },
            "ui_role_arn": "arn:aws:iam::123456789012:role/kira/staging/ui",
        },
    )
    session = Mock()
    session.return_value.client.return_value.get_caller_identity.return_value = {
        "Account": "123456789012",
        "Arn": "arn:aws:sts::123456789012:assumed-role/ui/private-session",
    }
    return lambda: environment(path, "customer-ui", session_factory=session)


@pytest.mark.parametrize("mode", [None, "oidc"])
def test_launcher_keeps_operator_password_only_outside_identity_mode(tmp_path, monkeypatch, mode):
    for key in (
        "APP_PASSWORD",
        "KIRA_IDENTITY_HEADER",
        "KIRA_SESSION_SIGNING_KEY",
        "KIRA_STAGING_TICKET_FILE",
    ):
        monkeypatch.setenv(key, "x" * 16)
    model = json.dumps({"protocol": "openai", "base_url": "https://models.example.invalid/v1"})
    result = launcher_connection(tmp_path, MODEL_API=model, **({"KIRA_AUTH_MODE": mode} if mode else {}))()
    assert ("APP_PASSWORD" in result) == (mode is None)
    assert (
        not {"KIRA_IDENTITY_HEADER", "KIRA_SESSION_SIGNING_KEY", "KIRA_STAGING_TICKET_FILE"} & result.keys()
    )
    assert result["MODEL_API"] == model  # connection values pass straight through, no allowlist


@pytest.mark.parametrize(
    "mode,password,hint", [(None, False, True), (None, True, False), ("oidc", False, False)]
)
def test_launcher_hints_when_default_mode_has_no_password(
    tmp_path, monkeypatch, capsys, mode, password, hint
):
    from scripts import run_customer_ui

    monkeypatch.delenv("APP_PASSWORD", raising=False)
    if password:
        monkeypatch.setenv("APP_PASSWORD", "x" * 16)
    build = launcher_connection(tmp_path, **({"KIRA_AUTH_MODE": mode} if mode else {}))
    monkeypatch.setattr(run_customer_ui, "environment", lambda path, profile: build())
    execve = Mock()
    monkeypatch.setattr(run_customer_ui.os, "execve", execve)
    monkeypatch.setattr(run_customer_ui.os, "chdir", Mock())
    monkeypatch.setattr(
        "sys.argv", ["run_customer_ui", "--connection", str(tmp_path / "ui.json"), "--profile", "customer-ui"]
    )
    run_customer_ui.main()
    execve.assert_called_once()
    assert ("APP_PASSWORD" in capsys.readouterr().err) is hint


def run_model_secret_op(tmp_path, monkeypatch, secret, *, provider="model_api"):
    from infra import durable_ops

    planned = configuration(tmp_path, identity=False, model_api=provider == "model_api")
    spec = {**planned["spec"], "reference_only": False}
    secretsmanager = Mock()
    secretsmanager.describe_secret.return_value = secret(spec) if callable(secret) else secret
    sts_and_sm = Mock(side_effect=lambda service, region: secretsmanager)
    monkeypatch.setattr(durable_ops, "read_bundle", lambda path, review_hash: {"spec": spec})
    monkeypatch.setattr(durable_ops, "assert_account", Mock())
    monkeypatch.setattr(durable_ops, "clients", sts_and_sm)
    output = tmp_path / "out.json"
    monkeypatch.setattr(
        "sys.argv",
        ["durable_ops", "model-secret-version", "--bundle", str(tmp_path), "--review-hash", "h"]
        + ["--output", str(output)],
    )
    return durable_ops.main(), output, secretsmanager, spec


def model_secret(spec, versions=None, **extra):
    return {
        "Name": prefix(spec) + "/model-api-key",
        "ARN": f"arn:aws:secretsmanager:{spec['bedrock_region']}:{spec['account_id']}:secret:{prefix(spec)}/model-api-key-123abc",
        "VersionIdsToStages": versions or {"a" * 32: ["AWSPREVIOUS"], "b" * 32: ["AWSCURRENT"]},
        **extra,
    }


def test_model_secret_version_op_pins_the_single_current_version_without_reading_the_value(
    tmp_path, monkeypatch
):
    rc, output, secretsmanager, spec = run_model_secret_op(tmp_path, monkeypatch, model_secret)
    assert rc == 0
    assert json.loads(output.read_text()) == {
        "arn": model_secret(spec)["ARN"],
        "version_id": "b" * 32,
    }
    secretsmanager.describe_secret.assert_called_once_with(SecretId=prefix(spec) + "/model-api-key")
    assert not secretsmanager.get_secret_value.called


@pytest.mark.parametrize(
    "mutation",
    [
        lambda spec: model_secret(spec, {"a" * 32: ["AWSPREVIOUS"]}),
        lambda spec: model_secret(spec, {"a" * 32: ["AWSCURRENT"], "b" * 32: ["AWSCURRENT"]}),
        lambda spec: model_secret(spec, Name="kira-staging/other"),
    ],
    ids=["no_current", "two_current", "other_secret"],
)
def test_model_secret_version_op_rejects_ambiguous_or_foreign_secrets(tmp_path, monkeypatch, mutation):
    rc, output, secretsmanager, _ = run_model_secret_op(tmp_path, monkeypatch, mutation)
    assert rc == 1 and not output.exists() and secretsmanager.describe_secret.called


def test_model_secret_version_op_is_model_api_only(tmp_path, monkeypatch):
    rc, output, secretsmanager, _ = run_model_secret_op(
        tmp_path, monkeypatch, model_secret, provider="bedrock"
    )
    assert rc == 1 and not output.exists() and not secretsmanager.describe_secret.called


def test_model_api_requires_standalone_runtime(tmp_path):
    with pytest.raises(VerificationError, match="standalone"):
        configuration(tmp_path, "agentcore", model_api=True)
