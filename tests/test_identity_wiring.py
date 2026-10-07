import copy
import json
from unittest.mock import Mock

import pytest

from infra import durable, durable_ops, owned_ops, owned_runtime
from infra import identity as infrastructure
from infra.spec import ROOT, load, name
from infra.verify import VerificationError
from kira import identity
from scripts.validate_durable import examples

SPEC = load(ROOT / "infra/deployment.example.json")
BASE = json.loads((ROOT / "infra/durable.example.json").read_text())
CONFIG = {**BASE, "identity": {"issuer": "https://identity.example.invalid", "audience": "customer-ui"}}
SECRET = {
    "SigningSecretArn": f"arn:aws:secretsmanager:{SPEC['bedrock_region']}:{SPEC['account_id']}:secret:{infrastructure.secret_name(SPEC)}-123abc",
    "SigningSecretVersion": "a" * 32,
}


def bindings(spec=SPEC, target="standalone"):
    config = {**BASE, "runtime_target": target}
    _, data, _, versions = examples(spec, config, include_bindings=True)
    data["versions"] = versions
    data["identity"] = {
        **SECRET,
        "SigningSecretArn": SECRET["SigningSecretArn"].replace(
            SPEC["bedrock_region"], spec["bedrock_region"]
        ),
    }
    from infra.chat import fixture_bindings

    fixture_bindings(spec, data)
    return data


@pytest.mark.parametrize(
    "issuer",
    [
        "http://insecure.invalid",
        "https://user:password@example.invalid",
        "https://example.invalid/?query=1",
        "https://example.invalid/#fragment",
        "https://example.invalid:4566",
        "https://",
    ],
)
def test_invalid_identity_metadata_rejected(issuer):
    with pytest.raises(VerificationError):
        infrastructure.validate_config({"issuer": issuer, "audience": "client"})


@pytest.mark.parametrize("target", ["standalone", "agentcore"])
def test_environment_propagates_security_to_both_targets(target):
    config = {**CONFIG, "runtime_target": target}
    data = bindings(target=target)
    env = owned_runtime.environment(SPEC, config, data)
    assert env["ENVIRONMENT"] == "staging" and env["KIRA_AUTH_MODE"] == "oidc"
    assert env["KIRA_SESSION_KEY_ARN"] == SECRET["SigningSecretArn"]
    assert env["KIRA_SESSION_KEY_VERSION"] == SECRET["SigningSecretVersion"]
    policy = json.loads(env["KIRA_ACCESS_POLICY_JSON"])
    assert policy["binding"] == [SPEC["environment"], SPEC["account_id"], env["RUNTIME_RELEASE"]]
    assert "KIRA_SESSION_SIGNING_KEY" not in env and "KIRA_ACCESS_POLICY_FILE" not in env


def test_agentcore_always_has_deployment_environment_even_without_identity_config():
    data = bindings(target="agentcore")
    stages = examples(SPEC, {**BASE, "runtime_target": "agentcore"})
    assert (
        stages["agentcore-runtime"]["Resources"]["Runtime"]["Properties"]["EnvironmentVariables"][
            "ENVIRONMENT"
        ]
        == "staging"
    )
    assert owned_runtime.caller_environment(SPEC, BASE, data)["ENVIRONMENT"] == "staging"


@pytest.mark.parametrize(
    "field,value",
    [
        ("SigningSecretVersion", "AWSCURRENT"),
        ("SigningSecretVersion", ""),
        ("SigningSecretArn", SECRET["SigningSecretArn"].replace(SPEC["account_id"], "999999999999")),
    ],
)
def test_foreign_or_mutable_secret_binding_denied(field, value):
    data = {"identity": {**SECRET, field: value}}
    with pytest.raises(VerificationError):
        infrastructure.permissions(SPEC, data, issuer=True)


def test_workloads_cannot_write_identity_grants_or_scan_session_table():
    for issuer in (True, False):
        policies = infrastructure.permissions(SPEC, {"identity": SECRET}, issuer=issuer)
        for policy in policies:
            actions = policy["Action"]
            actions = [actions] if isinstance(actions, str) else actions
            assert "dynamodb:Scan" not in actions and "dynamodb:Query" not in actions
            if any(a in actions for a in ["dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:UpdateItem"]):
                assert policy["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] in (
                    ["SESSION#*"],
                    ["AUDIT#*"],
                    ["QUOTA#login#*"],
                )
            if policy["Action"] == "secretsmanager:GetSecretValue":
                assert policy["Resource"] == SECRET["SigningSecretArn"]
                assert policy["Condition"] == {
                    "StringEquals": {"secretsmanager:VersionId": SECRET["SigningSecretVersion"]}
                }
        if not issuer:
            assert "dynamodb:DeleteItem" not in json.dumps(policies)
            assert [
                p["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"]
                for p in policies
                if p["Action"] == "dynamodb:PutItem"
            ] == [["AUDIT#*"]]


def test_identity_foundations_are_encrypted_retained_and_separate_from_incident_stream():
    table = infrastructure.foundation(SPEC)["Resources"]["Sessions"]
    props = table["Properties"]
    assert props["SSESpecification"] == {"SSEEnabled": True, "SSEType": "KMS"}
    assert props["TimeToLiveSpecification"] == {"AttributeName": "ttl", "Enabled": True}
    assert (
        props["DeletionProtectionEnabled"]
        and props["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"]
    )
    assert "StreamSpecification" not in props
    assert props["TableName"] != name(SPEC, "incidents") and table["DeletionPolicy"] == "Retain"
    secret = infrastructure.signing_secret(SPEC)["Resources"]["SigningSecret"]["Properties"]
    assert secret["GenerateSecretString"]["PasswordLength"] >= 32 and "SecretString" not in secret


def test_identity_metadata_and_key_version_change_release_fingerprint():
    data = bindings()
    original = owned_runtime.fingerprint(SPEC, CONFIG, data)
    other = copy.deepcopy(CONFIG)
    other["identity"]["audience"] = "other-ui"
    assert original != owned_runtime.fingerprint(SPEC, other, data)
    data["identity"]["SigningSecretVersion"] = "b" * 32
    assert original != owned_runtime.fingerprint(SPEC, CONFIG, data)


def test_identity_config_can_render_foundations_before_secret_bindings(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    bundle = durable.render(ROOT / "infra/deployment.example.json", path, tmp_path / "plan")
    for stage in ["identity-foundation", "identity-secret"]:
        assert stage in bundle["stages"] and stage in durable_ops.STAGES
        assert bundle["stages"][stage]["region"] == durable_ops.stage_region(SPEC, stage)
    durable_ops.read_bundle(tmp_path / "plan", bundle["review_hash"])


def test_inline_identity_policy_is_bound_and_conflicting_file_is_denied(monkeypatch):
    release = "b" * 64
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("EXPECTED_ACCOUNT_ID", SPEC["account_id"])
    monkeypatch.setenv("RUNTIME_RELEASE", release)
    monkeypatch.delenv("KIRA_ACCESS_POLICY_FILE", raising=False)
    env = infrastructure.environment(SPEC, CONFIG, {"identity": SECRET}, release)
    monkeypatch.setenv("KIRA_ACCESS_POLICY_JSON", env["KIRA_ACCESS_POLICY_JSON"])
    assert identity.Sessions().policy()["audience"] == "customer-ui"
    monkeypatch.setenv("KIRA_ACCESS_POLICY_FILE", "untrusted-file")
    with pytest.raises(identity.AccessDenied):
        identity.Sessions().policy()


def test_pinned_secret_read_uses_exact_version_and_never_falls_back_to_current(monkeypatch):
    identity.signing_key.cache_clear()
    client = Mock()
    client.get_secret_value.return_value = {
        "ARN": SECRET["SigningSecretArn"],
        "VersionId": SECRET["SigningSecretVersion"],
        "SecretString": "fixture-" * 8,
    }
    factory = Mock(return_value=client)
    monkeypatch.setattr(identity.boto3, "client", factory)
    assert identity.signing_key(SECRET["SigningSecretArn"], SECRET["SigningSecretVersion"], 1)
    identity.signing_key(SECRET["SigningSecretArn"], SECRET["SigningSecretVersion"], 1)
    assert client.get_secret_value.call_count == 1
    client.get_secret_value.assert_called_with(
        SecretId=SECRET["SigningSecretArn"], VersionId=SECRET["SigningSecretVersion"]
    )
    identity.signing_key(SECRET["SigningSecretArn"], SECRET["SigningSecretVersion"], 2)
    assert client.get_secret_value.call_count == 2
    identity.signing_key.cache_clear()


def test_wrong_secret_response_version_is_not_cached(monkeypatch):
    identity.signing_key.cache_clear()
    client = Mock()
    client.get_secret_value.return_value = {
        "ARN": SECRET["SigningSecretArn"],
        "VersionId": "b" * 32,
        "SecretString": "fixture-" * 8,
    }
    monkeypatch.setattr(identity.boto3, "client", lambda *a, **kw: client)
    for _ in range(2):
        with pytest.raises(identity.AccessDenied):
            identity.signing_key(SECRET["SigningSecretArn"], SECRET["SigningSecretVersion"], 1)
    assert client.get_secret_value.call_count == 2


def test_chat_canary_cannot_bypass_identity_even_with_paid_authorization():
    factory = Mock()
    with pytest.raises(VerificationError, match="individual-session"):
        owned_ops.canary({"spec": {"environment": "staging"}}, factory, allow_model_invocation=True)
    factory.assert_not_called()


@pytest.fixture
def foundation_clients():
    from infra.spec import tags
    from infra.templates import template_hash

    templates = {
        "identity-foundation": infrastructure.foundation(SPEC, {"identity": SECRET}),
        "identity-secret": infrastructure.signing_secret(SPEC),
    }
    cloud = Mock()
    cloud.describe_stacks.side_effect = lambda StackName: {
        "Stacks": [
            {
                "StackId": StackName,
                "StackStatus": "CREATE_COMPLETE",
                "Tags": [{"Key": k, "Value": v} for k, v in tags(SPEC).items()],
                "Outputs": [
                    {
                        "OutputKey": "SessionIssuerRoleArn",
                        "OutputValue": f"arn:aws:iam::{SPEC['account_id']}:role/{SPEC['project']}/{SPEC['environment']}/Issuer",
                    }
                ],
            }
        ]
    }
    cloud.get_template.side_effect = lambda StackName: {
        "TemplateBody": templates[
            "identity-secret" if StackName.endswith("identity-secret") else "identity-foundation"
        ]
    }
    ddb, secret = Mock(), Mock()
    table = {
        "AttributeDefinitions": [{"AttributeName": k, "AttributeType": "S"} for k in ("PK", "SK")],
        "TableName": infrastructure.table_name(SPEC),
        "TableArn": infrastructure.table_arn(SPEC),
        "TableStatus": "ACTIVE",
        "DeletionProtectionEnabled": True,
        "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
        "SSEDescription": {"Status": "ENABLED", "SSEType": "KMS"},
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
    }
    ddb.describe_table.return_value = {"Table": table}
    ddb.describe_time_to_live.return_value = {
        "TimeToLiveDescription": {"AttributeName": "ttl", "TimeToLiveStatus": "ENABLED"}
    }
    ddb.describe_continuous_backups.return_value = {
        "ContinuousBackupsDescription": {
            "PointInTimeRecoveryDescription": {"PointInTimeRecoveryStatus": "ENABLED"}
        }
    }
    secret.describe_secret.return_value = {
        "ARN": SECRET["SigningSecretArn"],
        "Name": infrastructure.secret_name(SPEC),
        "VersionIdsToStages": {
            SECRET["SigningSecretVersion"]: ["AWSCURRENT", "kira-identity-" + SPEC["release_id"]]
        },
    }

    iam = Mock()
    planned_role = templates["identity-foundation"]["Resources"]["SessionIssuerRole"]["Properties"]
    iam.get_role.return_value = {
        "Role": {
            "Arn": f"arn:aws:iam::{SPEC['account_id']}:role/{SPEC['project']}/{SPEC['environment']}/Issuer",
            "Path": planned_role["Path"],
            "AssumeRolePolicyDocument": planned_role["AssumeRolePolicyDocument"],
        }
    }
    iam.list_role_policies.return_value = {"PolicyNames": ["runtime"]}
    iam.list_attached_role_policies.return_value = {"AttachedPolicies": []}
    iam.get_role_policy.return_value = {"PolicyDocument": planned_role["Policies"][0]["PolicyDocument"]}

    def factory(service, region):
        return {"cloudformation": cloud, "dynamodb": ddb, "secretsmanager": secret, "iam": iam}[service]

    bundle = {
        "spec": SPEC,
        "config": CONFIG,
        "bindings": {"identity": SECRET},
        "stages": {k: {"template_hash": template_hash(v)} for k, v in templates.items()},
    }
    return bundle, factory, ddb, secret, table


def test_live_foundation_verifier_checks_configuration_without_reading_secrets(foundation_clients):
    bundle, factory, ddb, secret, _ = foundation_clients
    infrastructure.verify_foundations(bundle, factory)
    ddb.describe_time_to_live.assert_called_once()
    secret.get_secret_value.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("TableStatus", "CREATING"),
        ("DeletionProtectionEnabled", False),
        ("SSEDescription", {"Status": "DISABLED", "SSEType": "KMS"}),
        ("GlobalSecondaryIndexes", [{"IndexName": "unexpected"}]),
        ("StreamSpecification", {"StreamEnabled": True}),
        ("KeySchema", []),
        ("TableArn", "arn:aws:dynamodb:us-east-1:999999999999:table/other"),
        ("AttributeDefinitions", [{"AttributeName": "PK", "AttributeType": "N"}]),
    ],
)
def test_identity_table_drift_is_denied(foundation_clients, field, value):
    bundle, factory, _, _, table = foundation_clients
    table[field] = value
    with pytest.raises(VerificationError, match="Identity table"):
        infrastructure.verify_foundations(bundle, factory)


def test_disabled_ttl_is_rejected_by_foundation_verifier(foundation_clients):
    bundle, factory, ddb, _, _ = foundation_clients
    ddb.describe_time_to_live.return_value["TimeToLiveDescription"]["TimeToLiveStatus"] = "DISABLED"
    with pytest.raises(VerificationError):
        infrastructure.verify_foundations(bundle, factory)


def test_unpinned_or_deleted_secret_is_rejected_by_foundation_verifier(foundation_clients):
    bundle, factory, _, secret, _ = foundation_clients
    secret.describe_secret.return_value["DeletedDate"] = "fixture-date"
    with pytest.raises(VerificationError, match="signing-secret"):
        infrastructure.verify_foundations(bundle, factory)


def test_release_label_required_for_qualification_but_not_initial_pin(foundation_clients):
    bundle, factory, _, secret, _ = foundation_clients
    secret.describe_secret.return_value["VersionIdsToStages"][SECRET["SigningSecretVersion"]] = ["AWSCURRENT"]
    with pytest.raises(VerificationError, match="signing-secret"):
        infrastructure.verify_foundations(bundle, factory)
    infrastructure.verify_foundations(bundle, factory, require_label=False)


def test_issuer_role_cannot_invoke_models_tools_or_fetch_reports():
    role = infrastructure.foundation(SPEC, {"identity": SECRET})["Resources"]["SessionIssuerRole"][
        "Properties"
    ]
    policy = json.dumps(role["Policies"])
    assert all(a not in policy for a in ("bedrock:", "bedrock-agentcore:", "lambda:", "s3:", "kms:"))
    assert role["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {"AWS": SPEC["ui_principal_arn"]}


@pytest.mark.parametrize("drift", ["arn", "trust", "extra-policy"])
def test_actual_session_issuer_role_drift_is_rejected(foundation_clients, drift):
    bundle, factory, _, _, _ = foundation_clients
    iam = factory("iam", SPEC["monitor_region"])
    if drift == "arn":
        iam.get_role.return_value["Role"]["Arn"] = "arn:aws:iam::999999999999:role/forged"
    elif drift == "trust":
        iam.get_role.return_value["Role"]["AssumeRolePolicyDocument"] = {"Statement": []}
    else:
        iam.list_attached_role_policies.return_value = {
            "AttachedPolicies": [{"PolicyName": "AdministratorAccess"}]
        }
    with pytest.raises(VerificationError):
        infrastructure.verify_foundations(bundle, factory)


def test_post_promotion_ui_role_trust_and_grants_are_verified(monkeypatch):
    from infra import durable_templates

    data = bindings()
    planned = durable_templates.active_routing(
        SPEC,
        data["versions"]["InvestigateVersionArn"],
        "",
        "",
        data["foundation"],
        data["versions"],
        config=CONFIG,
        owned_bindings=data,
    )["Resources"]["UiRole"]["Properties"]
    arn = f"arn:aws:iam::{SPEC['account_id']}:role/{SPEC['project']}/{SPEC['environment']}/Ui"
    iam = Mock()
    iam.get_role.return_value = {
        "Role": {
            "Arn": arn,
            "Path": planned["Path"],
            "AssumeRolePolicyDocument": planned["AssumeRolePolicyDocument"],
        }
    }
    iam.list_role_policies.return_value = {"PolicyNames": ["runtime"]}
    iam.list_attached_role_policies.return_value = {"AttachedPolicies": []}
    iam.get_role_policy.return_value = {
        "PolicyDocument": copy.deepcopy(planned["Policies"][0]["PolicyDocument"])
    }
    monkeypatch.setattr(
        durable_ops,
        "owned_stack",
        lambda *a, **kw: (None, {"Outputs": [{"OutputKey": "UiRoleArn", "OutputValue": arn}]}),
    )
    bundle = {"spec": SPEC, "config": CONFIG, "bindings": data}
    infrastructure.verify_ui_role(bundle, lambda *a: iam)
    iam.get_role_policy.return_value["PolicyDocument"]["Statement"].append(
        {"Effect": "Allow", "Action": "dynamodb:PutItem", "Resource": "*"}
    )
    with pytest.raises(VerificationError, match="grants differ"):
        infrastructure.verify_ui_role(bundle, lambda *a: iam)


def test_oversized_identity_runtime_configuration_is_rejected_before_deployment():
    from infra import durable_templates

    spec = {**SPEC, "model_id": "x" * 3500}
    data = bindings()
    _, _, artifacts, _ = examples(SPEC, BASE, include_bindings=True)
    with pytest.raises(VerificationError, match="4 KiB"):
        durable_templates.runtime(spec, CONFIG, artifacts, data["foundation"], owned_bindings=data)
