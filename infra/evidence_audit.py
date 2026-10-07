"""Narrow customer data-access trail, private encrypted destination, finite retention."""

from infra.spec import name, prefix
from infra.templates import resource, tagged


def add(t, spec, config, evidence_bucket):
    from infra.identity import table_arn
    from kira.work_policy import DEFAULT

    bucket = f"{prefix(spec)}-{spec['account_id']}-{spec['monitor_region']}-audit"
    if len(bucket) > 63:
        raise ValueError("Audit bucket name exceeds S3 limit")
    trail = name(spec, "evidence-access")
    arn = f"arn:aws:cloudtrail:{spec['monitor_region']}:{spec['account_id']}:trail/{trail}"
    t["Resources"]["AccessAuditBucket"] = resource(
        "S3::Bucket",
        {
            "BucketName": bucket,
            "Tags": tagged(spec),
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "PublicAccessBlockConfiguration": {
                k: True
                for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
            },
            "VersioningConfiguration": {"Status": "Enabled"},
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
            "LifecycleConfiguration": {
                "Rules": [
                    {
                        "Id": "audit-retention",
                        "Status": "Enabled",
                        "ExpirationInDays": config.get("security", DEFAULT)["audit_days"],
                        "NoncurrentVersionExpiration": {
                            "NoncurrentDays": config.get("security", DEFAULT)["audit_days"]
                        },
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                    }
                ]
            },
        },
        retain=True,
    )
    t["Resources"]["AccessAuditPolicy"] = resource(
        "S3::BucketPolicy",
        {
            "Bucket": bucket,
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    },
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudtrail.amazonaws.com"},
                        "Action": "s3:GetBucketAcl",
                        "Resource": f"arn:aws:s3:::{bucket}",
                        "Condition": {"StringEquals": {"aws:SourceArn": arn}},
                    },
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudtrail.amazonaws.com"},
                        "Action": "s3:PutObject",
                        "Resource": f"arn:aws:s3:::{bucket}/AWSLogs/{spec['account_id']}/*",
                        "Condition": {
                            "StringEquals": {
                                "aws:SourceArn": arn,
                                "s3:x-amz-acl": "bucket-owner-full-control",
                            }
                        },
                    },
                ],
            },
        },
        depends=["AccessAuditBucket"],
    )
    t["Resources"]["AccessAuditTrail"] = resource(
        "CloudTrail::Trail",
        {
            "TrailName": trail,
            "IsLogging": True,
            "IsMultiRegionTrail": False,
            "IncludeGlobalServiceEvents": False,
            "EnableLogFileValidation": True,
            "S3BucketName": bucket,
            "Tags": tagged(spec),
            "AdvancedEventSelectors": [
                {
                    "Name": "Evidence objects",
                    "FieldSelectors": [
                        {"Field": "eventCategory", "Equals": ["Data"]},
                        {"Field": "resources.type", "Equals": ["AWS::S3::Object"]},
                        {
                            "Field": "resources.ARN",
                            "StartsWith": [f"arn:aws:s3:::{evidence_bucket}/incidents/"],
                        },
                    ],
                },
                {
                    "Name": "Authoritative read access",
                    "FieldSelectors": [
                        {"Field": "eventCategory", "Equals": ["Data"]},
                        {"Field": "readOnly", "Equals": ["true"]},
                        {"Field": "resources.type", "Equals": ["AWS::DynamoDB::Table"]},
                        {
                            "Field": "resources.ARN",
                            "Equals": [
                                table_arn(spec),
                                f"arn:aws:dynamodb:{spec['monitor_region']}:{spec['account_id']}:table/{name(spec, 'incidents')}",
                            ],
                        },
                    ],
                },
            ],
        },
        retain=True,
        depends=["AccessAuditPolicy"],
    )


def verify(bundle, factory):
    """Read actual encryption/selectors/delivery status; never claim receipt locally."""
    import json

    from infra import durable_templates
    from infra.verify import VerificationError

    spec, config = bundle["spec"], bundle["config"]
    if "identity" not in config:
        return
    planned = durable_templates.foundation(spec, config)["Resources"]
    desired = planned["AccessAuditTrail"]["Properties"]
    bucket = desired["S3BucketName"]
    owner = {"Bucket": bucket, "ExpectedBucketOwner": spec["account_id"]}
    s3 = factory("s3", spec["monitor_region"])
    if s3.get_bucket_versioning(**owner).get("Status") != "Enabled" or not all(
        (
            s3.get_public_access_block(**owner)["PublicAccessBlockConfiguration"].get(k) is True
            for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
        )
    ):
        raise VerificationError("Audit destination ownership/privacy/versioning drifted")
    encryption = s3.get_bucket_encryption(**owner)["ServerSideEncryptionConfiguration"]["Rules"]
    if (
        len(encryption) != 1
        or encryption[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] != "AES256"
    ):
        raise VerificationError("Audit destination encryption drifted")
    if (
        json.loads(s3.get_bucket_policy(**owner)["Policy"])
        != planned["AccessAuditPolicy"]["Properties"]["PolicyDocument"]
    ):
        raise VerificationError("Audit destination grants drifted")
    rules = s3.get_bucket_lifecycle_configuration(**owner)["Rules"]
    expected = planned["AccessAuditBucket"]["Properties"]["LifecycleConfiguration"]["Rules"][0]
    if (
        len(rules) != 1
        or rules[0].get("Expiration", {}).get("Days") != expected["ExpirationInDays"]
        or rules[0].get("NoncurrentVersionExpiration", {}).get("NoncurrentDays")
        != expected["NoncurrentVersionExpiration"]["NoncurrentDays"]
    ):
        raise VerificationError("Audit retention drifted")
    trail = factory("cloudtrail", spec["monitor_region"])
    arn = f"arn:aws:cloudtrail:{spec['monitor_region']}:{spec['account_id']}:trail/{desired['TrailName']}"
    actual = trail.get_trail(Name=arn)["Trail"]
    status = trail.get_trail_status(Name=arn)
    if (
        actual.get("TrailARN") != arn
        or actual.get("S3BucketName") != bucket
        or actual.get("IsMultiRegionTrail") is not False
        or actual.get("LogFileValidationEnabled") is not True
        or status.get("IsLogging") is not True
        or status.get("LatestDeliveryError")
    ):
        raise VerificationError("Data-access trail delivery/configuration drifted")
    if (
        trail.get_event_selectors(TrailName=arn).get("AdvancedEventSelectors")
        != desired["AdvancedEventSelectors"]
    ):
        raise VerificationError("Data-access trail scope drifted")
