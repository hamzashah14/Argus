"""Validated configuration shared by deployment scripts and the web client."""

import argparse
import json
import os
import re
import shlex
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$")
INSTANCE = re.compile(r"^i-(?:[0-9a-f]{8}|[0-9a-f]{17})$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9]{10}$")
RETENTION = {
    1,
    3,
    5,
    7,
    14,
    30,
    60,
    90,
    120,
    150,
    180,
    365,
    400,
    545,
    731,
    1096,
    1827,
    2192,
    2557,
    2922,
    3288,
    3653,
}


class ConfigError(ValueError):
    pass


def read_env(path):
    values = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line.strip())
        if not match:
            raise ConfigError(f"Configuration line {number} must be KEY=VALUE.")
        name, value = match.groups()
        value = value.strip()
        if name in values:
            raise ConfigError(f"Duplicate configuration key: {name}.")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigError(f"Unclosed quote on configuration line {number}.")
            value = value[1:-1]
        if any(ord(char) < 32 for char in value):
            raise ConfigError(f"Control characters in configuration key {name}.")
        values[name] = value
    return values


@dataclass(frozen=True)
class DeploymentConfig:
    ENVIRONMENT: str = "development"
    EXPECTED_ACCOUNT_ID: str = ""
    MONITOR_REGION: str = ""
    BEDROCK_REGION: str = ""
    BEDROCK_MODEL_ID: str = ""
    BEDROCK_AGENT_ID: str = ""
    BEDROCK_AGENT_ALIAS_ID: str = ""
    ALERT_EMAIL: str = ""
    INSTANCE_IDS: str = ""
    CONTAINER_NAMES: str = ""
    LOG_GROUP_PREFIX: str = "/aiops"
    LOG_RETENTION_DAYS: int = 30
    AGENT_NAME: str = "aiops-assistant"
    ENABLE_RESOURCE_ALARMS: bool = True
    CPU_THRESHOLD: int = 90
    MEM_THRESHOLD: int = 90
    DISK_THRESHOLD: int = 85
    DISK_PATH: str = "/"
    ENABLE_NGINX_ALARM: bool = True
    NGINX_ERROR_THRESHOLD: int = 5
    NGINX_ACCESS_FILTER_PATTERN: str = (
        "[ip, ident, user, timestamp, request, status_code = 502 || status_code = 504, bytes, referer, agent]"
    )
    NGINX_ERROR_FILTER_PATTERN: str = '?"upstream timed out" ?"no live upstreams" ?"connect() failed"'
    ENABLE_PROCESS_ALARM: bool = False
    TRIGGER_RESERVED_CONCURRENCY: str = ""
    MAINTENANCE_MODE: bool = False
    LOG_CURSOR_SECRET: str = field(default="", repr=False)
    METRIC_CATALOG_FILE: str = "config/metric-catalog.json"

    @classmethod
    def load(cls, path, purpose="validate"):
        raw = read_env(path)
        definitions = {item.name: item for item in fields(cls)}
        unknown = sorted(raw.keys() - definitions.keys())
        if unknown:
            raise ConfigError("Unknown configuration keys: " + ", ".join(unknown))
        parsed = {}
        for name, value in raw.items():
            typ = definitions[name].type
            if typ is bool:
                if value not in {"true", "false"}:
                    raise ConfigError(f"{name} must be true or false.")
                parsed[name] = value == "true"
            elif typ is int:
                if not re.fullmatch(r"\d+", value):
                    raise ConfigError(f"{name} must be a whole number.")
                parsed[name] = int(value)
            else:
                parsed[name] = value
        result = cls(**parsed)
        result.validate(purpose)
        return result

    def validate(self, purpose):
        if purpose not in {"validate", "iam", "tools", "agent", "alerts"}:
            raise ConfigError("Unknown configuration purpose.")
        if self.ENVIRONMENT not in {"development", "staging", "production"}:
            raise ConfigError("ENVIRONMENT must be development, staging or production.")
        if (
            not re.fullmatch(r"\d{12}", self.EXPECTED_ACCOUNT_ID)
            or self.EXPECTED_ACCOUNT_ID == "000000000000"
        ):
            raise ConfigError("EXPECTED_ACCOUNT_ID must identify the intended 12-digit AWS account.")
        for name in ("MONITOR_REGION", "BEDROCK_REGION"):
            region = getattr(self, name)
            if not REGION.fullmatch(region) or region.startswith(("cn-", "us-gov-")):
                raise ConfigError(
                    f"{name} must be a commercial AWS region; other partitions are not supported by the current scripts."
                )
        if not re.fullmatch(
            r"/[A-Za-z0-9_.\-/#]{1,200}", self.LOG_GROUP_PREFIX
        ) or self.LOG_GROUP_PREFIX.endswith("/"):
            raise ConfigError("LOG_GROUP_PREFIX must be a non-root prefix without a trailing slash.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", self.AGENT_NAME):
            raise ConfigError("AGENT_NAME has an invalid format.")
        if self.LOG_RETENTION_DAYS not in RETENTION:
            raise ConfigError("LOG_RETENTION_DAYS is not a supported retention interval.")
        for name in ("CPU_THRESHOLD", "MEM_THRESHOLD", "DISK_THRESHOLD"):
            if not 1 <= getattr(self, name) <= 100:
                raise ConfigError(f"{name} must be between 1 and 100.")
        if not 1 <= self.NGINX_ERROR_THRESHOLD <= 1000000:
            raise ConfigError("NGINX_ERROR_THRESHOLD must be between 1 and 1000000.")
        if not re.fullmatch(r"/[\w./-]*", self.DISK_PATH):
            raise ConfigError("DISK_PATH must be an absolute filesystem path.")
        for name in ("NGINX_ACCESS_FILTER_PATTERN", "NGINX_ERROR_FILTER_PATTERN"):
            if not 1 <= len(getattr(self, name).encode()) <= 1024:
                raise ConfigError(f"{name} must contain 1–1024 bytes.")
        for name in ("BEDROCK_AGENT_ID", "BEDROCK_AGENT_ALIAS_ID"):
            value = getattr(self, name)
            if value and not (
                IDENTIFIER.fullmatch(value) or (name.endswith("ALIAS_ID") and value == "TSTALIASID")
            ):
                raise ConfigError(f"{name} has an invalid identifier format.")
        if self.ENVIRONMENT == "production" and self.BEDROCK_AGENT_ALIAS_ID == "TSTALIASID":
            raise ConfigError("Production requires a versioned agent alias; TSTALIASID is forbidden.")
        if self.BEDROCK_MODEL_ID and not re.fullmatch(r"[A-Za-z0-9_:.\-/]{1,2048}", self.BEDROCK_MODEL_ID):
            raise ConfigError("BEDROCK_MODEL_ID has an invalid format.")
        if self.ALERT_EMAIL and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.ALERT_EMAIL):
            raise ConfigError("ALERT_EMAIL must be a valid email address.")
        for name, pattern in (
            ("INSTANCE_IDS", INSTANCE),
            ("CONTAINER_NAMES", re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")),
        ):
            value = getattr(self, name)
            if value:
                items = [item.strip() for item in value.split(",")]
                if (
                    len(items) > 100
                    or len(set(items)) != len(items)
                    or any(not pattern.fullmatch(item) for item in items)
                ):
                    raise ConfigError(
                        f"{name} must be a unique comma-separated list of valid identifiers (maximum 100)."
                    )
        if self.TRIGGER_RESERVED_CONCURRENCY:
            if not re.fullmatch(r"\d{1,5}", self.TRIGGER_RESERVED_CONCURRENCY):
                raise ConfigError("TRIGGER_RESERVED_CONCURRENCY must be blank or a nonnegative integer.")
            if int(self.TRIGGER_RESERVED_CONCURRENCY) == 0 and not self.MAINTENANCE_MODE:
                raise ConfigError("Zero worker concurrency requires MAINTENANCE_MODE=true.")
        if self.LOG_CURSOR_SECRET and not 32 <= len(self.LOG_CURSOR_SECRET.encode()) <= 256:
            raise ConfigError("LOG_CURSOR_SECRET must contain 32–256 bytes.")
        required = {
            "tools": ["INSTANCE_IDS", "LOG_CURSOR_SECRET"],
            "agent": ["BEDROCK_MODEL_ID"],
            "alerts": ["INSTANCE_IDS", "BEDROCK_AGENT_ID", "BEDROCK_AGENT_ALIAS_ID", "ALERT_EMAIL"],
        }
        for name in required.get(purpose, []):
            if not getattr(self, name):
                raise ConfigError(f"{name} is required for {purpose}.")
        if not self.METRIC_CATALOG_FILE or "\x00" in self.METRIC_CATALOG_FILE:
            raise ConfigError("METRIC_CATALOG_FILE is required.")
        from kira.metrics import validate_catalog

        try:
            catalog_path = Path(self.METRIC_CATALOG_FILE)
            if catalog_path.stat().st_size > 262144:
                raise ValueError("Metric catalog exceeds the supported size.")
            validate_catalog(json.loads(catalog_path.read_text()))
        except (OSError, ValueError) as exc:
            raise ConfigError(
                "METRIC_CATALOG_FILE must exist and contain valid allowlisted descriptors."
            ) from exc

    def exports(self):
        def encode(value):
            return str(value).lower() if isinstance(value, bool) else str(value)

        return "\n".join(
            f"export {name}={shlex.quote(encode(value))}" for name, value in asdict(self).items()
        )


@dataclass(frozen=True)
class AppConfig:
    region: str
    agent_id: str
    alias_id: str
    password: str = field(repr=False)
    environment: str = "development"
    runtime_target: str = "classic"
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
            os.getenv("BEDROCK_AGENT_ID", ""),
            os.getenv("BEDROCK_AGENT_ALIAS_ID", ""),
            os.getenv("APP_PASSWORD", ""),
            os.getenv("ENVIRONMENT", "development"),
            os.getenv("RUNTIME_TARGET", "classic" if os.getenv("BEDROCK_AGENT_ID") else "standalone"),
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
            problems.append("Set BEDROCK_REGION to the region containing your agent.")
        if self.runtime_target == "classic" and not IDENTIFIER.fullmatch(self.agent_id):
            problems.append("Set BEDROCK_AGENT_ID to your 10-character agent ID.")
        if (
            self.runtime_target == "classic"
            and not IDENTIFIER.fullmatch(self.alias_id)
            and self.alias_id != "TSTALIASID"
        ):
            problems.append("Set BEDROCK_AGENT_ALIAS_ID to a valid agent alias.")
        if self.environment not in {"development", "staging", "production"}:
            problems.append("ENVIRONMENT must be development, staging or production.")
        if self.environment == "production" and self.alias_id == "TSTALIASID":
            problems.append("Production requires a versioned alias.")
        if self.runtime_target not in {"standalone", "agentcore", "classic"}:
            problems.append(
                "RUNTIME_TARGET must be standalone or agentcore (classic is legacy compatibility)."
            )
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--purpose", default="validate")
    parser.add_argument("--exports", action="store_true")
    args = parser.parse_args()
    try:
        settings = DeploymentConfig.load(args.path, args.purpose)
    except (ConfigError, OSError) as exc:
        print(f"Configuration rejected: {exc}", file=sys.stderr)
        return 2
    print(settings.exports() if args.exports else "Configuration valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
