import json

import pytest

from kira.config import AppConfig
from kira.runtime import Limits


@pytest.fixture
def configured(monkeypatch):
    for key, value in {
        "BEDROCK_REGION": "eu-central-1",
        "ENVIRONMENT": "development",
        "RUNTIME_TARGET": "standalone",
        "EXPECTED_ACCOUNT_ID": "123456789012",
        "BEDROCK_MODEL_ID": "fixture-model",
        "ALLOWED_INSTANCE_IDS": "i-0123456789abcdef0",
        "RUNTIME_RELEASE": "a" * 64,
        "RUNTIME_LIMITS": json.dumps(Limits().__dict__),
        "LOGS_TOOL_ARN": "arn:aws:lambda:eu-central-1:123456789012:function:logs:1",
        "METRICS_TOOL_ARN": "arn:aws:lambda:eu-central-1:123456789012:function:metrics:1",
    }.items():
        monkeypatch.setenv(key, value)
    return AppConfig.from_env()


def test_current_runtime_configuration_is_valid(configured):
    assert configured.problems() == []


@pytest.mark.parametrize("target", ["classic", "unknown", ""])
def test_unsupported_runtime_cannot_enable_chat(configured, monkeypatch, target):
    monkeypatch.setenv("RUNTIME_TARGET", target)
    assert "RUNTIME_TARGET must be standalone or agentcore." in AppConfig.from_env().problems()


def test_unsupported_agent_variables_do_not_select_an_unsupported_runtime(monkeypatch):
    monkeypatch.delenv("RUNTIME_TARGET", raising=False)
    monkeypatch.setenv("BEDROCK_AGENT_ID", "ABCDEFGHIJ")
    assert AppConfig.from_env().runtime_target == "standalone"


@pytest.mark.parametrize(
    "key,value",
    [
        ("RUNTIME_RELEASE", "invented"),
        ("EXPECTED_ACCOUNT_ID", "wrong-account"),
        ("ALLOWED_INSTANCE_IDS", "i-bad"),
        ("RUNTIME_LIMITS", '{"tool_calls":999999}'),
        ("LOGS_TOOL_ARN", "arn:aws:lambda:eu-central-1:999999999999:function:logs:1"),
        ("METRICS_TOOL_ARN", "arn:aws:lambda:eu-central-1:123456789012:function:metrics:$LATEST"),
    ],
)
def test_invalid_bindings_are_rejected(configured, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    assert AppConfig.from_env().problems()


def test_production_requires_qualified_chat_gateway(configured, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CHAT_FUNCTION_ARN", raising=False)
    assert AppConfig.from_env().problems()
    monkeypatch.setenv("CHAT_FUNCTION_ARN", "arn:aws:lambda:eu-central-1:123456789012:function:chat:4")
    assert AppConfig.from_env().problems() == []


def test_password_is_not_in_configuration_repr(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "fixture-password-value")
    assert "fixture-password-value" not in repr(AppConfig.from_env())


@pytest.mark.parametrize(
    "command", ["render", "prepare", "upload", "change-set", "execute", "seal", "collect", "verify-candidate"]
)
def test_retired_classic_cli_commands_rejected_before_aws(monkeypatch, command):
    import sys
    from unittest.mock import Mock

    import boto3

    from infra.__main__ import main

    cloud = Mock()
    monkeypatch.setattr(boto3, "client", cloud)
    monkeypatch.setattr(sys, "argv", ["infra", command])
    with pytest.raises(SystemExit) as refused:
        main()
    assert refused.value.code == 2
    cloud.assert_not_called()


@pytest.mark.parametrize("target", ["classic", "unknown"])
def test_incident_dispatch_rejects_retired_target_before_request_or_aws(monkeypatch, target):
    from unittest.mock import Mock

    from kira import execution, pipeline

    request = Mock()
    monkeypatch.setattr(execution, "incident_request", request)
    monkeypatch.setenv("RUNTIME_TARGET", target)
    with pytest.raises(ValueError, match="Unsupported runtime target"):
        pipeline.invoke_agent({}, 100)
    request.assert_not_called()
