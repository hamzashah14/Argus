"""Customer access administration: reviewed grant diffs and immutable key labels.

No workload can write grants. This CLI uses a separately authorized operator,
never browser claims. Synthetic reference bundles are rejected before AWS calls.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError

from infra import durable_ops, identity, owned_runtime
from infra.aws import clients
from infra.spec import digest
from infra.verify import VerificationError, assert_account
from kira.identity import actor_id

FIELDS = ("binding", "enabled", "epoch", "role", "instance_ids")


def guard(bundle, need_identity=True):
    """Reject synthetic bundles; access administration additionally needs the identity module."""
    if bundle["spec"]["reference_only"]:
        raise VerificationError("Private operations require a customer bundle, not a synthetic reference")
    if need_identity:
        if "identity" not in bundle["config"]:
            raise VerificationError("Access administration requires a customer identity bundle")
        identity.validate_config(bundle["config"]["identity"])
        identity.validate_bindings(bundle["spec"], bundle["bindings"])
    owned_runtime.validate_bindings(bundle["spec"], bundle["config"], bundle["bindings"])


def key(actor):
    return {"PK": "IDENTITY#" + actor, "SK": "META"}


def pack(value):
    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in value.items()}


def current(client, spec, actor):
    row = client.get_item(TableName=identity.table_name(spec), Key=pack(key(actor)), ConsistentRead=True)
    decoder = TypeDeserializer()
    return {k: decoder.deserialize(v) for k, v in row["Item"].items()} if "Item" in row else None


def change(bundle, request, previous):
    """Produce a private reviewable diff without storing the issuer's raw subject."""
    spec = bundle["spec"]
    try:
        if (
            set(request) != {"subject", "enabled", "role", "instance_ids"}
            or not isinstance(request["subject"], str)
            or not 1 <= len(request["subject"]) <= 512
            or type(request["enabled"]) is not bool
            or request["role"] not in {"viewer", "investigator"}
            or not isinstance(request["instance_ids"], list)
            or not 1 <= len(request["instance_ids"]) <= 100
            or any(not isinstance(v, str) for v in request["instance_ids"])
            or len(set(request["instance_ids"])) != len(request["instance_ids"])
            or not set(request["instance_ids"]) <= {i["id"] for i in spec["instances"]}
        ):
            raise ValueError()
        actor = actor_id(bundle["config"]["identity"]["issuer"], request["subject"])
        epoch = 1
        if previous is not None:
            if (
                set(previous) != set(key(actor)) | set(FIELDS)
                or any(previous[k] != v for k, v in key(actor).items())
                or previous["epoch"] != int(previous["epoch"])
                or isinstance(previous["epoch"], bool)
                or not 1 <= previous["epoch"] < 2**53
            ):
                raise ValueError()
            epoch = int(previous["epoch"]) + 1
        desired = {
            **key(actor),
            "binding": [
                spec["environment"],
                spec["account_id"],
                owned_runtime.fingerprint(spec, bundle["config"], bundle["bindings"]),
            ],
            "enabled": request["enabled"],
            "epoch": epoch,
            "role": request["role"],
            "instance_ids": sorted(request["instance_ids"]),
        }
        before = {**previous, "epoch": int(previous["epoch"])} if previous else None
        plan = {"bundle_hash": bundle["review_hash"], "actor": actor, "before": before, "after": desired}
        return {**plan, "change_hash": digest(plan)}
    except Exception:
        raise VerificationError(
            "Invalid access change or existing grant; repair explicitly before retry"
        ) from None


def plan_grant(bundle, request, factory=clients):
    guard(bundle)
    # Validate all input before creating an AWS client, including actor derivation.
    candidate = change(bundle, request, None)
    spec = bundle["spec"]
    assert_account(factory("sts", spec["monitor_region"]), spec)
    identity.verify_foundations(bundle, factory)
    previous = current(factory("dynamodb", spec["monitor_region"]), spec, candidate["actor"])
    return change(bundle, request, previous)


def apply_grant(bundle, request, reviewed, factory=clients):
    guard(bundle)
    durable_ops.require_reviewed_source(bundle)
    actual = plan_grant(bundle, request, factory)
    if actual != reviewed:
        raise VerificationError("Access diff changed; review a new grant plan")
    kwargs = {
        "TableName": identity.table_name(bundle["spec"]),
        "Item": pack(actual["after"]),
        "ConditionExpression": "attribute_not_exists(PK)",
    }
    if actual["before"]:
        # Compare every authorization field, not only epoch, to fence another writer.
        kwargs.update(
            ConditionExpression=" AND ".join(f"#f{n} = :v{n}" for n in range(len(FIELDS))),
            ExpressionAttributeNames={f"#f{n}": field for n, field in enumerate(FIELDS)},
            ExpressionAttributeValues=pack(
                {f":v{n}": actual["before"][field] for n, field in enumerate(FIELDS)}
            ),
        )
    factory("dynamodb", bundle["spec"]["monitor_region"]).put_item(**kwargs)
    # Keep disabled tombstones: deleting/recreating epoch=1 can revive old sessions.
    return {
        "status": "APPLIED",
        "actor": actual["actor"],
        "epoch": actual["after"]["epoch"],
        "enabled": actual["after"]["enabled"],
    }


def version_label(spec):
    return "kira-identity-" + spec["release_id"]


def pin_secret(bundle, factory=clients):
    guard(bundle)
    durable_ops.require_reviewed_source(bundle)
    spec = bundle["spec"]
    assert_account(factory("sts", spec["bedrock_region"]), spec)
    # The verifier accepts an existing labeled version before the release label
    # is attached; unlike collect/describe, this command is an explicit mutation.
    identity.verify_foundations(bundle, factory, require_label=False)
    binding = identity.validate_bindings(spec, bundle["bindings"])
    client = factory("secretsmanager", spec["bedrock_region"])
    metadata = client.describe_secret(SecretId=binding["SigningSecretArn"])
    label = version_label(spec)
    owners = [v for v, stages in metadata["VersionIdsToStages"].items() if label in stages]
    if owners and owners != [binding["SigningSecretVersion"]]:
        raise VerificationError("Release key label already points to another version; create a new release")
    if not owners:
        client.update_secret_version_stage(
            SecretId=binding["SigningSecretArn"],
            VersionStage=label,
            MoveToVersionId=binding["SigningSecretVersion"],
        )
    return {"status": "PINNED", "version": binding["SigningSecretVersion"], "label": label}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("grant-plan", "grant-apply", "pin-secret-version"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--review-hash", required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--grant-plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        bundle = durable_ops.read_bundle(args.bundle, args.review_hash)
        guard(bundle)
        if args.command == "pin-secret-version":
            result = pin_secret(bundle)
        else:
            if not args.request or args.request.stat().st_size > 128000:
                raise VerificationError("Provide a bounded private access request file")
            request = json.loads(args.request.read_text())
            if args.command == "grant-apply":
                if not args.grant_plan or args.grant_plan.stat().st_size > 128000:
                    raise VerificationError("Provide the reviewed private grant plan")
                result = apply_grant(bundle, request, json.loads(args.grant_plan.read_text()))
            else:
                result = plan_grant(bundle, request)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"status": result.get("status", "PLANNED"), "output": str(args.output)}))
    except (VerificationError, BotoCoreError, ClientError, OSError, ValueError, KeyError):
        # SDK/JSON exceptions can contain private subjects or access plans.
        print(
            "Access administration failed; verify the private inputs, ownership and reviewed source.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
