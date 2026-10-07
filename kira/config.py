"""Validated web-client configuration for standalone and AgentCore runtimes."""

import json
import os
import re
from dataclasses import dataclass, field

REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$")
INSTANCE = re.compile(r"^i-(?:[0-9a-f]{8}|[0-9a-f]{17})$")


@dataclass(frozen=True)
class AppConfig:
    region: str
    password: str = field(repr=False)
    environment: str = "development"
    runtime_target: str = "standalone"
    model_id: str = ""
    account_id: str = ""
    logs_arn: str = ""
    metrics_arn: str = ""
    allowed_ids: str = ""
    runtime_limits: str = ""
    runtime_release: str = ""
    agentcore_arn: str = ""
    agentcore_endpoint: str = ""
    chat_arn: str = ""

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION", ""),
            os.getenv("APP_PASSWORD", ""),
            os.getenv("ENVIRONMENT", "development"),
            os.getenv("RUNTIME_TARGET", "standalone"),
            os.getenv("BEDROCK_MODEL_ID", ""),
            os.getenv("EXPECTED_ACCOUNT_ID", ""),
            os.getenv("LOGS_TOOL_ARN", ""),
            os.getenv("METRICS_TOOL_ARN", ""),
            os.getenv("ALLOWED_INSTANCE_IDS", ""),
            os.getenv("RUNTIME_LIMITS", ""),
            os.getenv("RUNTIME_RELEASE", ""),
            os.getenv("AGENTCORE_RUNTIME_ARN", ""),
            os.getenv("AGENTCORE_ENDPOINT", ""),
            os.getenv("CHAT_FUNCTION_ARN", ""),
        )

    def problems(self):
        problems = []
        if not REGION.fullmatch(self.region):
            problems.append("Set BEDROCK_REGION to the region containing your Bedrock model.")
        if self.environment not in {"development", "staging", "production"}:
            problems.append("ENVIRONMENT must be development, staging or production.")
        if self.runtime_target not in {"standalone", "agentcore"}:
            problems.append("RUNTIME_TARGET must be standalone or agentcore.")
        if self.runtime_target in {"standalone", "agentcore"}:
            if not re.fullmatch(r"[a-zA-Z_./0-9:-]{1,256}", self.model_id) or not re.fullmatch(
                r"[0-9]{12}", self.account_id
            ):
                problems.append("Set the intended Bedrock model and AWS account.")
            if not re.fullmatch(r"[0-9a-f]{64}", self.runtime_release):
                problems.append("Set the verified RUNTIME_RELEASE fingerprint.")
            try:
                from kira.runtime import Limits

                Limits(**json.loads(self.runtime_limits))
                ids = self.allowed_ids.split(",")
                if not ids or len(ids) > 100 or any(not INSTANCE.fullmatch(i) for i in ids):
                    raise ValueError("Invalid inventory")
                if self.environment in {"staging", "production"}:
                    if not re.fullmatch(
                        rf"arn:aws:lambda:{re.escape(os.getenv('MONITOR_REGION', self.region))}:{self.account_id}:function:[\w-]+:[1-9][0-9]*",
                        self.chat_arn,
                    ):
                        raise ValueError("Invalid dedicated chat version")
                elif self.runtime_target == "standalone":
                    for arn in (self.logs_arn, self.metrics_arn):
                        if not re.fullmatch(
                            rf"arn:aws:lambda:{re.escape(self.region)}:{self.account_id}:function:[\w-]+:[1-9][0-9]*",
                            arn,
                        ):
                            raise ValueError("Invalid tool version")
                else:
                    from kira.agentcore import validate_target

                    validate_target(self.agentcore_arn, self.agentcore_endpoint, self.region, self.account_id)
            except (ValueError, TypeError):
                problems.append("Set validated runtime limits, inventory and qualified execution bindings.")
        if bool(os.getenv("AWS_ACCESS_KEY_ID")) != bool(os.getenv("AWS_SECRET_ACCESS_KEY")):
            problems.append("Set both AWS credential variables, or remove both to use the credential chain.")
        return problems
