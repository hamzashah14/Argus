import copy
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from infra import reconcile, release, templates
from infra.spec import ROOT, alarm_descriptors, load, log_groups, metric_catalog, topic_arn
from infra.verify import (
    VerificationError,
    assert_account,
    assert_concurrency,
    assert_stack_absent,
    coverage,
    exact_metric_exists,
    put_targets_checked,
)
from scripts.validate_infrastructure import examples


@pytest.fixture
def spec():
    return {**load(ROOT / "infra/deployment.example.json"), "reference_only": False}


def test_same_and_split_region_ownership(spec):
    for region in ("eu-central-1", "us-east-1"):
        spec["bedrock_region"] = region
        rendered = examples(spec)
        for stage, template in rendered.items():
            expected = spec[release.STAGES[stage]]
            assert template["Metadata"]["Kira"]["ExpectedRegion"] == expected
            assert template["Metadata"]["Kira"]["Environment"] == "staging"
        assert templates.bucket_name(spec, "tools") != templates.bucket_name(spec, "monitor")


def test_staging_and_production_have_disjoint_physical_names(spec):
    def names(env):
        target = {**spec, "environment": env}
        return {
            resource["Properties"][key]
            for t in examples(target).values()
            for resource in t["Resources"].values()
            for key in ("FunctionName", "BucketName", "TopicName", "AlarmName", "LogGroupName", "AgentName")
            if isinstance(resource["Properties"].get(key), str)
        }

    assert not names("staging") & names("production")


def test_new_candidate_never_references_previous_release(spec):
    before = examples(spec)
    after = examples({**spec, "release_id": "next002"})
    for stage in release.IMMUTABLE:
        assert spec["release_id"] not in json.dumps(after[stage])
        assert release.stack_name(spec, stage) != release.stack_name({**spec, "release_id": "next002"}, stage)
    assert before["tools"]["Resources"]["Agent"]["Properties"]["AutoPrepare"] is False
    for logical in ("Logs", "Metrics"):
        permission = before["tools"]["Resources"][logical + "Permission"]["Properties"]
        assert permission["FunctionName"] == {"Ref": logical + "Version"}
        assert permission["SourceArn"] == {"Fn::GetAtt": ["Agent", "AgentArn"]}


def test_release_specific_fallback_remains_isolated(spec):
    spec["executor_mode"] = "release-name"
    t = examples(spec)["tools"]
    assert t["Resources"]["LogsPermission"]["Properties"]["FunctionName"] == templates.att("Logs")
    assert spec["release_id"] in t["Resources"]["Logs"]["Properties"]["FunctionName"]


def test_retention_and_exact_artifact_versions(spec):
    for template in examples(spec).values():
        for resource in template["Resources"].values():
            if resource["Type"] in {
                "AWS::S3::Bucket",
                "AWS::SecretsManager::Secret",
                "AWS::Logs::LogGroup",
                "AWS::Lambda::Version",
                "AWS::Lambda::Function",
            }:
                assert resource["DeletionPolicy"] == resource["UpdateReplacePolicy"] == "Retain"
            if resource["Type"] == "AWS::Lambda::Function":
                assert resource["Properties"]["Code"]["S3ObjectVersion"]
            if resource["Type"] == "AWS::Lambda::Version":
                assert resource["Properties"]["CodeSha256"]


def test_roles_cannot_deploy_and_only_log_tool_reads_secret(spec):
    rendered = examples(spec)
    allowed_secret_roles = []
    for stage, template in rendered.items():
        for logical, resource in template["Resources"].items():
            if resource["Type"] != "AWS::IAM::Role":
                continue
            assert resource["Properties"]["Path"] == "/kira/staging/"
            for policy in resource["Properties"]["Policies"]:
                for statement in policy["PolicyDocument"]["Statement"]:
                    actions = statement["Action"]
                    actions = [actions] if isinstance(actions, str) else actions
                    assert not any(
                        action == "*"
                        or action.startswith(
                            (
                                "iam:",
                                "cloudformation:Create",
                                "cloudformation:Update",
                                "lambda:Update",
                                "lambda:Create",
                                "sts:AssumeRole",
                            )
                        )
                        for action in actions
                    )
                    if "secretsmanager:GetSecretValue" in actions:
                        allowed_secret_roles.append((stage, logical))
                        assert ":secret:kira-staging/log-cursor-" in statement["Resource"]
    assert allowed_secret_roles == [("tools", "LogsRole")]
    log_policy = rendered["tools"]["Resources"]["LogsRole"]["Properties"]["Policies"][0]["PolicyDocument"][
        "Statement"
    ]
    query = next(s for s in log_policy if "logs:StartQuery" in s["Action"])
    assert all(":log-group:/kira/staging/i-0123456789abcdef0/" in arn for arn in query["Resource"])
    assert query["Condition"]["StringEquals"]["aws:RequestedRegion"] == spec["monitor_region"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.update(unknown=True),
        lambda s: s.update(environment="prod"),
        lambda s: s.update(reserved_concurrency=0),
        lambda s: s.update(model_arns=["*"]),
        lambda s: s.update(ui_principal_arn=s["deployment_role_arn"]),
        lambda s: s["instances"].append(copy.deepcopy(s["instances"][0])),
    ],
)
def test_invalid_spec_fails_locally(spec, tmp_path, mutation):
    mutation(spec)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError):
        load(path)


def test_catalog_and_cwagent_share_inventory(spec):
    from infra.spec import cwagent

    catalog = metric_catalog(spec)
    process = next(d for d in catalog if d["id"].endswith("process"))
    assert process["dimensions"]["exe"] == "nginx"
    assert process["dimensions"]["pid_finder"] == "native"
    config = cwagent(spec, spec["instances"][0])
    assert config["metrics"]["metrics_collected"]["procstat"][0]["exe"] == "nginx"
    assert all(
        i["log_group_name"] in log_groups(spec)
        for i in config["logs"]["logs_collected"]["files"]["collect_list"]
    )
    nginx = next(d for d in catalog if d["id"].endswith("nginx"))
    assert nginx["namespace"] == "kira/staging/Nginx" and nginx["dimensions"] == {}


def denied():
    return ClientError({"Error": {"Code": "AccessDenied", "Message": "private detail"}}, "Read")


def test_wrong_account_and_existing_release_block_writes(spec):
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "999999999999"}
    with pytest.raises(VerificationError):
        assert_account(sts, spec)
    cfn = MagicMock()
    with pytest.raises(VerificationError):
        assert_stack_absent(cfn, "existing")
    cfn.describe_stacks.side_effect = denied()
    with pytest.raises(ClientError):
        assert_stack_absent(cfn, "existing")


@pytest.mark.parametrize(
    "limit,requested,passes",
    [(10, 1, False), (100, 1, False), (102, 2, True), (101, 2, False), (10, None, True), (10, 0, True)],
)
def test_reserved_capacity_fails_closed(limit, requested, passes):
    client = MagicMock()
    client.get_account_settings.return_value = {"AccountLimit": {"UnreservedConcurrentExecutions": limit}}
    if passes:
        assert_concurrency(client, requested)
    else:
        with pytest.raises(VerificationError):
            assert_concurrency(client, requested)


@pytest.mark.parametrize(
    "response",
    [
        {"FailedEntryCount": 1, "FailedEntries": [{"TargetId": "alarms"}]},
        {},
        {"FailedEntryCount": 0, "FailedEntries": [{"TargetId": "alarms"}]},
    ],
)
def test_partial_eventbridge_registration_never_succeeds(response):
    events = MagicMock()
    events.put_targets.return_value = response
    with pytest.raises(VerificationError):
        put_targets_checked(events, Rule="test", Targets=[])


def test_metric_discovery_paginated_exact_and_denied(spec):
    client = MagicMock()
    descriptor = alarm_descriptors(spec)[0]
    client.list_metrics.side_effect = [
        {"Metrics": [{"Dimensions": []}], "NextToken": "two"},
        {"Metrics": [{"Dimensions": [{"Name": "InstanceId", "Value": spec["instances"][0]["id"]}]}]},
    ]
    assert exact_metric_exists(client, descriptor)
    assert client.list_metrics.call_args.kwargs["NextToken"] == "two"
    client.list_metrics.side_effect = denied()
    with pytest.raises(ClientError):
        exact_metric_exists(client, descriptor)


def good_clients(spec):
    services = {name: MagicMock() for name in ("sts", "lambda", "ec2", "cloudwatch", "logs")}
    services["sts"].get_caller_identity.return_value = {"Account": spec["account_id"]}
    services["ec2"].describe_instances.return_value = {
        "Reservations": [
            {"Instances": [{"InstanceId": spec["instances"][0]["id"], "State": {"Name": "running"}}]}
        ]
    }
    descriptors = alarm_descriptors(spec)
    services["cloudwatch"].list_metrics.side_effect = lambda **kw: {
        "Metrics": [
            {"Dimensions": [{"Name": k, "Value": v} for k, v in d["dimensions"].items()]}
            for d in descriptors
            if d["metric_name"] == kw["MetricName"] and d["namespace"] == kw["Namespace"]
        ]
    }
    services["logs"].test_metric_filter.return_value = {"matches": [{"eventNumber": 1}]}
    return services, lambda service, region: services[service]


def test_coverage_missing_and_denied_are_failures(spec):
    services, factory = good_clients(spec)
    assert coverage(spec, factory)["status"] == "PASS"
    services["cloudwatch"].list_metrics.side_effect = None
    services["cloudwatch"].list_metrics.return_value = {"Metrics": []}
    with pytest.raises(VerificationError, match="Required metric"):
        coverage(spec, factory)
    services["cloudwatch"].list_metrics.side_effect = denied()
    with pytest.raises(ClientError):
        coverage(spec, factory)


def test_bad_nginx_fixture_blocks_promotion(spec):
    services, factory = good_clients(spec)
    services["logs"].test_metric_filter.return_value = {"matches": [{"eventNumber": 1}, {"eventNumber": 2}]}
    with pytest.raises(VerificationError, match="filter"):
        coverage(spec, factory)


def test_retirement_diff_preserves_unrelated_history_and_removes_old_recipient(spec):
    retired = {"type": "AWS::CloudWatch::Alarm", "id": "kira-staging-retired-cpu"}
    old = {
        "type": "AWS::SNS::Subscription",
        "id": topic_arn(spec, "reports") + ":old",
        "topic": topic_arn(spec, "reports"),
        "endpoint": "former@example.invalid",
        "protocol": "email",
    }
    history = {"type": "AWS::Logs::LogGroup", "id": "/kira/staging/retired/application"}
    plan = reconcile.plan(spec, [retired, old, history], "worker")
    assert plan["disable_alarms"] == [retired["id"]] and plan["unsubscribe"] == [old]
    assert plan["preserve"] == [history["id"]]
    with pytest.raises(VerificationError):
        reconcile.plan(spec, [{**old, "topic": "unrelated"}], "worker")


def test_feature_disable_and_instance_removal_have_explicit_retirements(spec):
    original = alarm_descriptors(spec)
    changed = copy.deepcopy(spec)
    changed["instances"][0].update(resource_alarms=False, nginx_alarm=False, process_exe=None)
    plan = reconcile.plan(
        changed, [{"type": "AWS::CloudWatch::Alarm", "id": a["alarm_name"]} for a in original], "worker"
    )
    assert len(plan["disable_alarms"]) == 5
    changed["instances"][0]["id"] = "i-11111111111111111"
    plan = reconcile.plan(
        changed, [{"type": "AWS::CloudWatch::Alarm", "id": a["alarm_name"]} for a in original], "worker"
    )
    assert len(plan["disable_alarms"]) == 6


def test_changed_retirement_plan_cannot_mutate(spec):
    factory = MagicMock()
    factory.return_value.get_caller_identity.return_value = {"Account": spec["account_id"]}
    with patch("infra.reconcile.owned_resources", return_value=[]), pytest.raises(VerificationError):
        reconcile.apply(spec, factory, {"review_hash": "stale"}, "worker")
    factory.return_value.unsubscribe.assert_not_called()
    factory.return_value.disable_alarm_actions.assert_not_called()


def test_receipt_requires_exact_recent_candidate():
    bundle = {"review_hash": "this-release"}
    record = {
        "bundle_hash": "this-release",
        "status": "PASS",
        "canary_tools": ["fetch_logs", "fetch_metrics"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    release.require_receipt(bundle, record)
    for change in (
        {"bundle_hash": "other"},
        {"status": "FAIL"},
        {"canary_tools": ["fetch_logs"]},
        {"checked_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()},
    ):
        with pytest.raises(VerificationError):
            release.require_receipt(bundle, {**record, **change})


def test_local_bundle_tamper_detected(spec, tmp_path):
    bundle = release.render(ROOT / "infra/deployment.example.json", tmp_path)
    assert release.read_bundle(tmp_path, bundle["review_hash"])["spec"] == {**spec, "reference_only": True}
    path = tmp_path / "foundation-tools.json"
    value = json.loads(path.read_text())
    value["Resources"]["Artifacts"]["Properties"]["BucketName"] = "unrelated"
    path.write_text(json.dumps(value))
    with pytest.raises(VerificationError, match="Template"):
        release.read_bundle(tmp_path, bundle["review_hash"])


def test_cursor_uses_pinned_secret_and_does_not_refresh_to_current(monkeypatch):
    from kira import cursor

    cursor.secret_version.cache_clear()
    monkeypatch.setenv(
        "LOG_CURSOR_SECRET_ARN",
        "arn:aws:secretsmanager:eu-central-1:123456789012:secret:kira-staging/log-cursor-ABCDEF",
    )
    monkeypatch.setenv("LOG_CURSOR_SECRET_VERSION", "a" * 32)
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": "x" * 48}
    with patch("boto3.client", return_value=client):
        assert cursor.key() == cursor.key()
    client.get_secret_value.assert_called_once()
    assert client.get_secret_value.call_args.kwargs["VersionId"] == "a" * 32
    cursor.secret_version.cache_clear()


def test_packaged_log_scope_rejects_cross_instance_before_aws(tmp_path, monkeypatch):
    from tests.helpers import body, load_lambda

    logs = load_lambda("fetch_logs")
    path = tmp_path / "scope.json"
    group = "/aiops/i-0123456789abcdef0/application"
    path.write_text(json.dumps([group]))
    monkeypatch.setenv("LOG_SCOPE_FILE", str(path))
    with patch("boto3.client") as client:
        response = logs.lambda_handler(
            {
                "parameters": [
                    {"name": "instance_id", "value": "i-11111111111111111"},
                    {"name": "log_group_name", "value": group},
                ]
            },
            None,
        )
    assert body(response)["status"] == "error"
    client.assert_not_called()


def test_changed_log_prefix_replaces_filters_and_retains_old_groups(spec):
    old = templates.foundation(spec, "monitor")
    changed = {**spec, "log_segment": "v2"}
    new = templates.foundation(changed, "monitor")
    assert set(log_groups(spec)).isdisjoint(log_groups(changed))
    assert all(
        r["DeletionPolicy"] == "Retain"
        for r in old["Resources"].values()
        if r["Type"] == "AWS::Logs::LogGroup"
    )
    assert all(
        "/staging/v2/" in r["Properties"]["LogGroupName"]
        for r in new["Resources"].values()
        if r["Type"] == "AWS::Logs::MetricFilter"
    )


def test_already_disabled_retired_alarm_does_not_block_routing(spec):
    item = {"type": "AWS::CloudWatch::Alarm", "id": "retired", "actions_enabled": False}
    assert reconcile.plan(spec, [item], "worker")["disable_alarms"] == []


def test_ingestion_dispatch_notification_roles_have_separate_scopes(spec):
    rendered = examples(spec)
    roles = [
        rendered["foundation-monitor"]["Resources"][name] for name in ("IngestionRole", "NotificationRole")
    ]
    roles.append(rendered["worker"]["Resources"]["DispatchRole"])
    actions = [
        role["Properties"]["Policies"][0]["PolicyDocument"]["Statement"][0]["Action"] for role in roles
    ]
    assert actions == ["sqs:SendMessage", "sns:Publish", "lambda:InvokeFunction"]
    assert rendered["worker"]["Resources"]["Worker"]["Properties"]["Role"] == templates.att("WorkerRole")


def canary_events(status="no_data"):
    events = []
    for tool, body in (
        ("fetch_logs", {"status": "log_groups_found", "log_groups": []}),
        ("fetch_metrics", {"status": status, "descriptor": {}}),
    ):
        events.append(
            {
                "trace": {
                    "trace": {
                        "orchestrationTrace": {
                            "invocationInput": {"actionGroupInvocationInput": {"actionGroupName": tool}}
                        }
                    }
                }
            }
        )
        events.append(
            {
                "trace": {
                    "trace": {
                        "orchestrationTrace": {
                            "observation": {"actionGroupInvocationOutput": {"text": json.dumps(body)}}
                        }
                    }
                }
            }
        )
    return events + [{"chunk": {"bytes": b"Both tools returned"}}]


def test_canary_requires_actual_successful_tool_observations(spec):
    bundle = {"spec": spec, "bindings": {"agent_id": "ABCDEFGHIJ", "alias_id": "KLMNOPQRST"}}
    client = MagicMock()
    client.invoke_agent.return_value = {"completion": canary_events()}
    assert release.candidate_canary(bundle, lambda *args: client) == ["fetch_logs", "fetch_metrics"]
    for events in (
        canary_events("error"),
        [{"chunk": {"bytes": b"I used both tools"}}],
        canary_events()[:-1],
    ):
        client.invoke_agent.return_value = {"completion": events}
        with pytest.raises(VerificationError):
            release.candidate_canary(bundle, lambda *args: client)


def test_missing_receipt_fails_safely():
    with pytest.raises(VerificationError):
        release.require_receipt({"review_hash": "test"}, None)


def test_cloud_change_set_template_mismatch_cannot_execute(spec):
    bundle = {
        "spec": spec,
        "stages": {
            "tools": {
                "stack": release.stack_name(spec, "tools"),
                "region": spec["bedrock_region"],
                "template_hash": "expected",
            }
        },
    }
    client = MagicMock()
    client.describe_change_set.return_value = {"Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE"}
    client.get_template.return_value = {"TemplateBody": {"Resources": {}}}
    with pytest.raises(VerificationError, match="template"):
        release.inspect_change_set(bundle, "tools", "candidate", lambda *args: client)
    client.execute_change_set.assert_not_called()


def test_released_roles_are_retained_with_published_functions(spec):
    for stage in ("tools", "worker"):
        for resource in examples(spec)[stage]["Resources"].values():
            if resource["Type"] == "AWS::IAM::Role":
                assert resource["DeletionPolicy"] == "Retain"


@pytest.mark.parametrize(
    "bindings", [[1], {"secret": {"arn": [], "version_id": None}}, {"agent_id": []}, {"worker_arn": []}]
)
def test_malformed_release_bindings_fail_explicitly(spec, bindings):
    with pytest.raises(VerificationError):
        release.validate_bindings(spec, bindings, None)


def test_reference_inventory_never_authenticates_to_aws(spec):
    client = MagicMock()
    with pytest.raises(VerificationError, match="Synthetic"):
        assert_account(client, {**spec, "reference_only": True})
    client.get_caller_identity.assert_not_called()


def test_maintenance_disables_automatic_ingress(spec):
    rendered = examples({**spec, "maintenance_mode": True, "reserved_concurrency": 0})["routing"]
    assert rendered["Resources"]["Ec2Down"]["Properties"]["State"] == "DISABLED"
    alarms = [r for k, r in rendered["Resources"].items() if k.startswith("Alarm")]
    assert alarms and all(r["Properties"]["ActionsEnabled"] is False for r in alarms)


def test_seal_requires_owned_successful_stack_and_reads_protection_back(spec):
    from infra.__main__ import seal
    from infra.spec import tags

    client = MagicMock()
    client.get_caller_identity.return_value = {"Account": spec["account_id"]}
    stack = {
        "StackStatus": "CREATE_COMPLETE",
        "EnableTerminationProtection": True,
        "Tags": [{"Key": k, "Value": v} for k, v in tags(spec).items()],
    }
    client.describe_stacks.return_value = {"Stacks": [stack]}
    client.get_stack_policy.return_value = {"StackPolicyBody": json.dumps(release.SEALED_POLICY)}
    assert seal(spec, "tools", lambda *args: client)["status"] == "SEALED"
    client.set_stack_policy.assert_called_once()
    client.update_termination_protection.assert_called_once()
    stack["EnableTerminationProtection"] = False
    with pytest.raises(VerificationError, match="did not take effect"):
        seal(spec, "tools", lambda *args: client)
    client.reset_mock()
    stack["Tags"] = []
    with pytest.raises(VerificationError, match="owned"):
        seal(spec, "tools", lambda *args: client)
    client.set_stack_policy.assert_not_called()


@pytest.mark.parametrize("protection", [False, True])
def test_candidate_cannot_read_or_invoke_unsealed_release(spec, protection):
    clients = {key: MagicMock() for key in ("sts", "cloudformation", "lambda", "bedrock-agent-runtime")}
    clients["sts"].get_caller_identity.return_value = {"Account": spec["account_id"]}
    clients["cloudformation"].describe_stacks.return_value = {
        "Stacks": [{"StackStatus": "CREATE_COMPLETE", "EnableTerminationProtection": protection}]
    }
    clients["cloudformation"].get_stack_policy.return_value = {"StackPolicyBody": "{}"}
    with pytest.raises(VerificationError):
        release.verify_candidate({"spec": spec, "bindings": {}}, lambda key, region: clients[key])
    clients["lambda"].get_function.assert_not_called()
    clients["bedrock-agent-runtime"].invoke_agent.assert_not_called()


def test_routing_verification_rejects_alarm_and_event_drift(spec):
    from infra.verify import routing_health

    clients = {key: MagicMock() for key in ("events", "sns", "cloudwatch")}
    rendered = examples(spec)["routing"]["Resources"]
    worker = rendered["WorkerSubscription"]["Properties"]["Endpoint"]
    rule = rendered["Ec2Down"]["Properties"]
    clients["events"].describe_rule.return_value = {
        "State": rule["State"],
        "EventPattern": json.dumps(rule["EventPattern"]),
    }
    clients["events"].list_targets_by_rule.return_value = {"Targets": rule["Targets"]}
    subscriptions = [r["Properties"] for r in rendered.values() if r["Type"] == "AWS::SNS::Subscription"]
    clients["sns"].get_paginator.return_value.paginate.side_effect = lambda TopicArn: [
        {
            "Subscriptions": [
                {**s, "SubscriptionArn": TopicArn + ":subscription"}
                for s in subscriptions
                if s["TopicArn"] == TopicArn
            ]
        }
    ]
    alarms = [
        copy.deepcopy(r["Properties"]) for r in rendered.values() if r["Type"] == "AWS::CloudWatch::Alarm"
    ]
    clients["cloudwatch"].describe_alarms.return_value = {"MetricAlarms": alarms}

    def factory(key, region):
        return clients[key]

    assert routing_health(spec, factory, worker)["status"] == "PASS"
    alarms[0]["AlarmActions"] = ["arn:aws:sns:eu-central-1:123456789012:unrelated"]
    with pytest.raises(VerificationError, match="AlarmActions"):
        routing_health(spec, factory, worker)
    clients["events"].describe_rule.return_value["EventPattern"] = "{}"
    with pytest.raises(VerificationError, match="event selection"):
        routing_health(spec, factory, worker)


@pytest.mark.parametrize("drift", [None, "code", "environment", "model", "schema", "executor", "alias"])
def test_candidate_checks_deployed_contracts(spec, drift):
    import base64
    import hashlib

    rendered = examples(spec)
    resources = rendered["tools"]["Resources"]
    agent_properties = resources["Agent"]["Properties"]
    bindings = {"agent_id": "ABCDEFGHIJ", "alias_id": "KLMNOPQRST", "artifacts": {}}
    clients = {key: MagicMock() for key in ("sts", "cloudformation", "lambda", "bedrock-agent")}
    clients["sts"].get_caller_identity.return_value = {"Account": spec["account_id"]}
    clients["cloudformation"].describe_stacks.return_value = {
        "Stacks": [{"StackStatus": "CREATE_COMPLETE", "EnableTerminationProtection": True}]
    }
    clients["cloudformation"].get_stack_policy.return_value = {
        "StackPolicyBody": json.dumps(release.SEALED_POLICY)
    }
    functions = {}
    for stage, logical, function, key in (
        ("tools", "Logs", "fetch_logs", "logs_arn"),
        ("tools", "Metrics", "fetch_metrics", "metrics_arn"),
        ("worker", "Worker", "trigger_investigation", "worker_arn"),
    ):
        props = rendered[stage]["Resources"][logical]["Properties"]
        arn = f"arn:aws:lambda:{spec[release.STAGES[stage]]}:{spec['account_id']}:function:{props['FunctionName']}:1"
        bindings[key] = arn
        bindings["artifacts"][function] = {
            "bucket": props["Code"]["S3Bucket"],
            "key": props["Code"]["S3Key"],
            "version_id": props["Code"]["S3ObjectVersion"],
            "sha256": "a" * 64,
        }
        functions[arn] = {
            "Configuration": {
                "CodeSha256": base64.b64encode(bytes.fromhex("a" * 64)).decode(),
                "Runtime": "python3.12",
                "State": "Active",
                "Environment": copy.deepcopy(props["Environment"]),
            }
        }
    log_env = resources["Logs"]["Properties"]["Environment"]["Variables"]
    bindings["secret"] = {
        "arn": log_env["LOG_CURSOR_SECRET_ARN"],
        "version_id": log_env["LOG_CURSOR_SECRET_VERSION"],
    }
    clients["lambda"].get_function.side_effect = lambda FunctionName: functions[FunctionName]
    agent = clients["bedrock-agent"]
    alias = {"agentAliasStatus": "PREPARED", "routingConfiguration": [{"agentVersion": "1"}]}
    agent.get_agent_alias.return_value = {"agentAlias": alias}
    version = {"foundationModel": spec["model_id"], "instruction": agent_properties["Instruction"]}
    agent.get_agent_version.return_value = {"agentVersion": version}
    groups = {}
    hashes = {}
    for group in agent_properties["ActionGroups"]:
        tool = group["ActionGroupName"]
        payload = group["ApiSchema"]["Payload"]
        hashes[tool] = hashlib.sha256(payload.encode()).hexdigest()
        groups[tool] = {
            "agentActionGroup": {
                "actionGroupName": tool,
                "actionGroupState": "ENABLED",
                "apiSchema": {"payload": payload},
                "actionGroupExecutor": {
                    "lambda": bindings["logs_arn" if tool == "fetch_logs" else "metrics_arn"]
                },
            }
        }
    agent.get_paginator.return_value.paginate.return_value = [
        {"actionGroupSummaries": [{"actionGroupId": t} for t in groups]}
    ]
    agent.get_agent_action_group.side_effect = lambda **kwargs: groups[kwargs["actionGroupId"]]
    bundle = {
        "spec": spec,
        "bindings": bindings,
        "schema_sha256": hashes,
        "prompt_sha256": hashlib.sha256(version["instruction"].encode()).hexdigest(),
    }
    if drift == "code":
        functions[bindings["logs_arn"]]["Configuration"]["CodeSha256"] = "changed"
    elif drift == "environment":
        functions[bindings["logs_arn"]]["Configuration"]["Environment"]["Variables"][
            "ALLOWED_INSTANCE_IDS"
        ] = "other"
    elif drift == "model":
        version["foundationModel"] = "other"
    elif drift == "schema":
        groups["fetch_logs"]["agentActionGroup"]["apiSchema"]["payload"] = "{}"
    elif drift == "executor":
        groups["fetch_logs"]["agentActionGroup"]["actionGroupExecutor"]["lambda"] = "other"
    elif drift == "alias":
        alias["routingConfiguration"] = [{"agentVersion": "DRAFT"}]
    if drift:
        with pytest.raises(VerificationError):
            release.verify_candidate(bundle, lambda key, region: clients[key])
    else:
        result = release.verify_candidate(bundle, lambda key, region: clients[key])
        assert result["agent_version"] == "1" and len(result["functions"]) == 3


def test_changed_dependency_lock_requires_rebuild(spec, tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "python": "3.12",
                "architecture": "x86_64",
                "lock_sha256": "old-lock",
                "functions": {key: {} for key in ("fetch_logs", "fetch_metrics", "trigger_investigation")},
            }
        )
    )
    with pytest.raises(VerificationError, match="Dependency lock changed"):
        release.checked_build(tmp_path, spec)
