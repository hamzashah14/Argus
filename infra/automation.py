"""Customer deployment CLI: init, dry-run, check, apply and resumable status.

No AWS call in init/dry-run/status. Apply reuses the existing reviewed/sealed
release gates, never installs collectors or bypasses OIDC/inbox qualification.
"""

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from infra import deployment_preflight, durable, templates
from infra.spec import ROOT, cwagent, digest, load, name, prefix
from infra.verify import PendingConfirmation, VerificationError


class Waiting(RuntimeError):
    """Resumable dependency, in-progress operation or required human action."""

    def __init__(self, message, *, automatic=False):
        super().__init__(message)
        self.automatic = automatic


def confirmation_wait(recipients):
    """The human step when the only thing missing is a click on the subscription emails."""
    return Waiting(
        f"Confirm the subscription emails sent to the addresses configured as {' and '.join(recipients)}, "
        "then resume apply with the same plan hash"
    )


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Replace atomically so an interruption cannot truncate the resume journal.
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def private_dir(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / ".local"):
        raise VerificationError("Deployment files must live under ignored .local/")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


@contextlib.contextmanager
def locked(directory):
    # File locking is released on crash; do not use stale PID lock files.
    if os.name != "posix":
        raise VerificationError("Deployment automation currently requires macOS/Linux; use WSL on Windows")
    import fcntl

    fd = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VerificationError("Another deployment process owns this work directory") from None
        yield
    finally:
        os.close(fd)


def model_api(spec):
    return spec.get("model_provider", "bedrock") == "model_api"


def stage_order(spec, config):
    stages = ["foundation-tools", "foundation-monitor", "durable-foundation"]
    if "identity" in config:
        stages += ["identity-foundation", "identity-secret", "identity-foundation-bound"]
    if model_api(spec):
        stages += ["model-secret"]  # Pins the out-of-band key secret version before any runtime renders.
    stages += ["owned-tools"]
    if config["runtime_target"] == "agentcore":
        stages += ["agentcore-runtime", "agentcore-endpoint"]
        if "identity" in config:
            stages += ["agentcore-chat-runtime", "agentcore-chat-endpoint"]
    stages += ["durable-runtime"]
    if "identity" in config:
        stages += ["chat-runtime"]
    if "observability" in spec:
        stages += ["observation-foundation", "observation-runtime", "health-bootstrap"]
    return (
        stages
        + ["candidate-verification"]
        + (["initial-access"] if "identity" in config else [])
        + ["staging-canary", "routing"]
        + (["observations"] if "observability" in spec else [])
        + ["registration-verification", "manual-acceptance"]
    )


def plan(path):
    path = Path(path).resolve()
    value = json.loads(path.read_text())
    if (
        set(value) != {"version", "spec", "runtime_config", "profile", "wheelhouse", "initial_access"}
        or value["version"] != 1
    ):
        raise VerificationError("Automation configuration has unknown or missing fields")
    if value["profile"] is not None and (
        not isinstance(value["profile"], str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", value["profile"])
    ):
        raise VerificationError("Invalid AWS profile name")
    paths = {}
    for field in ("spec", "runtime_config", "wheelhouse"):
        if not isinstance(value[field], str) or not value[field]:
            raise VerificationError("Supply spec, runtime configuration and verified wheelhouse paths")
        paths[field] = (path.parent / value[field]).resolve()
    spec = load(paths["spec"])
    config = durable.load_config(paths["runtime_config"], spec)
    identity_mode = "identity" in config
    if model_api(spec) and config["runtime_target"] != "standalone":
        raise VerificationError("model_api is supported only by the standalone runtime")
    if not config["investigation_paused"]:
        raise VerificationError(
            "Initial deployment must keep investigation_paused true; activation is a separate qualified release"
        )
    access = value["initial_access"]
    if not isinstance(access, list) or len(access) > 100:
        raise VerificationError("Invalid initial access list")
    if access and not identity_mode:
        raise VerificationError("initial_access needs an identity block in the runtime configuration")
    subjects = set()
    for request in access:
        if not isinstance(request, dict) or set(request) != {"subject", "enabled", "role", "instance_ids"}:
            raise VerificationError("Initial access requires subject, enabled, role and instance_ids")
        if (
            not isinstance(request["subject"], str)
            or not 1 <= len(request["subject"]) <= 512
            or request["subject"] in subjects
            or type(request["enabled"]) is not bool
            or request["role"] not in {"viewer", "investigator"}
            or not isinstance(request["instance_ids"], list)
            or not request["instance_ids"]
            or any(not isinstance(i, str) for i in request["instance_ids"])
            or len(set(request["instance_ids"])) != len(request["instance_ids"])
            or not set(request["instance_ids"]) <= {i["id"] for i in spec["instances"]}
        ):
            raise VerificationError("Invalid initial grant subject/role/scope")
        subjects.add(request["subject"])
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    result = {
        "version": 1,
        "source_sha": source,
        "spec": spec,
        "runtime_config": config,
        "profile": value["profile"],
        "initial_access": access,
        "paths": {k: str(v) for k, v in paths.items()},
        "stages": stage_order(spec, config),
        "automatic_activation": False,
        "manual": [
            "EC2/application/CloudWatch Agent configuration and telemetry",
            *(
                ["OIDC provider registration, client/cookie secrets, native MFA staging login"]
                if identity_mode
                else ["Local UI: export APP_PASSWORD (12+ characters) in your shell before launching it"]
            ),
            *(
                [
                    f"Create secret {prefix(spec)}/model-api-key in {spec['bedrock_region']} out of band; automation never reads or writes its value"
                ]
                if model_api(spec)
                else []
            ),
            "Primary/fallback email confirmation and real inbox qualification",
            "Production promotion/activation after customer acceptance",
        ],
    }
    from infra import durable_ops, durable_templates, identity

    previews = {
        "foundation-tools": templates.foundation(spec, "tools"),
        "foundation-monitor": templates.foundation(spec, "monitor"),
        "durable-foundation": durable_templates.foundation(spec, config),
        **(
            {
                "identity-foundation": identity.foundation(spec),
                "identity-secret": identity.signing_secret(spec),
            }
            if identity_mode
            else {}
        ),
    }
    result["bootstrap_templates"] = previews
    result["resources"] = {
        stage: {
            "stack": name(spec, stage, stage in durable_ops.IMMUTABLE),
            "region": durable_ops.stage_region(spec, stage),
            "create_only": stage in durable_ops.IMMUTABLE,
            "resource_types": sorted({r["Type"] for r in previews[stage]["Resources"].values()})
            if stage in previews
            else {
                "owned-tools": [
                    "AWS::Lambda::Function",
                    "AWS::Lambda::Version",
                    "AWS::IAM::Role",
                    "AWS::Logs::LogGroup",
                ],
                "durable-runtime": [
                    "AWS::Lambda::Function",
                    "AWS::Lambda::Version",
                    "AWS::IAM::Role",
                    "AWS::Logs::LogGroup",
                ],
                "chat-runtime": [
                    "AWS::Lambda::Function",
                    "AWS::Lambda::Version",
                    "AWS::IAM::Role",
                    "AWS::Logs::LogGroup",
                ],
                "agentcore-runtime": ["AWS::BedrockAgentCore::Runtime", "AWS::IAM::Role"],
                "agentcore-chat-runtime": ["AWS::BedrockAgentCore::Runtime", "AWS::IAM::Role"],
                "agentcore-endpoint": ["AWS::BedrockAgentCore::RuntimeEndpoint", "AWS::Logs::LogGroup"],
                "agentcore-chat-endpoint": ["AWS::BedrockAgentCore::RuntimeEndpoint", "AWS::Logs::LogGroup"],
                "routing": [
                    "AWS::CloudWatch::Alarm",
                    "AWS::Events::Rule",
                    "AWS::Lambda::EventSourceMapping",
                    "AWS::SNS::Subscription",
                    "AWS::IAM::Role",
                    "AWS::Lambda::Permission",
                ],
                "observation-foundation": ["AWS::SQS::Queue", "AWS::SNS::Subscription"],
                "observation-runtime": [
                    "AWS::Lambda::Function",
                    "AWS::Lambda::Version",
                    "AWS::IAM::Role",
                    "AWS::Logs::LogGroup",
                ],
                "observations": [
                    "AWS::Events::Rule",
                    "AWS::CloudWatch::Dashboard",
                    "AWS::CloudWatch::Alarm",
                    "AWS::Lambda::Permission",
                ],
            }.get(stage, []),
        }
        for stage in result["stages"]
        if stage in durable_ops.STAGES
    }
    result["preview_limit"] = (
        "Bootstrap templates are exact; later runtime resources resolve collected AWS outputs and immutable artifact versions during apply. Actual change sets are inspected before execution. No invoice/free-tier estimate or production qualification."
    )
    result["permission_screen"] = deployment_preflight.permission_requests(
        spec, {**config, "_initial_access": access}
    )
    result["plan_hash"] = digest(result)
    return result


def factory(profile):
    session = boto3.Session(profile_name=profile)
    return lambda service, region: session.client(
        service,
        region_name=region,
        config=Config(
            connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 2, "mode": "standard"}
        ),
    )


class Driver:
    def __init__(self, planned, directory):
        self.plan, self.directory = planned, directory
        self.env = {**os.environ, "AWS_EC2_METADATA_DISABLED": "true", "PYTHON_DOTENV_DISABLED": "1"}
        if planned["profile"]:
            # A named profile must not silently lose to ambient static credentials.
            for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
                self.env.pop(key, None)
            self.env["AWS_PROFILE"] = planned["profile"]
        self.clients = factory(planned["profile"])

    def command(self, module, arguments, output=None):
        command = [
            sys.executable,
            "-m",
            "infra.operator",
            "--profile",
            self.plan["profile"] or "",
            "--module",
            module,
            "--",
            *map(str, arguments),
        ]
        if output:
            command += ["--output", str(output)]
        # Do not stream raw cloud errors, request payloads or credentials to users.
        with (self.directory / "operations.log").open("ab") as log:
            os.chmod(log.name, 0o600)
            result = subprocess.run(
                command, cwd=ROOT, env=self.env, stdout=log, stderr=log, timeout=600, umask=0o077
            )
        if result.returncode == PendingConfirmation.EXIT_CODE and module == "infra.durable_ops" and output:
            raise confirmation_wait(json.loads(output.read_text())["recipients"])
        if result.returncode:
            raise VerificationError(
                f"{module} failed; inspect private operations.log and repair before resuming"
            )
        return json.loads(output.read_text()) if output else None

    def op(self, bundle, command, **kwargs):
        arguments = [command, "--bundle", self.directory / "bundle", "--review-hash", bundle["review_hash"]]
        for key, value in kwargs.items():
            if value is not None:
                arguments += ["--" + key.replace("_", "-")]
                if value != "":
                    arguments.append(value)
        return self.command("infra.durable_ops", arguments, self.directory / "operation.json")

    def render(self, bindings):
        private_json(self.directory / "bindings.json", bindings)
        p = self.plan["paths"]
        current_spec = load(p["spec"])
        if (
            current_spec != self.plan["spec"]
            or durable.load_config(p["runtime_config"], current_spec) != self.plan["runtime_config"]
        ):
            raise VerificationError(
                "Customer configuration changed during deployment; stop and review a new plan"
            )
        current_source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if current_source != self.plan["source_sha"]:
            raise VerificationError("Source revision changed during deployment")
        return durable.render(
            Path(p["spec"]),
            Path(p["runtime_config"]),
            self.directory / "bundle",
            self.directory / "build/pipeline",
            self.directory / "bindings.json",
            self.directory / "build/tools",
            self.directory / "build/host"
            if self.plan["runtime_config"]["runtime_target"] == "agentcore"
            else None,
            self.directory / "build/observation" if "observability" in self.plan["spec"] else None,
        )

    def build(self):
        p = self.plan["paths"]
        builds = self.directory / "build"
        # Build commands output a directory, not operation JSON.
        commands = [
            (
                "infra",
                ["build", "--spec", p["spec"], "--wheelhouse", p["wheelhouse"], "--output", builds / "tools"],
            ),
            ("scripts.build_pipeline", ["--wheelhouse", p["wheelhouse"], "--output", builds / "pipeline"]),
        ]
        if self.plan["runtime_config"]["runtime_target"] == "agentcore":
            commands.append(
                (
                    "scripts.build_lambdas",
                    [
                        "--function",
                        "incident_investigate",
                        "--architecture",
                        "arm64",
                        "--wheelhouse",
                        p["wheelhouse"],
                        "--output",
                        builds / "host",
                    ],
                )
            )
        if "observability" in self.plan["spec"]:
            commands.append(
                (
                    "scripts.build_observations",
                    [
                        "--spec",
                        p["spec"],
                        "--wheelhouse",
                        p["wheelhouse"],
                        "--output",
                        builds / "observation",
                    ],
                )
            )
        for module, arguments in commands:
            self.command(module, arguments)

    def inspect_stack(self, bundle, stage):
        info = bundle["stages"][stage]
        client = self.clients("cloudformation", info["region"])
        try:
            response = client.describe_stacks(StackName=info["stack"])["Stacks"][0]
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ValidationError" and "does not exist" in exc.response[
                "Error"
            ].get("Message", ""):
                return None
            raise
        expected = dict((r["Key"], r["Value"]) for r in templates.tagged(bundle["spec"]))
        actual = dict((r["Key"], r["Value"]) for r in response.get("Tags", []))
        if any(actual.get(k) != v for k, v in expected.items()):
            raise VerificationError("Existing stack is not owned by this deployment")
        return response

    def template_matches(self, bundle, stage):
        info = bundle["stages"][stage]
        body = self.clients("cloudformation", info["region"]).get_template(StackName=info["stack"])[
            "TemplateBody"
        ]
        return (
            templates.template_hash(json.loads(body) if isinstance(body, str) else body)
            == info["template_hash"]
        )

    def stage(self, bundle, stage, record, save, *, receipt=None, retirement=None):
        info = bundle["stages"][stage]
        client = self.clients("cloudformation", info["region"])
        if record.get("template_hash") != info["template_hash"]:
            if record:
                raise VerificationError("Checkpoint template changed; do not reuse a deployment journal")
            record.update(template_hash=info["template_hash"], status="INTENT")
            save()  # Durable intent before any request; recover lost responses by name.
        current = self.inspect_stack(bundle, stage)
        if (
            current
            and current["StackStatus"] != "REVIEW_IN_PROGRESS"
            and current["StackStatus"].endswith("_IN_PROGRESS")
        ):
            raise Waiting(
                f"{stage}: CloudFormation is still processing; rerun apply to resume", automatic=True
            )
        if (
            current
            and current["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
            and self.template_matches(bundle, stage)
        ):
            if info["create_only"]:
                self.op(bundle, "seal-runtime", stage=stage)
            record["status"] = "COMPLETE"
            save()
            return
        if current and current["StackStatus"] not in {
            "CREATE_COMPLETE",
            "UPDATE_COMPLETE",
            "REVIEW_IN_PROGRESS",
        }:
            raise VerificationError(
                f"{stage}: stack needs operator recovery; rollback/failure is not success"
            )
        if current and info["create_only"] and current["StackStatus"] != "REVIEW_IN_PROGRESS":
            raise VerificationError("Immutable release exists with a different template; use a new release")
        cs_name = "review-" + bundle["review_hash"][:24]
        try:
            cs = client.describe_change_set(StackName=info["stack"], ChangeSetName=cs_name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"ChangeSetNotFound", "ChangeSetNotFoundException"}:
                # A missing stack can return ValidationError; verify exact absence.
                if not (
                    current is None
                    and exc.response["Error"]["Code"] == "ValidationError"
                    and "does not exist" in exc.response["Error"].get("Message", "")
                ):
                    raise
            # Existing REVIEW_IN_PROGRESS stack means CreateChangeSet was accepted
            # but its response was lost. It is safe only with our exact intent.
            if current and current["StackStatus"] == "REVIEW_IN_PROGRESS":
                raise VerificationError("Pending stack has no matching change set; inspect before retry")
            self.op(bundle, "change-set", stage=stage)
            raise Waiting(f"{stage}: change set requested; rerun apply to resume", automatic=True)
        if (
            cs["Status"] in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}
            or cs.get("ExecutionStatus") == "EXECUTE_IN_PROGRESS"
        ):
            raise Waiting(f"{stage}: change set is still processing", automatic=True)
        if cs["Status"] == "FAILED":
            # An unchanged stable stack is valid only if its actual template matches.
            if (
                current
                and current["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
                and self.template_matches(bundle, stage)
            ):
                record["status"] = "COMPLETE"
                save()
                return
            raise VerificationError(f"{stage}: change set failed; inspect private AWS events")
        inspected = self.op(bundle, "inspect", stage=stage, change_set=cs_name)
        # Removing/replacing existing resources is never automatically approved.
        changes = inspected["changes"]
        if any(
            r.get("Type") != "Resource"
            or r.get("ResourceChange", {}).get("Action") not in {"Add", "Modify"}
            or r.get("ResourceChange", {}).get("Replacement", "False") != "False"
            for r in changes
        ):
            raise VerificationError(
                "Change set deletes/replaces resources; separate operator review required"
            )
        private_json(self.directory / f"review-{stage}.json", inspected)
        record.update(
            status="EXECUTION_INTENT",
            change_set=inspected["change_set"],
            change_hash=inspected["review_hash"],
        )
        save()
        options = dict(
            stage=stage, change_set=inspected["change_set"], change_set_hash=inspected["review_hash"]
        )
        if receipt:
            private_json(self.directory / "canary.json", receipt)
            options["receipt"] = self.directory / "canary.json"
        if retirement:
            private_json(self.directory / "retirement.json", retirement)
            options["retirement_plan"] = self.directory / "retirement.json"
        self.op(bundle, "execute", **options)
        raise Waiting(f"{stage}: execution requested; rerun apply to resume", automatic=True)


def deploy(planned, directory, driver, *, allow_model=False, ticket=None, retry_canary=False):
    journal = directory / "state.json"
    state = (
        json.loads(journal.read_text())
        if journal.exists()
        else {
            "version": 1,
            "plan_hash": planned["plan_hash"],
            "bindings": {},
            "stages": {},
            "status": "RUNNING",
        }
    )
    if state.get("version") != 1 or state.get("plan_hash") != planned["plan_hash"]:
        raise VerificationError("Configuration/source changed; create a new deployment work directory")
    # Without an identity block this is local single-user mode: no identity stages, grants or tickets.
    identity_mode = "identity" in planned["runtime_config"]

    def save():
        private_json(journal, state)

    def stage(stage_name, checkpoint=None, *, unbound=False, **kwargs):
        checkpoint = checkpoint or stage_name
        bindings = {k: v for k, v in state["bindings"].items() if not (unbound and k == "identity")}
        bundle = driver.render(bindings)
        if stage_name not in bundle["stages"]:
            raise VerificationError("Required deployment bindings are missing")
        record = state["stages"].setdefault(checkpoint, {})
        driver.stage(bundle, stage_name, record, save, **kwargs)
        return bundle

    def collect(stage_name, key):
        bundle = driver.render(state["bindings"])
        state["bindings"][key] = driver.op(bundle, "collect", stage=stage_name)
        save()

    if retry_canary:
        if not allow_model or (identity_mode and ticket is None):
            raise VerificationError(
                "Retry requires a private ticket and explicit paid invocation authorization"
                if identity_mode
                else "Retry requires explicit paid invocation authorization"
            )
        state.setdefault("canary_history", []).append(
            {
                "previous_receipt": state.pop("canary", None),
                "previous_request": state.pop("canary_requested", False),
                "reason": "Explicit operator --retry-canary",
            }
        )
        save()
    save()
    try:
        # Recheck identity and permissions on every resume. Capacity accounts for
        # already verified own reservations, never trusts journal-only values.
        # Investigate (2) and Chat (1) are reserved only by identity-enabled templates.
        remaining = planned["runtime_config"]["initial_reserved_concurrency"] + (3 if identity_mode else 0)
        for stage_name, logicals in [
            (
                "durable-runtime",
                [("Initial", planned["runtime_config"]["initial_reserved_concurrency"])]
                + ([("Investigate", 2)] if identity_mode else []),
            ),
            *([("chat-runtime", [("Chat", 1)])] if identity_mode else []),
        ]:
            record = state["stages"].get(stage_name)
            if record:
                bundle = driver.render(state["bindings"]) if state.get("built") else None
                current = driver.inspect_stack(bundle, stage_name) if bundle else None
                if (
                    current
                    and current["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
                    and driver.template_matches(bundle, stage_name)
                ):
                    client = driver.clients("lambda", planned["spec"]["monitor_region"])
                    output = driver.op(bundle, "collect", stage=stage_name)
                    for logical, amount in logicals:
                        arn = output[logical + "VersionArn"]
                        if (
                            client.get_function_concurrency(FunctionName=arn.rsplit(":", 1)[0]).get(
                                "ReservedConcurrentExecutions"
                            )
                            == amount
                        ):
                            remaining -= amount
        report = getattr(driver, "preflight", None)
        if report is None:
            report = deployment_preflight.check(planned, driver.clients, remaining_reserved=remaining)
            driver.preflight = report
        private_json(directory / "preflight.json", report)
        if report["status"] != "SIMULATED":
            raise VerificationError("Permission preflight blocked; inspect private preflight.json")
        if not state.get("built"):
            driver.build()
            state["built"] = True
            save()
        for name in (
            "foundation-tools",
            "foundation-monitor",
            "durable-foundation",
            *(("identity-foundation", "identity-secret") if identity_mode else ()),
        ):
            if name == "identity-foundation":
                if "identity-foundation-bound" not in state["stages"]:
                    stage(name, unbound=True)
            else:
                stage(name)
        collect("durable-foundation", "foundation")
        bundle = driver.render(state["bindings"])
        if identity_mode and "identity" not in state["bindings"]:
            state["bindings"]["identity"] = driver.op(bundle, "identity-version")
            save()
        if "secret" not in state["bindings"]:
            state["bindings"]["secret"] = driver.op(bundle, "cursor-version")
            save()
        if model_api(planned["spec"]) and "model_secret" not in state["bindings"]:
            # Read-only: pins the out-of-band key secret's current version; the value is never read here.
            state["bindings"]["model_secret"] = driver.op(bundle, "model-secret-version")
            save()
        if identity_mode:
            # The second identity foundation adds the exact-version issuer grants.
            stage("identity-foundation", "identity-foundation-bound")
            bundle = driver.render(state["bindings"])
            driver.command(
                "infra.identity_ops",
                [
                    "pin-secret-version",
                    "--bundle",
                    directory / "bundle",
                    "--review-hash",
                    bundle["review_hash"],
                ],
                directory / "pin.json",
            )
        if "tool_artifacts" not in state["bindings"]:
            bundle = driver.render(state["bindings"])
            state["bindings"]["tool_artifacts"] = driver.op(
                bundle, "upload", build_dir=directory / "build/tools", artifact_kind="tools"
            )
            save()
        stage("owned-tools")
        collect("owned-tools", "tools")
        for kind, key in [
            ("host", "host_artifact"),
            ("observation", "observation_artifacts"),
            ("pipeline", "artifacts"),
        ]:
            if (
                kind == "host"
                and planned["runtime_config"]["runtime_target"] != "agentcore"
                or kind == "observation"
                and "observability" not in planned["spec"]
            ):
                continue
            if key not in state["bindings"]:
                bundle = driver.render(state["bindings"])
                state["bindings"][key] = driver.op(
                    bundle, "upload", build_dir=directory / "build" / kind, artifact_kind=kind
                )
                save()
        if planned["runtime_config"]["runtime_target"] == "agentcore":
            for suffix, candidate, binding in [
                ("agentcore", "agentcore_candidate", "agentcore"),
                *(
                    [("agentcore-chat", "agentcore_chat_candidate", "agentcore_chat")]
                    if identity_mode
                    else []
                ),
            ]:
                stage(suffix + "-runtime")
                collect(suffix + "-runtime", candidate)
                # RuntimeArn is unused candidate metadata; render expects exact ID/version.
                state["bindings"][candidate].pop("RuntimeArn", None)
                save()
                stage(suffix + "-endpoint")
                collect(suffix + "-endpoint", binding)
        stage("durable-runtime")
        collect("durable-runtime", "versions")
        if identity_mode:
            stage("chat-runtime")
            collect("chat-runtime", "chat_version")
        if "observability" in planned["spec"]:
            stage("observation-foundation")
            stage("observation-runtime")
            collect("observation-runtime", "observation_versions")
            bundle = driver.render(state["bindings"])
            driver.op(bundle, "seed-health")
        bundle = driver.render(state["bindings"])
        driver.op(bundle, "verify-candidate")
        # This output has references only; credentials and IdP secrets stay separate.
        connection = json.loads((directory / "bundle/routing.json").read_text())["Outputs"][
            "RuntimeConnection"
        ]["Value"]
        env = {
            **json.loads(connection),
            "MONITOR_REGION": planned["spec"]["monitor_region"],
            "INCIDENT_TABLE": state["bindings"]["foundation"]["TableName"],
            "REPORT_BUCKET": state["bindings"]["foundation"]["EvidenceBucket"],
        }
        if identity_mode:
            issuer = driver.op(bundle, "collect", stage="identity-foundation")["SessionIssuerRoleArn"]
            private_json(
                directory / "ui-connection.json",
                {
                    "environment": env,
                    "staging_issuer_role_arn": issuer,
                    "operational_role": "Available only after routing verification",
                    "provider_setup": "Configure privately; see deployment automation guide",
                },
            )
        for index, request in enumerate(planned["initial_access"]):
            request_file = directory / f"access-{index}.json"
            private_json(request_file, request)
            args = [
                "--bundle",
                directory / "bundle",
                "--review-hash",
                bundle["review_hash"],
                "--request",
                request_file,
            ]
            grant_file = directory / f"grant-{index}.json"
            diff = driver.command("infra.identity_ops", ["grant-plan", *args], grant_file)
            before, after = diff["before"], diff["after"]
            if before and all(before.get(k) == v for k, v in after.items() if k != "epoch"):
                continue
            driver.command(
                "infra.identity_ops",
                ["grant-apply", *args, "--grant-plan", grant_file],
                directory / f"grant-result-{index}.json",
            )
        if planned["spec"]["environment"] != "staging":
            raise Waiting(
                "Production candidates provisioned; existing gates require separately qualified staging and production cutover"
            )
        if not allow_model or (identity_mode and ticket is None):
            raise Waiting(
                "Candidate ready: configure OIDC, log in with MFA and export the private staging ticket; resume with --allow-model-invocation --access-ticket-file"
                if identity_mode
                else "Candidate ready: resume with --allow-model-invocation"
            )
        # Paid work is not blindly repeated on an ambiguous failure.
        receipt = state.get("canary")
        if receipt:
            from infra.release import require_receipt

            try:
                require_receipt(bundle, receipt)
            except VerificationError:
                raise Waiting(
                    "Canary receipt expired/differs; inspect it and explicitly use --retry-canary for new paid work"
                ) from None
        elif state.get("canary_requested"):
            raise Waiting(
                "Previous paid canary outcome is ambiguous; inspect private result before explicitly authorizing --retry-canary"
            )
        else:
            state["canary_requested"] = True
            save()
            receipt = driver.op(bundle, "canary", allow_model_invocation="", access_ticket_file=ticket)
            state["canary"] = receipt
            save()
        private_json(directory / "canary.json", receipt)
        retirement = driver.op(bundle, "retirement-plan", receipt=directory / "canary.json")
        if retirement.get("disable_alarms") or retirement.get("unsubscribe"):
            raise Waiting(
                "Legacy resource retirement requires separate review; automation never deletes subscriptions or alarms"
            )
        stage("routing", receipt=receipt, retirement=retirement)
        if "observability" in planned["spec"]:
            stage("observations")
        driver.op(bundle, "verify-routing")
        if "observability" in planned["spec"]:
            driver.op(bundle, "verify-observation-routing")
        role = driver.op(bundle, "collect", stage="routing")["UiRoleArn"]
        private_json(
            directory / "ui-connection.json",
            {
                "environment": env,
                "ui_role_arn": role,
                **(
                    {"staging_issuer_role_arn": issuer, "provider_setup": "Configure privately"}
                    if identity_mode
                    else {}
                ),
            },
        )
        state["status"] = "INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING"
        state["next"] = (
            "Confirm notification subscriptions and actual delivery; complete customer live acceptance. Investigation remains paused."
        )
        save()
    except Waiting as exc:
        state["status"] = "WAITING"
        state["auto_resume"] = exc.automatic
        state["next"] = str(exc)
        save()
    except Exception:
        state["status"] = "FAILED"
        state["next"] = "Repair the recorded failed step, then resume the same reviewed configuration"
        save()
        raise
    return {
        "status": state["status"],
        "auto_resume": state.get("auto_resume", False) if state["status"] == "WAITING" else False,
        "next": state["next"],
        "completed_stages": [k for k, v in state["stages"].items() if v.get("status") == "COMPLETE"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "dry-run", "check", "apply", "status"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--plan-hash")
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=900,
        help="Automatically wait/resume AWS steps, up to 3600 seconds; 0 advances once",
    )
    parser.add_argument("--allow-model-invocation", action="store_true")
    parser.add_argument(
        "--retry-canary",
        action="store_true",
        help="Explicitly authorize replacing an expired or ambiguous paid canary after inspection",
    )
    parser.add_argument("--access-ticket-file", type=Path)
    parser.add_argument(
        "--identity",
        action="store_true",
        help="init only: start from the opt-in individual-identity (OIDC) runtime example",
    )
    args = parser.parse_args()
    if args.identity and args.command != "init":
        parser.error("--identity applies to init only; identity mode follows runtime.json")
    try:
        directory = private_dir(args.work_dir)
        with locked(directory):
            if args.command == "init":
                import shutil

                targets = {
                    "deployment.json": ROOT / "examples/deployment.example.json",
                    "runtime.json": ROOT
                    / (
                        "examples/identity.example.json" if args.identity else "examples/durable.example.json"
                    ),
                }
                if any((directory / p).exists() for p in [*targets, "automation.json"]):
                    raise VerificationError("Init never overwrites existing customer files")
                for name, source in targets.items():
                    shutil.copyfile(source, directory / name)
                    os.chmod(directory / name, 0o600)
                private_json(
                    directory / "automation.json",
                    {
                        "version": 1,
                        "spec": "deployment.json",
                        "runtime_config": "runtime.json",
                        "profile": None,
                        "wheelhouse": str(ROOT / ".build/wheels"),
                        "initial_access": [],
                    },
                )
                print(
                    "Created private templates. Fill deployment.json/runtime.json/automation.json; see docs/DEPLOY.md. Reference inputs cannot deploy AWS."
                    + (
                        ""
                        if args.identity
                        else " Local single-user mode; add --identity at init for individual OIDC sign-in."
                    )
                )
                return 0
            if args.command == "status":
                state = json.loads((directory / "state.json").read_text())
                print(json.dumps({k: state.get(k) for k in ("status", "next", "plan_hash")}, indent=2))
                return 0
            if not args.config:
                raise VerificationError("--config is required")
            planned = plan(args.config)
            if args.command == "dry-run":
                private_json(directory / "plan.json", planned)
                for instance in planned["spec"]["instances"]:
                    private_json(
                        directory / "collector-examples" / (instance["id"] + ".json"),
                        cwagent(planned["spec"], instance),
                    )
                print(
                    json.dumps(
                        {
                            "plan_hash": planned["plan_hash"],
                            "reference_only": planned["spec"]["reference_only"],
                            "stages": planned["stages"],
                            "runtime_target": planned["runtime_config"]["runtime_target"],
                            "resources": planned["resources"],
                            "preview_limit": planned["preview_limit"],
                            "automatic_activation": False,
                            "manual": planned["manual"],
                            "details": str(directory / "plan.json"),
                        },
                        indent=2,
                    )
                )
                return 0
            if planned["spec"]["reference_only"]:
                raise VerificationError("Synthetic reference inputs cannot check/deploy AWS")
            if args.command == "check":
                report = deployment_preflight.check(planned, factory(planned["profile"]))
                private_json(directory / "preflight.json", report)
                print(
                    json.dumps(
                        {
                            "status": report["status"],
                            "permission_blockers": len(report["blockers"]),
                            "details": str(directory / "preflight.json"),
                        },
                        indent=2,
                    )
                )
                return 0 if not report["blockers"] else 1
            if args.plan_hash != planned["plan_hash"]:
                raise VerificationError("Run dry-run and supply its exact --plan-hash before apply")
            if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
                raise VerificationError("Apply requires a clean reviewed source checkout")
            identity_mode = "identity" in planned["runtime_config"]
            if args.access_ticket_file and not identity_mode:
                raise VerificationError(
                    "--access-ticket-file applies only with an identity block in runtime.json"
                )
            if args.retry_canary and (
                not args.allow_model_invocation or (identity_mode and not args.access_ticket_file)
            ):
                raise VerificationError(
                    "--retry-canary needs --allow-model-invocation and a private ticket"
                    if identity_mode
                    else "--retry-canary needs --allow-model-invocation"
                )
            if args.access_ticket_file and not args.allow_model_invocation:
                raise VerificationError("A canary ticket requires explicit paid model authorization")
            if args.access_ticket_file:
                ticket = args.access_ticket_file
                if (
                    ticket.is_symlink()
                    or ticket.stat().st_mode & 0o077
                    or ticket.parent.stat().st_mode & 0o077
                    or not 1 <= ticket.stat().st_size <= 1024
                ):
                    raise VerificationError(
                        "Canary ticket and parent directory must be private, with a bounded nonempty ticket"
                    )
            if not 0 <= args.wait_seconds <= 3600:
                raise VerificationError("--wait-seconds must be between 0 and 3600")
            driver = Driver(planned, directory)
            deadline = time.monotonic() + args.wait_seconds
            result = deploy(
                planned,
                directory,
                driver,
                allow_model=args.allow_model_invocation,
                ticket=args.access_ticket_file,
                retry_canary=args.retry_canary,
            )
            while result["status"] == "WAITING" and result["auto_resume"] and time.monotonic() < deadline:
                print(json.dumps({"status": "WAITING", "next": result["next"]}), flush=True)
                time.sleep(min(5, max(0, deadline - time.monotonic())))
                result = deploy(
                    planned,
                    directory,
                    driver,
                    allow_model=args.allow_model_invocation,
                    ticket=args.access_ticket_file,
                )
            print(json.dumps(result, indent=2))
            return 2 if result["status"] == "WAITING" else 0
    except (
        VerificationError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        BotoCoreError,
        ClientError,
        subprocess.SubprocessError,
    ) as exc:
        if isinstance(exc, ClientError):
            private_json(
                directory / "error.json",
                {
                    "status": "FAILED",
                    "operation": exc.operation_name,
                    "error_code": exc.response.get("Error", {}).get("Code", "UNKNOWN"),
                    "next": "Repair the named API permission/prerequisite; never treat AccessDenied as absence",
                },
            )
        # Known local verification messages contain no raw cloud payloads.
        print(
            str(exc)
            if isinstance(exc, VerificationError)
            else f"Deployment failed ({type(exc).__name__}); no success claimed. Inspect private evidence.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
