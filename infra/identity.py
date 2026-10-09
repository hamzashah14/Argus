"""Optional customer identity foundations and exact workload grants; no cloud calls."""

import json
import re
from urllib.parse import urlsplit

from infra.spec import name, prefix
from infra.templates import att, resource, role, statement, tagged, template
from infra.verify import VerificationError
from kira.work_policy import DEFAULT


def validate_config(value):
    try:
        uri = urlsplit(value["issuer"])
        if (
            set(value) != {"issuer", "audience"}
            or uri.scheme != "https"
            or not uri.hostname
            or uri.username
            or uri.password
            or uri.query
            or uri.fragment
            or uri.port not in {None, 443}
            or not isinstance(value["audience"], str)
            or not 1 <= len(value["audience"]) <= 256
            or any(ord(c) < 32 for c in value["audience"])
        ):
            raise ValueError()
    except Exception:
        raise VerificationError("Identity requires an HTTPS issuer and exact UI client audience") from None
    return value


def table_name(spec):
    return name(spec, "identity")


def table_arn(spec):
    return f"arn:aws:dynamodb:{spec['monitor_region']}:{spec['account_id']}:table/{table_name(spec)}"


def secret_name(spec):
    return prefix(spec) + "/session-signing"


def validate_bindings(spec, bindings):
    try:
        value = bindings["identity"]
        if (
            set(value) != {"SigningSecretArn", "SigningSecretVersion"}
            or not re.fullmatch(
                rf"arn:aws:secretsmanager:{re.escape(spec['bedrock_region'])}:{spec['account_id']}:secret:{re.escape(secret_name(spec))}-[A-Za-z0-9]{{6}}",
                value["SigningSecretArn"],
            )
            or not re.fullmatch(r"[A-Za-z0-9-]{32,64}", value["SigningSecretVersion"])
        ):
            raise ValueError()
    except Exception:
        raise VerificationError("Bind the exact owned identity secret ARN and immutable version") from None
    return value


def foundation(spec, bindings=None):
    t = template(spec, spec["monitor_region"], "Customer identity/session store; no incident stream")
    t["Resources"]["Sessions"] = resource(
        "DynamoDB::Table",
        {
            "TableName": table_name(spec),
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": k, "AttributeType": "S"} for k in ("PK", "SK")],
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
            "SSESpecification": {"SSEEnabled": True, "SSEType": "KMS"},
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
            "DeletionProtectionEnabled": True,
            "Tags": tagged(spec),
        },
        retain=True,
    )
    t["Outputs"] = {
        "SessionTableName": {"Value": table_name(spec)},
        "SessionTableArn": {"Value": att("Sessions")},
    }
    if bindings and "identity" in bindings:
        t["Resources"]["SessionIssuerRole"] = role(
            spec,
            spec["ui_principal_arn"],
            permissions(spec, bindings, issuer=True),
            service=False,
        )
        t["Outputs"]["SessionIssuerRoleArn"] = {"Value": att("SessionIssuerRole")}
    return t


def signing_secret(spec):
    t = template(spec, spec["bedrock_region"], "Independent generated session signing secret")
    t["Resources"]["SigningSecret"] = resource(
        "SecretsManager::Secret",
        {
            "Name": secret_name(spec),
            "Description": "Kira session references; never the OIDC client/cookie secret",
            "GenerateSecretString": {"PasswordLength": 64, "ExcludePunctuation": True, "IncludeSpace": False},
            "Tags": tagged(spec),
        },
        retain=True,
    )
    t["Outputs"]["SigningSecretArn"] = {"Value": {"Ref": "SigningSecret"}}
    return t


def environment(spec, config, bindings, release):
    value = validate_config(config["identity"])
    secret = validate_bindings(spec, bindings)
    return {
        "KIRA_AUTH_MODE": "oidc",
        "KIRA_WORK_POLICY": json.dumps(
            config.get("security", DEFAULT),
            sort_keys=True,
            separators=(",", ":"),
        ),
        "MONITOR_REGION": spec["monitor_region"],
        "KIRA_SESSION_TABLE": table_name(spec),
        "KIRA_ACCESS_POLICY_JSON": json.dumps(
            {"version": 1, "binding": [spec["environment"], spec["account_id"], release], **value},
            separators=(",", ":"),
            sort_keys=True,
        ),
        "KIRA_SESSION_KEY_ARN": secret["SigningSecretArn"],
        "KIRA_SESSION_KEY_VERSION": secret["SigningSecretVersion"],
    }


def permissions(spec, bindings, *, issuer=False, purpose=None):
    secret = validate_bindings(spec, bindings)

    def rows(actions, prefixes):
        return statement(
            actions,
            table_arn(spec),
            Condition={
                "ForAllValues:StringLike": {"dynamodb:LeadingKeys": prefixes},
                "Null": {"dynamodb:LeadingKeys": "false"},
            },
        )

    return [
        rows("dynamodb:GetItem", ["IDENTITY#*"]),
        rows(
            ["dynamodb:GetItem", "dynamodb:UpdateItem"]
            + (["dynamodb:PutItem", "dynamodb:DeleteItem"] if issuer else []),
            ["SESSION#*"],
        ),
        rows("dynamodb:PutItem", ["AUDIT#*"]),
        *([rows("dynamodb:UpdateItem", ["QUOTA#login#*"])] if issuer else []),
        *(
            [
                rows(
                    ["dynamodb:UpdateItem", "dynamodb:PutItem", "dynamodb:DeleteItem"],
                    ["QUOTA#chat#*", "SLOT#*"],
                )
            ]
            if purpose == "chat"
            else []
        ),
        statement(
            "secretsmanager:GetSecretValue",
            secret["SigningSecretArn"],
            Condition={"StringEquals": {"secretsmanager:VersionId": secret["SigningSecretVersion"]}},
        ),
    ]


def verify_foundations(bundle, factory, *, require_label=True):
    """Verify actual storage settings and exact secret ownership without reading key bytes."""
    spec = bundle["spec"]
    if "identity" not in bundle["config"]:
        return
    from infra.durable_ops import owned_stack
    from infra.templates import template_hash

    for stage in ("identity-foundation", "identity-secret"):
        client, stack = owned_stack(spec, stage, factory=factory)
        body = client.get_template(StackName=stack["StackId"])["TemplateBody"]
        if isinstance(body, str):
            body = json.loads(body)
        if template_hash(body) != bundle["stages"][stage]["template_hash"]:
            raise VerificationError("Identity foundation template drifted")
        if stage == "identity-foundation":
            from infra.owned_ops import verify_role

            planned = body.get("Resources", {}).get("SessionIssuerRole", {}).get("Properties")
            role_arn = next(
                (
                    i["OutputValue"]
                    for i in stack.get("Outputs", [])
                    if i["OutputKey"] == "SessionIssuerRoleArn"
                ),
                "",
            )
            if not planned or not re.fullmatch(
                rf"arn:aws:iam::{spec['account_id']}:role/{re.escape(spec['project'])}/{spec['environment']}/[A-Za-z0-9+=,.@_-]+",
                role_arn,
            ):
                raise VerificationError(
                    "Bind and deploy the limited identity issuer role before qualification"
                )
            client = factory("iam", spec["monitor_region"])
            if client.get_role(RoleName=role_arn.rsplit("/", 1)[-1])["Role"].get("Arn") != role_arn:
                raise VerificationError("Identity issuer role ARN drifted")
            verify_role(client, role_arn, planned)
    ddb = factory("dynamodb", spec["monitor_region"])
    table = ddb.describe_table(TableName=table_name(spec))["Table"]
    ttl = ddb.describe_time_to_live(TableName=table_name(spec))["TimeToLiveDescription"]
    backups = ddb.describe_continuous_backups(TableName=table_name(spec))["ContinuousBackupsDescription"]
    if (
        table.get("TableStatus") != "ACTIVE"
        or table.get("TableArn") != table_arn(spec)
        or table.get("TableName") != table_name(spec)
        or table.get("DeletionProtectionEnabled") is not True
        or table.get("GlobalSecondaryIndexes")
        or table.get("LocalSecondaryIndexes")
        or table.get("StreamSpecification", {}).get("StreamEnabled")
        or table.get("SSEDescription", {}).get("Status") != "ENABLED"
        or table.get("SSEDescription", {}).get("SSEType") != "KMS"
        or table.get("BillingModeSummary", {}).get("BillingMode") != "PAY_PER_REQUEST"
        or {tuple(sorted(k.items())) for k in table.get("KeySchema", [])}
        != {
            tuple(sorted({"AttributeName": "PK", "KeyType": "HASH"}.items())),
            tuple(sorted({"AttributeName": "SK", "KeyType": "RANGE"}.items())),
        }
        or {tuple(sorted(k.items())) for k in table.get("AttributeDefinitions", [])}
        != {tuple(sorted({"AttributeName": k, "AttributeType": "S"}.items())) for k in ("PK", "SK")}
        or ttl != {"AttributeName": "ttl", "TimeToLiveStatus": "ENABLED"}
        or backups.get("PointInTimeRecoveryDescription", {}).get("PointInTimeRecoveryStatus") != "ENABLED"
    ):
        raise VerificationError("Identity table encryption, recovery, TTL, stream or schema drifted")
    value = validate_bindings(spec, bundle["bindings"])
    secret = factory("secretsmanager", spec["bedrock_region"]).describe_secret(
        SecretId=value["SigningSecretArn"]
    )
    from infra.identity_ops import version_label

    if (
        secret.get("ARN") != value["SigningSecretArn"]
        or secret.get("Name") != secret_name(spec)
        or secret.get("DeletedDate")
        or value["SigningSecretVersion"] not in secret.get("VersionIdsToStages", {})
        or (
            require_label
            and version_label(spec)
            not in secret.get("VersionIdsToStages", {}).get(value["SigningSecretVersion"], [])
        )
        or secret.get("KmsKeyId") not in (None, "alias/aws/secretsmanager")
    ):
        raise VerificationError("Identity signing-secret ownership/version/encryption drifted")
