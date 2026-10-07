"""Generate reviewable regional CloudFormation stacks from one inventory.

Release stacks are create-only. Stable routing is a separate, gated change.
"""

import base64
import hashlib
import json

from infra.spec import ROOT, alarm_descriptors, digest, log_groups, log_prefix, name, prefix, tags, topic_arn


def ref(key):
    return {"Ref": key}


def att(key, attribute="Arn"):
    return {"Fn::GetAtt": [key, attribute]}


def tagged(spec, release=False):
    return [{"Key": key, "Value": value} for key, value in tags(spec, release).items()]


def resource(kind, properties, retain=False, depends=None):
    value = {"Type": f"AWS::{kind}", "Properties": properties}
    if retain:
        value.update(DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    if depends:
        value["DependsOn"] = depends
    return value


def template(spec, region, description):
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": description,
        "Metadata": {"Kira": {**tags(spec), "ExpectedAccount": spec["account_id"], "ExpectedRegion": region}},
        "Resources": {},
        "Outputs": {},
    }


def statement(actions, resources, **extra):
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def role(spec, principal, statements, *, service=True, conditions=None, release=False):
    trust = {
        "Effect": "Allow",
        "Principal": {"Service" if service else "AWS": principal},
        "Action": "sts:AssumeRole",
    }
    if conditions:
        trust["Condition"] = conditions
    return resource(
        "IAM::Role",
        {
            "Path": f"/{spec['project']}/{spec['environment']}/",
            "Tags": tagged(spec, release),
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [trust]},
            "Policies": [
                {
                    "PolicyName": "runtime",
                    "PolicyDocument": {"Version": "2012-10-17", "Statement": statements},
                }
            ],
        },
        retain=release,
    )


def bucket_name(spec, purpose):
    # Global S3 namespace; account and region are explicit. Two buckets even in a same-region deployment.
    region = spec["bedrock_region"] if purpose == "tools" else spec["monitor_region"]
    value = f"{prefix(spec)}-{spec['account_id']}-{region}-{purpose}"
    if len(value) > 63:
        raise ValueError("Artifact bucket name exceeds 63 characters; shorten project name")
    return value


def foundation(spec, purpose):
    region = spec["bedrock_region"] if purpose == "tools" else spec["monitor_region"]
    t = template(spec, region, f"Kira {purpose} foundation; retained private artifacts and telemetry")
    r = t["Resources"]
    r["Artifacts"] = resource(
        "S3::Bucket",
        {
            "BucketName": bucket_name(spec, purpose),
            "Tags": tagged(spec),
            "VersioningConfiguration": {"Status": "Enabled"},
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "PublicAccessBlockConfiguration": {
                key: True
                for key in (
                    "BlockPublicAcls",
                    "IgnorePublicAcls",
                    "BlockPublicPolicy",
                    "RestrictPublicBuckets",
                )
            },
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        },
        retain=True,
    )
    r["ArtifactPolicy"] = resource(
        "S3::BucketPolicy",
        {
            "Bucket": ref("Artifacts"),
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [att("Artifacts"), {"Fn::Sub": "${Artifacts.Arn}/*"}],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    }
                ],
            },
        },
    )
    t["Outputs"]["ArtifactBucket"] = {"Value": ref("Artifacts")}
    if purpose == "tools":
        r["CursorSecret"] = resource(
            "SecretsManager::Secret",
            {
                "Name": f"{prefix(spec)}/log-cursor",
                "Description": "Pin a VersionId per release; never put the value in a plan",
                "GenerateSecretString": {"PasswordLength": 48, "ExcludePunctuation": True},
                "Tags": tagged(spec),
            },
            retain=True,
        )
        t["Outputs"]["CursorSecretArn"] = {"Value": ref("CursorSecret")}
        r["CiValidationRole"] = role(
            spec,
            spec["ci_principal_arn"],
            [
                statement(
                    [
                        "cloudformation:DescribeStacks",
                        "cloudformation:DescribeStackEvents",
                        "cloudformation:DescribeChangeSet",
                        "cloudformation:ListStackResources",
                    ],
                    f"arn:aws:cloudformation:*:{spec['account_id']}:stack/{prefix(spec)}-*/*",
                ),
                statement(["s3:GetObjectVersion"], f"arn:aws:s3:::{bucket_name(spec, 'tools')}/*"),
            ],
            service=False,
        )
    else:
        # Identities are provisioned now; their durable runtime bindings belong
        # to Phase 3. No queue or asynchronous pipeline is implied here.
        r["IngestionRole"] = role(
            spec,
            "lambda.amazonaws.com",
            [
                statement(
                    "sqs:SendMessage", f"arn:aws:sqs:{region}:{spec['account_id']}:{name(spec, 'incidents')}"
                )
            ],
        )
        r["NotificationRole"] = role(
            spec, "lambda.amazonaws.com", [statement("sns:Publish", topic_arn(spec, "reports"))]
        )
        for key, suffix in (("AlarmsTopic", "alarms"), ("ReportsTopic", "reports")):
            r[key] = resource(
                "SNS::Topic", {"TopicName": name(spec, suffix), "Tags": tagged(spec)}, retain=True
            )
            t["Outputs"][key + "Arn"] = {"Value": ref(key)}
        r["TopicPolicies"] = resource(
            "SNS::TopicPolicy",
            {
                "Topics": [ref("AlarmsTopic"), ref("ReportsTopic")],
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        statement(
                            "sns:Publish",
                            ref("AlarmsTopic"),
                            Principal={"Service": "events.amazonaws.com"},
                            Condition={
                                "StringEquals": {"aws:SourceAccount": spec["account_id"]},
                                "ArnEquals": {
                                    "aws:SourceArn": f"arn:aws:events:{region}:{spec['account_id']}:rule/{name(spec, 'ec2-down')}"
                                },
                            },
                        ),
                        statement(
                            "sns:Publish",
                            [ref("AlarmsTopic"), ref("ReportsTopic")],
                            Principal={"Service": "cloudwatch.amazonaws.com"},
                            Condition={
                                "StringEquals": {"aws:SourceAccount": spec["account_id"]},
                                "ArnLike": {
                                    "aws:SourceArn": f"arn:aws:cloudwatch:{region}:{spec['account_id']}:alarm:{prefix(spec)}-*"
                                },
                            },
                        ),
                    ],
                },
            },
        )
        for group in log_groups(spec):
            r["Log" + digest(group)[:16]] = resource(
                "Logs::LogGroup",
                {"LogGroupName": group, "RetentionInDays": spec["log_retention_days"], "Tags": tagged(spec)},
                retain=True,
            )
        for instance in spec["instances"]:
            if not instance["nginx_alarm"]:
                continue
            for kind in ("access", "error"):
                group = f"{log_prefix(spec)}/{instance['id']}/nginx-{kind}"
                r["Filter" + digest([instance["id"], kind])[:16]] = resource(
                    "Logs::MetricFilter",
                    {
                        "FilterName": name(spec, f"{instance['id']}-{kind}"),
                        "LogGroupName": group,
                        "FilterPattern": spec["nginx_filters"][kind]["pattern"],
                        "MetricTransformations": [
                            {
                                "MetricName": (
                                    f"nginx-{'failed-requests' if kind == 'access' else 'diagnostic-events'}-{instance['id']}"
                                    if "observability" in spec
                                    else f"nginx-upstream-errors-{instance['id']}"
                                ),
                                "MetricNamespace": f"{spec['project']}/{spec['environment']}/Nginx",
                                "MetricValue": "1",
                                "DefaultValue": 0,
                            }
                        ],
                    },
                    depends=["Log" + digest(group)[:16]],
                )
    return t


def add_function(t, spec, logical, function, artifact, env, region, policies, timeout):
    if len(json.dumps(env, separators=(",", ":"), ensure_ascii=False).encode()) > 4096:
        from infra.verify import VerificationError

        raise VerificationError("Lambda environment exceeds the conservative 4 KiB rendering limit")
    r = t["Resources"]
    physical = name(spec, function.replace("_", "-"), release=True)
    group = f"/aws/lambda/{physical}"
    r[logical + "Log"] = resource(
        "Logs::LogGroup",
        {"LogGroupName": group, "RetentionInDays": spec["log_retention_days"], "Tags": tagged(spec, True)},
        retain=True,
    )
    log_arn = f"arn:aws:logs:{region}:{spec['account_id']}:log-group:{group}:*"
    r[logical + "Role"] = role(
        spec,
        "lambda.amazonaws.com",
        [statement(["logs:CreateLogStream", "logs:PutLogEvents"], log_arn), *policies],
        release=True,
    )
    r[logical] = resource(
        "Lambda::Function",
        {
            "FunctionName": physical,
            "Runtime": "python3.12",
            "Architectures": ["x86_64"],
            "Handler": "lambda_function.lambda_handler",
            "Code": {
                "S3Bucket": artifact["bucket"],
                "S3Key": artifact["key"],
                "S3ObjectVersion": artifact["version_id"],
            },
            "Role": att(logical + "Role"),
            "Timeout": timeout,
            "MemorySize": 256,
            "Environment": {"Variables": env},
            "Tags": tagged(spec, True),
        },
        retain=True,
        depends=[logical + "Log"],
    )
    r[logical + "Version"] = resource(
        "Lambda::Version",
        {
            "FunctionName": ref(logical),
            "CodeSha256": base64.b64encode(bytes.fromhex(artifact["sha256"])).decode(),
            "Description": f"{spec['release_id']} code/config snapshot",
        },
        retain=True,
    )
    t["Outputs"][logical + "VersionArn"] = {"Value": ref(logical + "Version")}
    t["Outputs"][logical + "FunctionArn"] = {"Value": att(logical)}
    return ref(logical + "Version")


def tools_release(spec, artifacts, secret, *, classic=True):
    region = spec["bedrock_region"]
    t = template(spec, region, "Kira create-only tool and agent candidate; never update this release stack")
    r = t["Resources"]
    common = {
        "MONITOR_REGION": spec["monitor_region"],
        "ENVIRONMENT": spec["environment"],
        "EXPECTED_ACCOUNT_ID": spec["account_id"],
        "LOG_GROUP_PREFIX": log_prefix(spec),
        "ALLOWED_INSTANCE_IDS": ",".join(i["id"] for i in spec["instances"]),
        "LOG_SCOPE_FILE": "config/log-scope.json",
    }
    logs_env = {
        **common,
        "LOG_CURSOR_SECRET_ARN": secret["arn"],
        "LOG_CURSOR_SECRET_VERSION": secret["version_id"],
    }
    logs_arns = [
        f"arn:aws:logs:{spec['monitor_region']}:{spec['account_id']}:log-group:{group}:*"
        for group in log_groups(spec)
    ]
    region_condition = {"StringEquals": {"aws:RequestedRegion": spec["monitor_region"]}}
    logs_version = add_function(
        t,
        spec,
        "Logs",
        "fetch_logs",
        artifacts["fetch_logs"],
        logs_env,
        region,
        [
            statement(["logs:StartQuery"], logs_arns, Condition=region_condition),
            statement(
                ["logs:GetQueryResults", "logs:StopQuery", "logs:DescribeLogGroups"],
                "*",
                Condition=region_condition,
            ),
            statement("secretsmanager:GetSecretValue", secret["arn"]),
        ],
        120,
    )
    metrics_version = add_function(
        t,
        spec,
        "Metrics",
        "fetch_metrics",
        artifacts["fetch_metrics"],
        common,
        region,
        [
            statement("cloudwatch:GetMetricStatistics", "*", Condition=region_condition),
        ],
        30,
    )
    if not classic:
        t["Description"] = "Kira create-only tools for code-owned orchestration"
        return t
    executors = (
        {"Logs": logs_version, "Metrics": metrics_version}
        if spec["executor_mode"] == "qualified"
        else {"Logs": att("Logs"), "Metrics": att("Metrics")}
    )
    r["AgentRole"] = role(
        spec,
        "bedrock.amazonaws.com",
        [
            statement("lambda:InvokeFunction", list(executors.values())),
            statement(
                [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:GetInferenceProfile",
                    "bedrock:GetFoundationModel",
                ],
                spec["model_arns"],
            ),
        ],
        conditions={
            "StringEquals": {"aws:SourceAccount": spec["account_id"]},
            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{region}:{spec['account_id']}:agent/*"},
        },
        release=True,
    )
    action_groups = []
    for logical, tool in (("Logs", "fetch_logs"), ("Metrics", "fetch_metrics")):
        action_groups.append(
            {
                "ActionGroupName": tool,
                "ActionGroupState": "ENABLED",
                "ActionGroupExecutor": {"Lambda": executors[logical]},
                "ApiSchema": {"Payload": (ROOT / f"schemas/{tool}.json").read_text()},
            }
        )
    r["Agent"] = resource(
        "Bedrock::Agent",
        {
            "AgentName": name(spec, "agent", release=True),
            "AgentResourceRoleArn": att("AgentRole"),
            "AutoPrepare": False,
            "FoundationModel": spec["model_id"],
            "IdleSessionTTLInSeconds": 1800,
            "Instruction": (ROOT / "agent-instruction.txt").read_text(),
            "ActionGroups": action_groups,
            "Tags": tags(spec, True),
        },
        retain=True,
    )
    for logical in ("Logs", "Metrics"):
        r[logical + "Permission"] = resource(
            "Lambda::Permission",
            {
                "FunctionName": executors[logical],
                "Action": "lambda:InvokeFunction",
                "Principal": "bedrock.amazonaws.com",
                "SourceAccount": spec["account_id"],
                "SourceArn": att("Agent", "AgentArn"),
            },
            retain=True,
        )
    t["Outputs"]["AgentId"] = {"Value": ref("Agent")}
    return t


def candidate_alias(spec, agent_id):
    t = template(
        spec, spec["bedrock_region"], "Kira create-only alias for an explicitly prepared candidate agent"
    )
    t["Resources"]["Candidate"] = resource(
        "Bedrock::AgentAlias",
        {
            "AgentId": agent_id,
            "AgentAliasName": name(spec, "candidate", release=True),
            "Tags": tags(spec, True),
        },
        retain=True,
    )
    t["Outputs"]["AgentAliasArn"] = {"Value": att("Candidate", "AgentAliasArn")}
    t["Outputs"]["AgentAliasId"] = {"Value": att("Candidate", "AgentAliasId")}
    return t


def worker_release(spec, artifact, agent_id, alias_id):
    t = template(
        spec, spec["monitor_region"], "Kira create-only worker candidate; not subscribed until promotion"
    )
    alias = f"arn:aws:bedrock:{spec['bedrock_region']}:{spec['account_id']}:agent-alias/{agent_id}/{alias_id}"
    env = {
        "BEDROCK_REGION": spec["bedrock_region"],
        "BEDROCK_AGENT_ID": agent_id,
        "BEDROCK_AGENT_ALIAS_ID": alias_id,
        "REPORTS_TOPIC_ARN": topic_arn(spec, "reports"),
        "ALARM_NAME_PREFIX": prefix(spec),
        "ALLOWED_INSTANCE_IDS": ",".join(i["id"] for i in spec["instances"]),
    }
    add_function(
        t,
        spec,
        "Worker",
        "trigger_investigation",
        artifact,
        env,
        spec["monitor_region"],
        [
            statement("bedrock:InvokeAgent", alias),
            statement("sns:Publish", topic_arn(spec, "reports")),
        ],
        600,
    )
    if spec["reserved_concurrency"] is not None:
        t["Resources"]["Worker"]["Properties"]["ReservedConcurrentExecutions"] = spec["reserved_concurrency"]
    t["Resources"]["DispatchRole"] = role(
        spec, "lambda.amazonaws.com", [statement("lambda:InvokeFunction", ref("WorkerVersion"))], release=True
    )
    t["Resources"]["WorkerAsync"] = resource(
        "Lambda::EventInvokeConfig",
        {
            "FunctionName": ref("Worker"),
            "Qualifier": att("WorkerVersion", "Version"),
            "MaximumRetryAttempts": 0,
            "MaximumEventAgeInSeconds": 3600,
        },
    )
    t["Resources"]["WorkerPermission"] = resource(
        "Lambda::Permission",
        {
            "FunctionName": ref("WorkerVersion"),
            "Action": "lambda:InvokeFunction",
            "Principal": "sns.amazonaws.com",
            "SourceAccount": spec["account_id"],
            "SourceArn": topic_arn(spec, "alarms"),
        },
        retain=True,
    )
    return t


def routing(spec, worker_arn, agent_id, alias_id):
    t = template(
        spec,
        spec["monitor_region"],
        "Kira active routing; apply only after candidate and coverage verification",
    )
    r = t["Resources"]
    r["WorkerSubscription"] = resource(
        "SNS::Subscription",
        {"Protocol": "lambda", "Endpoint": worker_arn, "TopicArn": topic_arn(spec, "alarms")},
    )
    # Endpoint-specific logical IDs make retirement explicit. Reconciliation removes the old recipient first.
    r["Email" + digest(spec["notification_email"])[:16]] = resource(
        "SNS::Subscription",
        {"Protocol": "email", "Endpoint": spec["notification_email"], "TopicArn": topic_arn(spec, "reports")},
    )
    r["Ec2Down"] = resource(
        "Events::Rule",
        {
            "Name": name(spec, "ec2-down"),
            "State": "DISABLED" if spec["maintenance_mode"] else "ENABLED",
            "EventPattern": {
                "source": ["aws.ec2"],
                "detail-type": ["EC2 Instance State-change Notification"],
                "detail": {
                    "state": ["stopped", "terminated"],
                    "instance-id": [i["id"] for i in spec["instances"]],
                },
            },
            "Targets": [{"Id": "alarms", "Arn": topic_arn(spec, "alarms")}],
            "Tags": tagged(spec),
        },
    )
    for alarm in alarm_descriptors(spec):
        r["Alarm" + digest(alarm["id"])[:16]] = resource(
            "CloudWatch::Alarm",
            {
                "AlarmName": alarm["alarm_name"],
                **(
                    {
                        "AlarmDescription": "Owner: "
                        + (
                            alarm.get("owner")
                            or next(
                                s["owner"]
                                for s in spec["observability"]["services"]
                                if s["instance_id"] == alarm["instance_id"]
                            )
                        )
                        + "; docs/implementation/phase-4/RUNBOOKS.md"
                    }
                    if "observability" in spec
                    else {}
                ),
                "Namespace": alarm["namespace"],
                "MetricName": alarm["metric_name"],
                "Dimensions": [{"Name": k, "Value": v} for k, v in sorted(alarm["dimensions"].items())],
                "Statistic": alarm["statistic"],
                "Period": alarm["period"],
                "EvaluationPeriods": 2,
                "DatapointsToAlarm": 2,
                "Threshold": alarm["threshold"],
                "ComparisonOperator": alarm["comparison"],
                "TreatMissingData": alarm.get(
                    "missing_data", "notBreaching" if alarm["namespace"].endswith("/Nginx") else "missing"
                ),
                "ActionsEnabled": not spec["maintenance_mode"]
                and (not alarm["namespace"].endswith("/Health") or spec["observability"]["enabled"]),
                "AlarmActions": [topic_arn(spec, "alarms")],
                **({"OKActions": [topic_arn(spec, "alarms")]} if "observability" in spec else {}),
                "Tags": tagged(spec),
            },
        )
    r["WorkerFailure"] = resource(
        "CloudWatch::Alarm",
        {
            "AlarmName": name(spec, "worker-errors"),
            "Namespace": "AWS/Lambda",
            "MetricName": "Errors",
            "Dimensions": [{"Name": "FunctionName", "Value": worker_arn.split(":")[6]}],
            "Statistic": "Sum",
            "Period": 300,
            "EvaluationPeriods": 1,
            "Threshold": 0,
            "ComparisonOperator": "GreaterThanThreshold",
            "TreatMissingData": "notBreaching",
            "AlarmActions": [topic_arn(spec, "reports")],
            "Tags": tagged(spec),
        },
    )
    alias_arn = (
        f"arn:aws:bedrock:{spec['bedrock_region']}:{spec['account_id']}:agent-alias/{agent_id}/{alias_id}"
    )
    r["UiRole"] = role(
        spec, spec["ui_principal_arn"], [statement("bedrock:InvokeAgent", alias_arn)], service=False
    )
    t["Outputs"]["UiRoleArn"] = {"Value": att("UiRole")}
    t["Outputs"]["AgentConnection"] = {
        "Value": json.dumps(
            {
                "BEDROCK_REGION": spec["bedrock_region"],
                "BEDROCK_AGENT_ID": agent_id,
                "BEDROCK_AGENT_ALIAS_ID": alias_id,
            }
        )
    }
    return t


def template_hash(t):
    return hashlib.sha256(json.dumps(t, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
