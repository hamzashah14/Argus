"""Explicit local plan/build and separately invoked AWS release operations."""

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import boto3
from botocore.config import Config

from infra import reconcile, release
from infra.spec import load, log_groups, metric_catalog, name
from infra.templates import bucket_name
from infra.verify import VerificationError, assert_account, coverage, routing_health


def clients(service, region):
    return boto3.client(
        service,
        region_name=region,
        config=Config(
            connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 2, "mode": "standard"}
        ),
    )


def upload(spec, build_dir, factory):
    assert_account(factory("sts", spec["bedrock_region"]), spec)
    from infra.verify import assert_stack_absent

    for stage in release.IMMUTABLE:
        assert_stack_absent(
            factory("cloudformation", spec[release.STAGES[stage]]), release.stack_name(spec, stage)
        )
    build = release.checked_build(build_dir, spec)
    result = {"artifacts": {}}
    # Check BOTH regional buckets before uploading any artifact.
    for purpose, region in (("tools", spec["bedrock_region"]), ("monitor", spec["monitor_region"])):
        client = factory("s3", region)
        bucket = bucket_name(spec, purpose)
        owner = {"Bucket": bucket, "ExpectedBucketOwner": spec["account_id"]}
        if client.get_bucket_versioning(**owner).get("Status") != "Enabled":
            raise VerificationError("Artifact bucket versioning must be enabled")
        location = client.get_bucket_location(**owner).get("LocationConstraint") or "us-east-1"
        if location != region:
            raise VerificationError("Artifact bucket is in the wrong region")
    for function, artifact in build["functions"].items():
        purpose = "monitor" if function == "trigger_investigation" else "tools"
        region = spec["monitor_region"] if purpose == "monitor" else spec["bedrock_region"]
        bucket = bucket_name(spec, purpose)
        key = f"releases/{spec['release_id']}/{artifact['sha256']}.zip"
        response = factory("s3", region).put_object(
            Bucket=bucket,
            Key=key,
            Body=(build_dir / artifact["artifact"]).read_bytes(),
            ExpectedBucketOwner=spec["account_id"],
            ServerSideEncryption="AES256",
            ChecksumSHA256=base64.b64encode(bytes.fromhex(artifact["sha256"])).decode(),
        )
        if response.get("VersionId") in (None, "", "null"):
            raise VerificationError("Artifact upload did not return an immutable object version")
        result["artifacts"][function] = {
            "bucket": bucket,
            "key": key,
            "version_id": response["VersionId"],
            "sha256": artifact["sha256"],
        }
    secret = factory("secretsmanager", spec["bedrock_region"]).describe_secret(
        SecretId=f"{name(spec, '')[:-1]}/log-cursor"
    )
    label = "kira-" + spec["release_id"]
    pinned = [version for version, stages in secret["VersionIdsToStages"].items() if label in stages]
    versions = pinned or [
        version for version, stages in secret["VersionIdsToStages"].items() if "AWSCURRENT" in stages
    ]
    if len(versions) != 1:
        raise VerificationError("Cursor secret has no unique current version")
    result["secret"] = {"arn": secret["ARN"], "version_id": versions[0]}
    if not pinned:
        factory("secretsmanager", spec["bedrock_region"]).update_secret_version_stage(
            SecretId=secret["ARN"], VersionStage=label, MoveToVersionId=versions[0]
        )
    release.validate_bindings(spec, result, build)
    return result


def collect(spec, bindings, stage, factory):
    assert_account(factory("sts", spec[release.STAGES[stage]]), spec)
    data = factory("cloudformation", spec[release.STAGES[stage]]).describe_stacks(
        StackName=release.stack_name(spec, stage)
    )["Stacks"][0]
    if data["StackStatus"] != "CREATE_COMPLETE":
        raise VerificationError("Candidate release stack is not successfully created")
    outputs = {item["OutputKey"]: item["OutputValue"] for item in data["Outputs"]}
    mapping = {
        "tools": {"AgentId": "agent_id", "LogsVersionArn": "logs_arn", "MetricsVersionArn": "metrics_arn"},
        "alias": {"AgentAliasId": "alias_id"},
        "worker": {"WorkerVersionArn": "worker_arn"},
    }
    return {**bindings, **{mapping[stage][key]: outputs[key] for key in mapping[stage]}}


def prepare_agent(spec, bindings, factory):
    assert_account(factory("sts", spec["bedrock_region"]), spec)
    client = factory("bedrock-agent", spec["bedrock_region"])
    agent = client.get_agent(agentId=bindings["agent_id"])["agent"]
    if agent["agentName"] != name(spec, "agent", True):
        raise VerificationError("Refusing to prepare an agent outside this release")
    client.prepare_agent(agentId=bindings["agent_id"])
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        status = client.get_agent(agentId=bindings["agent_id"])["agent"]["agentStatus"]
        if status == "PREPARED":
            return {"status": "PREPARED", "agent_id": bindings["agent_id"]}
        if status == "FAILED":
            raise VerificationError("Candidate preparation failed; existing release untouched")
        time.sleep(2)
    raise VerificationError("Candidate preparation timed out; existing release untouched")


def seal(spec, stage, factory):
    region = spec[release.STAGES[stage]]
    assert_account(factory("sts", region), spec)
    client = factory("cloudformation", region)
    stack = release.stack_name(spec, stage)
    data = client.describe_stacks(StackName=stack)["Stacks"][0]
    actual_tags = {item["Key"]: item["Value"] for item in data.get("Tags", [])}
    if (
        data["StackStatus"] != "CREATE_COMPLETE"
        or actual_tags.get("Environment") != spec["environment"]
        or actual_tags.get("Project") != spec["project"]
        or actual_tags.get("ManagedBy") != "kira-cloudformation"
    ):
        raise VerificationError("Only a successfully created, owned release stack can be sealed")
    client.set_stack_policy(StackName=stack, StackPolicyBody=json.dumps(release.SEALED_POLICY))
    client.update_termination_protection(StackName=stack, EnableTerminationProtection=True)
    if (
        not client.describe_stacks(StackName=stack)["Stacks"][0].get("EnableTerminationProtection")
        or json.loads(client.get_stack_policy(StackName=stack)["StackPolicyBody"]) != release.SEALED_POLICY
    ):
        raise VerificationError("Release stack protection did not take effect")
    return {"status": "SEALED", "stack": stack}


def execute(bundle, directory, stage, change_set, reviewed_change_hash, record, retirement, factory):
    spec = bundle["spec"]
    info = bundle["stages"][stage]
    assert_account(factory("sts", info["region"]), spec)
    if bundle["source_dirty"]:
        raise VerificationError("Commit and rebuild the reviewed source before cloud execution")
    if stage == "routing":
        release.require_receipt(bundle, record)
        release.verify_candidate(bundle, factory)
        coverage(spec, factory)
        current_plan = reconcile.plan(
            spec, reconcile.owned_resources(spec, factory), bundle["bindings"]["worker_arn"]
        )
        if current_plan["disable_alarms"] or current_plan["unsubscribe"]:
            raise VerificationError("Retire obsolete alarm actions/subscribers before the routing update")
        if retirement is None:
            raise VerificationError("Routing requires a reviewed retirement plan, including an empty plan")
        if retirement != current_plan:
            raise VerificationError("Routing retirement plan changed; review it again")
    response, actual_hash = release.inspect_change_set(bundle, stage, change_set, factory)
    if actual_hash != reviewed_change_hash:
        raise VerificationError("CloudFormation change set differs from the reviewed diff")
    client = factory("cloudformation", info["region"])
    client.execute_change_set(StackName=info["stack"], ChangeSetName=response["ChangeSetId"])
    # Do not claim completion from an accepted ExecuteChangeSet API call.
    return {
        "status": "EXECUTION_REQUESTED",
        "stack": info["stack"],
        "region": info["region"],
        "next": "Wait for stack completion, then collect outputs or verify routing",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("render", "build", "upload", "collect", "prepare-agent", "seal"):
        p = sub.add_parser(command)
        p.add_argument("--spec", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        if command in {"render", "upload"}:
            p.add_argument("--build-dir", type=Path, required=command == "upload")
        if command in {"render", "collect", "prepare-agent"}:
            p.add_argument("--bindings", type=Path, required=command != "render")
        if command == "build":
            p.add_argument("--wheelhouse", type=Path, required=True)
        if command in {"collect", "seal"}:
            p.add_argument("--stage", choices=sorted(release.IMMUTABLE), required=True)
    for command in (
        "change-set",
        "inspect",
        "execute",
        "verify-candidate",
        "coverage",
        "retirement-plan",
        "retire",
        "verify-routing",
    ):
        p = sub.add_parser(command)
        p.add_argument("--bundle", type=Path, required=True)
        p.add_argument("--review-hash", required=True)
        p.add_argument("--output", type=Path, required=True)
        if command in {"change-set", "inspect", "execute"}:
            p.add_argument("--stage", choices=sorted(release.STAGES), required=True)
        if command in {"inspect", "execute"}:
            p.add_argument("--change-set", required=True)
        if command == "execute":
            p.add_argument("--change-set-hash", required=True)
            p.add_argument("--receipt", type=Path)
            p.add_argument("--retirement-plan", type=Path)
        if command == "verify-candidate":
            p.add_argument(
                "--invoke-canary",
                action="store_true",
                required=True,
                help="Invokes a paid candidate investigation; produces a promotion receipt",
            )
        if command == "retire":
            p.add_argument("--retirement-plan", type=Path, required=True)
            p.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if hasattr(args, "spec"):
            spec = load(args.spec)
            if args.command not in {"render", "build"} and spec["reference_only"]:
                raise VerificationError("Synthetic reference inputs cannot be used for cloud operations")
            if args.command == "render":
                value = release.render(args.spec, args.output, args.build_dir, args.bindings)
                print(
                    json.dumps(
                        {
                            "review_hash": value["review_hash"],
                            "stages": list(value["stages"]),
                            "source_dirty": value["source_dirty"],
                        }
                    )
                )
                return 0
            if args.command == "build":
                from scripts.build_lambdas import FUNCTIONS, build

                args.output.mkdir(parents=True, exist_ok=True)
                release.write_json(args.output / "metric-catalog.json", metric_catalog(spec))
                release.write_json(args.output / "log-scope.json", log_groups(spec))
                build(
                    FUNCTIONS,
                    args.output,
                    args.output / "metric-catalog.json",
                    args.wheelhouse,
                    args.output / "log-scope.json",
                )
                return 0
            if args.command == "upload":
                value = upload(spec, args.build_dir, clients)
            elif args.command == "seal":
                value = seal(spec, args.stage, clients)
            else:
                bindings = json.loads(args.bindings.read_text())
                value = (
                    collect(spec, bindings, args.stage, clients)
                    if args.command == "collect"
                    else prepare_agent(spec, bindings, clients)
                )
        else:
            bundle = release.read_bundle(args.bundle, args.review_hash)
            spec = bundle["spec"]
            if spec["reference_only"]:
                raise VerificationError("Synthetic reference inputs cannot be used for cloud operations")
            if args.command == "change-set":
                if bundle["source_dirty"]:
                    raise VerificationError("Commit and rebuild source before creating cloud change sets")
                value = release.create_change_set(bundle, args.bundle, args.stage, clients)
            elif args.command == "inspect":
                result, review_hash = release.inspect_change_set(bundle, args.stage, args.change_set, clients)
                value = {
                    "review_hash": review_hash,
                    "changes": result["Changes"],
                    "change_set": result["ChangeSetId"],
                }
            elif args.command == "execute":
                record = json.loads(args.receipt.read_text()) if args.receipt else None
                retirement = json.loads(args.retirement_plan.read_text()) if args.retirement_plan else None
                value = execute(
                    bundle,
                    args.bundle,
                    args.stage,
                    args.change_set,
                    args.change_set_hash,
                    record,
                    retirement,
                    clients,
                )
            elif args.command == "verify-candidate":
                value = release.receipt(bundle, clients)
            elif args.command == "coverage":
                value = coverage(spec, clients)
            elif args.command == "verify-routing":
                assert_account(clients("sts", spec["monitor_region"]), spec)
                value = routing_health(spec, clients, bundle["bindings"]["worker_arn"])
            elif args.command == "retirement-plan":
                assert_account(clients("sts", spec["monitor_region"]), spec)
                value = reconcile.plan(
                    spec, reconcile.owned_resources(spec, clients), bundle["bindings"]["worker_arn"]
                )
            else:
                release.require_receipt(bundle, json.loads(args.receipt.read_text()))
                release.verify_candidate(bundle, clients)
                value = reconcile.apply(
                    spec,
                    clients,
                    json.loads(args.retirement_plan.read_text()),
                    bundle["bindings"]["worker_arn"],
                )
        release.write_json(args.output, value)
        print(f"Saved {args.command} result to {args.output}")
        return 0
    except Exception as exc:
        # Cloud responses may contain account data, payloads or tokens. Save detailed
        # diagnosis only through an operator's private tooling, never public stdout.
        from botocore.exceptions import BotoCoreError, ClientError

        if isinstance(exc, (VerificationError, ValueError, KeyError, OSError, BotoCoreError, ClientError)):
            print(
                f"Release operation failed ({type(exc).__name__}); no success receipt was produced.",
                file=sys.stderr,
            )
            if isinstance(exc, VerificationError):
                print(str(exc), file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
