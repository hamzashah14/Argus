"""Release bundles bind source, immutable S3 object versions, templates and evidence."""

import base64
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone

from infra import templates
from infra.spec import ROOT, cwagent, digest, load, log_groups, metric_catalog, name, tags
from infra.verify import VerificationError, assert_account, assert_stack_absent, coverage, verify_function

STAGES = {
    "foundation-tools": "bedrock_region",
    "foundation-monitor": "monitor_region",
    "tools": "bedrock_region",
    "alias": "bedrock_region",
    "worker": "monitor_region",
    "routing": "monitor_region",
}
IMMUTABLE = {"tools", "alias", "worker"}
SEALED_POLICY = {"Statement": [{"Effect": "Deny", "Action": "Update:*", "Principal": "*", "Resource": "*"}]}


def stack_name(spec, stage):
    return name(spec, stage, release=stage in IMMUTABLE)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def checked_build(directory, spec):
    manifest = json.loads((directory / "manifest.json").read_text())
    if set(manifest["functions"]) != {"fetch_logs", "fetch_metrics", "trigger_investigation"}:
        raise VerificationError("Release requires all three Lambda artifacts")
    if manifest["python"] != "3.12" or manifest["architecture"] != "x86_64":
        raise VerificationError("Unsupported build runtime/architecture")
    lock_hash = hashlib.sha256((ROOT / "requirements/lambda.lock").read_bytes()).hexdigest()
    if manifest.get("lock_sha256") != lock_hash:
        raise VerificationError("Dependency lock changed after build; rebuild before rendering")
    for function, item in manifest["functions"].items():
        required = {str(p.relative_to(ROOT)) for p in (ROOT / "kira").glob("*.py")} | {
            "agent-instruction.txt",
            "schemas/fetch_logs.json",
            "schemas/fetch_metrics.json",
            "kira_agentcore.py",
            "lambda_function.py",
        }
        if not required <= set(item["source_files"]):
            raise VerificationError("Build manifest omits required current source")
        if item["artifact"] != f"{function}.zip":
            raise VerificationError("Invalid artifact path")
        path = directory / item["artifact"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise VerificationError("Artifact hash differs from build manifest")
        with zipfile.ZipFile(path) as archive:
            if hashlib.sha256(archive.read("requirements/lambda.lock")).hexdigest() != lock_hash:
                raise VerificationError("Packaged dependency lock differs from current source")
            if json.loads(archive.read("config/metric-catalog.json")) != metric_catalog(spec):
                raise VerificationError("Packaged metric catalog differs from deployment inventory")
            if json.loads(archive.read("config/log-scope.json")) != log_groups(spec):
                raise VerificationError("Packaged log scope differs from deployment inventory")
            for filename, expected in item["source_files"].items():
                if hashlib.sha256(archive.read(filename)).hexdigest() != expected:
                    raise VerificationError("Packaged source differs from build manifest")
                source = ROOT / (
                    f"lambda/{function}/lambda_function.py" if filename == "lambda_function.py" else filename
                )
                if filename.startswith(("kira/", "schemas/")) or filename in {
                    "lambda_function.py",
                    "agent-instruction.txt",
                    "kira_agentcore.py",
                }:
                    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                        raise VerificationError("Source changed after build; rebuild before rendering")
    return manifest


def validate_bindings(spec, bindings, build):
    if not isinstance(bindings, dict):
        raise VerificationError("Release bindings must be an object")
    if not bindings:
        return
    allowed = {"artifacts", "secret", "agent_id", "alias_id", "worker_arn", "logs_arn", "metrics_arn"}
    if set(bindings) - allowed:
        raise VerificationError("Unknown release binding")
    if "artifacts" in bindings:
        if (
            build is None
            or not isinstance(bindings["artifacts"], dict)
            or set(bindings["artifacts"]) != set(build["functions"])
        ):
            raise VerificationError("Artifact bindings require matching verified builds")
        for function, item in bindings["artifacts"].items():
            purpose = "monitor" if function == "trigger_investigation" else "tools"
            expected_hash = build["functions"][function]["sha256"]
            if (
                not isinstance(item, dict)
                or set(item) != {"bucket", "key", "version_id", "sha256"}
                or item["bucket"] != templates.bucket_name(spec, purpose)
                or item["sha256"] != expected_hash
                or item["key"] != f"releases/{spec['release_id']}/{expected_hash}.zip"
                or not isinstance(item["version_id"], str)
                or item["version_id"] in ("", "null")
            ):
                raise VerificationError("Artifact binding is not a pinned object in this environment")
    if "secret" in bindings:
        value = bindings["secret"]
        expected = f"arn:aws:secretsmanager:{spec['bedrock_region']}:{spec['account_id']}:secret:{name(spec, '')[:-1]}/log-cursor-"
        if (
            not isinstance(value, dict)
            or set(value) != {"arn", "version_id"}
            or not isinstance(value["arn"], str)
            or not re.fullmatch(re.escape(expected) + r"[A-Za-z0-9]{6}", value["arn"])
            or not isinstance(value["version_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9-]{32,64}", value["version_id"])
        ):
            raise VerificationError("Cursor secret must be pinned to this environment and region")
    for key in ("agent_id", "alias_id"):
        if key in bindings and (
            not isinstance(bindings[key], str)
            or not re.fullmatch(r"[A-Za-z0-9]{10}", bindings[key])
            or bindings[key] == "TSTALIASID"
        ):
            raise VerificationError("Expected a concrete agent/alias ID")
    for key, function in (
        ("worker_arn", "trigger_investigation"),
        ("logs_arn", "fetch_logs"),
        ("metrics_arn", "fetch_metrics"),
    ):
        if key in bindings:
            region = spec["monitor_region"] if key == "worker_arn" else spec["bedrock_region"]
            expected = f"arn:aws:lambda:{region}:{spec['account_id']}:function:{name(spec, function.replace('_', '-'), True)}:"
            if (
                not isinstance(bindings[key], str)
                or not bindings[key].startswith(expected)
                or not re.fullmatch(r"[1-9][0-9]*", bindings[key][len(expected) :])
            ):
                raise VerificationError("Lambda binding must name this candidate's qualified numeric version")


def render(spec_path, output, build_dir=None, bindings_path=None):
    spec = load(spec_path)
    build = checked_build(build_dir, spec) if build_dir else None
    bindings = json.loads(bindings_path.read_text()) if bindings_path else {}
    validate_bindings(spec, bindings, build)
    values = {
        "foundation-tools": templates.foundation(spec, "tools"),
        "foundation-monitor": templates.foundation(spec, "monitor"),
    }
    if {"artifacts", "secret"} <= bindings.keys():
        values["tools"] = templates.tools_release(spec, bindings["artifacts"], bindings["secret"])
    if "agent_id" in bindings:
        values["alias"] = templates.candidate_alias(spec, bindings["agent_id"])
    if {"artifacts", "agent_id", "alias_id"} <= bindings.keys():
        values["worker"] = templates.worker_release(
            spec, bindings["artifacts"]["trigger_investigation"], bindings["agent_id"], bindings["alias_id"]
        )
    if {"worker_arn", "agent_id", "alias_id"} <= bindings.keys():
        values["routing"] = templates.routing(
            spec, bindings["worker_arn"], bindings["agent_id"], bindings["alias_id"]
        )
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    bundle = {
        "version": 1,
        "source_sha": source_sha,
        "source_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "spec": spec,
        "bindings": bindings,
        "build": build,
        "prompt_sha256": hashlib.sha256((ROOT / "agent-instruction.txt").read_bytes()).hexdigest(),
        "schema_sha256": {
            tool: hashlib.sha256((ROOT / f"schemas/{tool}.json").read_bytes()).hexdigest()
            for tool in ("fetch_logs", "fetch_metrics")
        },
        "stages": {
            stage: {
                "stack": stack_name(spec, stage),
                "region": spec[STAGES[stage]],
                "create_only": stage in IMMUTABLE,
                "template_hash": templates.template_hash(t),
            }
            for stage, t in values.items()
        },
    }
    bundle["review_hash"] = digest(bundle)
    output.mkdir(parents=True, exist_ok=True)
    for stage, t in values.items():
        if len(json.dumps(t).encode()) > 51200:
            raise VerificationError("Template exceeds inline change-set limit; reduce inventory size")
        write_json(output / f"{stage}.json", t)
    write_json(output / "bundle.json", bundle)
    write_json(output / "metric-catalog.json", metric_catalog(spec))
    write_json(output / "log-scope.json", log_groups(spec))
    for instance in spec["instances"]:
        write_json(output / f"cwagent-{instance['id']}.json", cwagent(spec, instance))
    return bundle


def read_bundle(directory, expected_hash=None):
    bundle = json.loads((directory / "bundle.json").read_text())
    review_hash = bundle.pop("review_hash")
    if digest(bundle) != review_hash or (expected_hash and review_hash != expected_hash):
        raise VerificationError("Bundle differs from the reviewed plan")
    bundle["review_hash"] = review_hash
    for stage, info in bundle["stages"].items():
        if (
            stage not in STAGES
            or info["stack"] != stack_name(bundle["spec"], stage)
            or info["region"] != bundle["spec"][STAGES[stage]]
        ):
            raise VerificationError("Invalid bundle stage boundary")
        value = json.loads((directory / f"{stage}.json").read_text())
        if templates.template_hash(value) != info["template_hash"]:
            raise VerificationError("Template differs from the reviewed plan")
    return bundle


def create_change_set(bundle, directory, stage, clients):
    spec, info = bundle["spec"], bundle["stages"][stage]
    assert_account(clients("sts", info["region"]), spec)
    client = clients("cloudformation", info["region"])
    kind = "CREATE"
    if stage in IMMUTABLE:
        assert_stack_absent(client, info["stack"])
    else:
        try:
            assert_stack_absent(client, info["stack"])
        except VerificationError:
            kind = "UPDATE"
            current = client.describe_stacks(StackName=info["stack"])["Stacks"][0]
            actual_tags = {x["Key"]: x["Value"] for x in current.get("Tags", [])}
            if any(actual_tags.get(k) != v for k, v in tags(spec).items()):
                raise VerificationError("Refusing to adopt an unowned stack")
    return client.create_change_set(
        StackName=info["stack"],
        ChangeSetName="review-" + bundle["review_hash"][:24],
        ChangeSetType=kind,
        TemplateBody=(directory / f"{stage}.json").read_text(),
        Capabilities=["CAPABILITY_IAM"],
        RoleARN=spec["deployment_role_arn"],
        Tags=templates.tagged(spec),
    )


def change_set_digest(response):
    return digest(
        {
            key: response.get(key)
            for key in ("ChangeSetId", "StackId", "Changes", "Parameters", "Capabilities", "RoleARN", "Tags")
        }
    )


def inspect_change_set(bundle, stage, change_set, clients):
    info = bundle["stages"][stage]
    client = clients("cloudformation", info["region"])
    result = client.describe_change_set(StackName=info["stack"], ChangeSetName=change_set)
    if result.get("NextToken"):
        raise VerificationError("Paginated change set needs complete review; execution is blocked")
    if result["Status"] != "CREATE_COMPLETE" or result["ExecutionStatus"] != "AVAILABLE":
        raise VerificationError("Change set is not ready for execution")
    body = client.get_template(StackName=info["stack"], ChangeSetName=change_set)["TemplateBody"]
    if isinstance(body, str):
        body = json.loads(body)
    if templates.template_hash(body) != info["template_hash"]:
        raise VerificationError("CloudFormation template differs from reviewed bundle")
    if result.get("RoleARN") != bundle["spec"]["deployment_role_arn"]:
        raise VerificationError("CloudFormation execution role differs from the plan")
    return result, change_set_digest(result)


def verify_candidate(bundle, clients):
    spec, bindings = bundle["spec"], bundle["bindings"]
    assert_account(clients("sts", spec["bedrock_region"]), spec)
    for stage in sorted(IMMUTABLE):
        cfn = clients("cloudformation", spec[STAGES[stage]])
        stack = stack_name(spec, stage)
        current = cfn.describe_stacks(StackName=stack)["Stacks"][0]
        if current["StackStatus"] != "CREATE_COMPLETE" or not current.get("EnableTerminationProtection"):
            raise VerificationError(
                "Seal all successfully created release stacks before candidate verification"
            )
        if json.loads(cfn.get_stack_policy(StackName=stack)["StackPolicyBody"]) != SEALED_POLICY:
            raise VerificationError("Release stack update protection differs from the sealed policy")
    functions = []
    for key, logical, function, stage in (
        ("logs_arn", "Logs", "fetch_logs", "tools"),
        ("metrics_arn", "Metrics", "fetch_metrics", "tools"),
        ("worker_arn", "Worker", "trigger_investigation", "worker"),
    ):
        if key not in bindings:
            raise VerificationError("Candidate output bindings are incomplete")
        region = spec["monitor_region"] if stage == "worker" else spec["bedrock_region"]
        expected_template = (
            templates.tools_release(spec, bindings["artifacts"], bindings["secret"])
            if stage == "tools"
            else templates.worker_release(
                spec, bindings["artifacts"][function], bindings["agent_id"], bindings["alias_id"]
            )
        )
        expected_env = expected_template["Resources"][logical]["Properties"]["Environment"]["Variables"]
        result = verify_function(clients("lambda", region), bindings[key], bindings["artifacts"][function])
        if result.pop("configuration") != expected_env:
            raise VerificationError("Published version configuration differs from planned configuration")
        functions.append(result)
        if stage == "tools" and spec["executor_mode"] == "release-name":
            live = clients("lambda", region).get_function(FunctionName=bindings[key].rsplit(":", 1)[0])[
                "Configuration"
            ]
            if (
                live["CodeSha256"] != base64.b64encode(bytes.fromhex(result["code_sha256"])).decode()
                or live.get("Environment", {}).get("Variables", {}) != expected_env
            ):
                raise VerificationError(
                    "Release-specific fallback function drifted from its published snapshot"
                )
    agent = clients("bedrock-agent", spec["bedrock_region"])
    alias = agent.get_agent_alias(agentId=bindings["agent_id"], agentAliasId=bindings["alias_id"])[
        "agentAlias"
    ]
    route = alias.get("routingConfiguration", [])
    if (
        alias["agentAliasStatus"] != "PREPARED"
        or len(route) != 1
        or not re.fullmatch(r"[1-9][0-9]*", route[0].get("agentVersion", ""))
    ):
        raise VerificationError("Candidate alias is not routed to one prepared numbered version")
    version = route[0]["agentVersion"]
    data = agent.get_agent_version(agentId=bindings["agent_id"], agentVersion=version)["agentVersion"]
    if (
        data["foundationModel"] != spec["model_id"]
        or hashlib.sha256(data["instruction"].encode()).hexdigest() != bundle["prompt_sha256"]
    ):
        raise VerificationError("Candidate model or instruction differs from release")
    seen = set()
    for page in agent.get_paginator("list_agent_action_groups").paginate(
        agentId=bindings["agent_id"], agentVersion=version
    ):
        for summary in page["actionGroupSummaries"]:
            group = agent.get_agent_action_group(
                agentId=bindings["agent_id"], agentVersion=version, actionGroupId=summary["actionGroupId"]
            )["agentActionGroup"]
            tool = group["actionGroupName"]
            if tool not in {"fetch_logs", "fetch_metrics"} or group["actionGroupState"] != "ENABLED":
                raise VerificationError("Unexpected or disabled candidate action group")
            executor = bindings["logs_arn" if tool == "fetch_logs" else "metrics_arn"]
            if spec["executor_mode"] == "release-name":
                executor = executor.rsplit(":", 1)[0]
            if (
                group["actionGroupExecutor"]["lambda"] != executor
                or hashlib.sha256(group["apiSchema"]["payload"].encode()).hexdigest()
                != bundle["schema_sha256"][tool]
            ):
                raise VerificationError("Candidate executor or schema differs from release")
            seen.add(tool)
    if seen != {"fetch_logs", "fetch_metrics"}:
        raise VerificationError("Candidate is missing required tools")
    return {"functions": functions, "agent_version": version, "alias_id": bindings["alias_id"]}


def candidate_canary(bundle, clients):
    """Explicitly paid/invoking command; never run as part of offline checks."""
    import uuid

    spec, b = bundle["spec"], bundle["bindings"]
    response = clients("bedrock-agent-runtime", spec["bedrock_region"]).invoke_agent(
        agentId=b["agent_id"],
        agentAliasId=b["alias_id"],
        sessionId=str(uuid.uuid4()),
        enableTrace=True,
        inputText=f"Deployment canary. Call fetch_logs to discover log groups for {spec['instances'][0]['id']}, and call fetch_metrics for that instance CPUUtilization. Report whether BOTH tools succeeded, including no data. Do not skip either tool.",
    )
    seen, observed, answer = set(), set(), False
    stream = response["completion"]
    try:
        for index, event in enumerate(stream):
            if index >= 2048 or any(key.endswith("Exception") for key in event):
                raise VerificationError("Candidate canary did not complete within its event limit")
            answer = answer or bool(event.get("chunk", {}).get("bytes"))
            trace = event.get("trace", {}).get("trace", {})
            if "failureTrace" in trace:
                raise VerificationError("Bedrock reported candidate tool failure")
            orchestration = trace.get("orchestrationTrace", {})
            call = orchestration.get("invocationInput", {}).get("actionGroupInvocationInput", {})
            if call.get("actionGroupName"):
                seen.add(call["actionGroupName"])
            output = orchestration.get("observation", {}).get("actionGroupInvocationOutput", {}).get("text")
            if output:
                # Require an actual success-shaped tool observation, not just a proposed call.
                try:
                    body = json.loads(output)
                except (TypeError, ValueError):
                    raise VerificationError(
                        "Tool canary output was not a JSON contract; retain private trace for investigation"
                    )
                if body.get("status") in {"log_groups_found", "no_log_groups_found"}:
                    observed.add("fetch_logs")
                elif body.get("status") in {"ok", "no_data"} and "descriptor" in body:
                    observed.add("fetch_metrics")
                else:
                    raise VerificationError("Tool canary returned failure or an unexpected contract")
    finally:
        if hasattr(stream, "close"):
            stream.close()
    if not answer or seen != {"fetch_logs", "fetch_metrics"} or observed != seen:
        raise VerificationError("Canary did not demonstrate successful execution of both tool contracts")
    return sorted(observed)


def receipt(bundle, clients):
    candidate = verify_candidate(bundle, clients)
    coverage_result = coverage(bundle["spec"], clients)
    tools = candidate_canary(bundle, clients)
    return {
        "bundle_hash": bundle["review_hash"],
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate,
        "coverage": coverage_result,
        "canary_tools": tools,
    }


def require_receipt(bundle, record):
    if not isinstance(record, dict):
        raise VerificationError("Promotion requires a candidate receipt")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["checked_at"])).total_seconds()
    if (
        record.get("bundle_hash") != bundle["review_hash"]
        or record.get("status") != "PASS"
        or not 0 <= age <= 3600
        or set(record.get("canary_tools", [])) != {"fetch_logs", "fetch_metrics"}
    ):
        raise VerificationError("Promotion requires a passing, recent canary receipt for this exact bundle")
