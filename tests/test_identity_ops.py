import copy
import json
from decimal import Decimal
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from infra import identity_ops as ops
from infra.verify import VerificationError
from tests.test_identity_wiring import CONFIG, SECRET, SPEC, bindings

REQUEST = {
    "subject": "synthetic-private-subject",
    "enabled": True,
    "role": "investigator",
    "instance_ids": [SPEC["instances"][0]["id"]],
}


@pytest.fixture
def administration(monkeypatch):
    bundle = {
        "spec": {**SPEC, "reference_only": False},
        "config": CONFIG,
        "bindings": bindings(),
        "review_hash": "reviewed-offline-fixture",
    }
    monkeypatch.setattr(ops.durable_ops, "require_reviewed_source", lambda b: None)
    monkeypatch.setattr(ops.identity, "verify_foundations", Mock())
    monkeypatch.setattr(ops, "assert_account", lambda c, s: None)
    ddb, secret = Mock(), Mock()
    ddb.get_item.return_value = {}
    secret.describe_secret.return_value = {
        "VersionIdsToStages": {SECRET["SigningSecretVersion"]: ["AWSCURRENT"]}
    }

    def factory(service, region):
        return {"dynamodb": ddb, "secretsmanager": secret, "sts": Mock()}[service]

    return bundle, factory, ddb, secret


def test_grant_diff_omits_private_subject_and_binds_authoritative_permissions(administration):
    bundle, factory, ddb, _ = administration
    plan = ops.plan_grant(bundle, REQUEST, factory)
    assert REQUEST["subject"] not in json.dumps(plan)
    assert plan["before"] is None and plan["after"]["epoch"] == 1
    assert plan["after"]["binding"][:2] == [SPEC["environment"], SPEC["account_id"]]
    assert plan["after"]["role"] == "investigator"
    assert ddb.get_item.call_args.kwargs["ConsistentRead"] is True
    assert ddb.put_item.call_count == 0


def test_new_grant_apply_is_conditional_and_exact(administration):
    bundle, factory, ddb, _ = administration
    plan = ops.plan_grant(bundle, REQUEST, factory)
    result = ops.apply_grant(bundle, REQUEST, plan, factory)
    assert result["status"] == "APPLIED" and result["epoch"] == 1
    kwargs = ddb.put_item.call_args.kwargs
    assert kwargs["ConditionExpression"] == "attribute_not_exists(PK)"
    assert kwargs["Item"] == ops.pack(plan["after"])


def test_disable_preserves_tombstone_epoch_and_compares_all_authorization_fields(administration):
    bundle, factory, ddb, _ = administration
    prior = ops.change(bundle, REQUEST, None)["after"]
    prior["epoch"] = Decimal(7)
    ddb.get_item.return_value = {"Item": ops.pack(prior)}
    request = {**REQUEST, "enabled": False}
    plan = ops.plan_grant(bundle, request, factory)
    ops.apply_grant(bundle, request, plan, factory)
    kwargs = ddb.put_item.call_args.kwargs
    assert kwargs["Item"]["epoch"] == {"N": "8"} and kwargs["Item"]["enabled"] == {"BOOL": False}
    assert set(kwargs["ExpressionAttributeNames"].values()) == set(ops.FIELDS)
    assert "attribute_not_exists" not in kwargs["ConditionExpression"]
    assert ddb.delete_item.call_count == 0


def test_changed_access_review_is_rejected_before_write(administration):
    bundle, factory, ddb, _ = administration
    plan = ops.plan_grant(bundle, REQUEST, factory)
    plan["after"]["role"] = "viewer"
    with pytest.raises(VerificationError, match="diff changed"):
        ops.apply_grant(bundle, REQUEST, plan, factory)
    ddb.put_item.assert_not_called()


def test_concurrent_grant_writer_is_not_overwritten(administration):
    bundle, factory, ddb, _ = administration
    prior = ops.change(bundle, REQUEST, None)["after"]
    ddb.get_item.return_value = {"Item": ops.pack(prior)}
    plan = ops.plan_grant(bundle, REQUEST, factory)
    ddb.put_item.side_effect = ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
    with pytest.raises(ClientError):
        ops.apply_grant(bundle, REQUEST, plan, factory)
    assert ddb.put_item.call_count == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"subject": ""},
        {"enabled": "true"},
        {"role": "admin"},
        {"instance_ids": ["i-fffffffffffffffff"]},
        {"instance_ids": []},
        {"role_from_prompt": "investigator"},
    ],
)
def test_bad_or_cross_scope_access_request_denied_before_aws(administration, patch):
    bundle, _, _, _ = administration
    factory = Mock()
    with pytest.raises(VerificationError):
        ops.plan_grant(bundle, {**REQUEST, **patch}, factory)
    factory.assert_not_called()


@pytest.mark.parametrize("epoch", [0, True, Decimal("1.5"), 2**53])
def test_malformed_or_exhausted_epoch_cannot_reset_to_one(administration, epoch):
    bundle, _, _, _ = administration
    prior = ops.change(bundle, REQUEST, None)["after"]
    prior["epoch"] = epoch
    with pytest.raises(VerificationError):
        ops.change(bundle, REQUEST, prior)


def test_key_pin_attaches_release_label_without_reading_key(administration):
    bundle, factory, _, secret = administration
    result = ops.pin_secret(bundle, factory)
    secret.update_secret_version_stage.assert_called_once_with(
        SecretId=SECRET["SigningSecretArn"],
        VersionStage=ops.version_label(SPEC),
        MoveToVersionId=SECRET["SigningSecretVersion"],
    )
    secret.get_secret_value.assert_not_called()
    assert result["status"] == "PINNED"


def test_existing_label_is_idempotent_and_cannot_be_retargeted(administration):
    bundle, factory, _, secret = administration
    secret.describe_secret.return_value["VersionIdsToStages"][SECRET["SigningSecretVersion"]].append(
        ops.version_label(SPEC)
    )
    ops.pin_secret(bundle, factory)
    secret.update_secret_version_stage.assert_not_called()
    secret.describe_secret.return_value["VersionIdsToStages"] = {"b" * 32: [ops.version_label(SPEC)]}
    with pytest.raises(VerificationError, match="another version"):
        ops.pin_secret(bundle, factory)
    secret.update_secret_version_stage.assert_not_called()


@pytest.mark.parametrize("operation", ["plan", "apply", "pin"])
def test_reference_administration_never_constructs_aws_client(administration, operation):
    bundle, _, _, _ = administration
    bundle = copy.deepcopy(bundle)
    bundle["spec"]["reference_only"] = True
    factory = Mock()
    with pytest.raises(VerificationError):
        if operation == "pin":
            ops.pin_secret(bundle, factory)
        elif operation == "apply":
            ops.apply_grant(bundle, REQUEST, {}, factory)
        else:
            ops.plan_grant(bundle, REQUEST, factory)
    factory.assert_not_called()


def test_dirty_source_cannot_apply_access_changes(administration, monkeypatch):
    bundle, _, _, _ = administration

    def reject(bundle):
        raise VerificationError("dirty")

    monkeypatch.setattr(ops.durable_ops, "require_reviewed_source", reject)
    factory = Mock()
    with pytest.raises(VerificationError, match="dirty"):
        ops.apply_grant(bundle, REQUEST, {}, factory)
    factory.assert_not_called()
