import json
import time
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from kira import chat, runtime, status
from tests.helpers import ROOT


@pytest.fixture
def settings(monkeypatch):
    for key, value in {
        "APP_PASSWORD": "synthetic-workspace-password",
        "BEDROCK_REGION": "eu-central-1",
        "RUNTIME_TARGET": "standalone",
        "EXPECTED_ACCOUNT_ID": "123456789012",
        "BEDROCK_MODEL_ID": "fixture-model",
        "RUNTIME_RELEASE": "a" * 64,
        "RUNTIME_LIMITS": json.dumps(runtime.Limits().__dict__),
        "LOGS_TOOL_ARN": "arn:aws:lambda:eu-central-1:123456789012:function:logs:1",
        "METRICS_TOOL_ARN": "arn:aws:lambda:eu-central-1:123456789012:function:metrics:1",
        "ENVIRONMENT": "development",
    }.items():
        monkeypatch.setenv(key, value)


def app(authenticated=True):
    test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=10)
    if authenticated:
        test.session_state["authenticated"] = True
        test.session_state["auth_at"] = time.monotonic()
    return test


def button(test, label):
    return next(item for item in test.button if item.label == label)


def test_missing_password_safe_setup(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    test = app(False).run()
    assert not test.exception and any("APP_PASSWORD" in item.value for item in test.info)
    assert not test.chat_input


def test_missing_runtime_configuration_disables_input(settings, monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID")
    test = app().run()
    assert not test.exception and test.chat_input[0].disabled
    assert any("not been checked" in item.value for item in test.info)


def test_production_without_oidc_uses_password_login_and_in_process_chat(settings, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("KIRA_AUTH_MODE", raising=False)
    invoke = Mock(return_value=chat.ChatResult("Answer", "ok"))
    monkeypatch.setattr(chat, "invoke", invoke)
    test = app(False).run()
    assert not test.exception and not test.error and test.text_input and not test.chat_input
    assert not any(item.label == "Sign in with SSO" for item in test.button)
    test.text_input[0].input("synthetic-workspace-password")
    button(test, "Open workspace").click().run()
    assert test.session_state["authenticated"] and not test.exception and not test.chat_input[0].disabled
    test.chat_input[0].set_value("Investigate the incident").run()
    assert not test.exception and any("Answer" in item.value for item in test.markdown)
    invoke.assert_called_once()
    assert "access_ticket" not in invoke.call_args.kwargs


def test_login_and_logout(settings):
    test = app(False).run()
    test.text_input[0].input("synthetic-workspace-password")
    button(test, "Open workspace").click().run()
    assert test.session_state["authenticated"] and not test.exception
    button(test, "Sign out").click().run()
    assert not test.session_state["authenticated"] and test.session_state["messages"] == []


@pytest.mark.parametrize(
    "code,message",
    [
        ("CREDENTIALS_UNAVAILABLE", "AWS credentials are unavailable."),
        ("CREDENTIALS_EXPIRED", "Refresh your AWS sign-in."),
        ("AGENT_UNAVAILABLE", "The model or agent is unavailable."),
        ("EMPTY_RESPONSE", "The agent returned no answer."),
    ],
)
def test_ui_safe_failure_and_retry(settings, monkeypatch, code, message):
    invoke = Mock(
        side_effect=[
            chat.ChatResult("", "error", code, message, "test-reference"),
            chat.ChatResult("Recovered answer", "ok"),
        ]
    )
    monkeypatch.setattr(chat, "invoke", invoke)
    test = app().run()
    original_session = test.session_state["session_id"]
    test.chat_input[0].set_value("Investigate the incident").run()
    assert not test.exception and any(item.value == message for item in test.warning)
    assert any(code in item.value for item in test.caption)
    button(test, "Retry in a new conversation").click().run()
    assert test.session_state["session_id"] != original_session
    assert any("Recovered answer" in item.value for item in test.markdown)
    assert invoke.call_count == 2


def test_ui_partial_answer_visible(settings, monkeypatch):
    monkeypatch.setattr(
        chat,
        "invoke",
        lambda *args, **kwargs: chat.ChatResult(
            "Evidence received before interruption",
            "partial",
            "REQUEST_FAILED",
            "Connection interrupted",
            "ref",
        ),
    )
    test = app().run()
    test.chat_input[0].set_value("Investigate").run()
    assert not test.exception
    assert any("Evidence received" in item.value for item in test.markdown)
    assert any("Partial result" in item.value for item in test.caption)


def test_long_history_requires_new_context(settings):
    test = app().run()
    old = test.session_state["session_id"]
    test.session_state["messages"] = [{"role": "user", "content": "question"}] * chat.MAX_HISTORY_MESSAGES
    test.run()
    assert test.chat_input[0].disabled
    button(test, "New conversation").click().run()
    assert test.session_state["messages"] == [] and test.session_state["session_id"] != old
    assert not test.chat_input[0].disabled


def test_hourly_work_limit_survives_new_conversation(settings):
    test = app().run()
    test.session_state["attempts"] = [time.monotonic()] * chat.MAX_REQUESTS_PER_HOUR
    test.run()
    assert test.chat_input[0].disabled
    button(test, "New conversation").click().run()
    assert test.chat_input[0].disabled


def test_expired_session_clears_private_history(settings):
    test = app().run()
    test.session_state["auth_at"] = time.monotonic() - chat.SESSION_SECONDS - 1
    test.session_state["messages"] = [{"role": "user", "content": "private question"}]
    test.run()
    assert not test.session_state["authenticated"] and not test.session_state["messages"]
    assert not test.chat_input


def test_incident_link_requires_sign_in_and_shows_authorized_report(settings, monkeypatch):
    incident_id = "a" * 32
    read = Mock(
        return_value={
            "incident_id": incident_id,
            "instance_id": "i-0123456789abcdef0",
            "occurred_at": "2026-10-05T10:00:00Z",
            "status": "COMPLETE",
            "report": "Redacted evidence from private storage",
        }
    )
    monkeypatch.setattr(status, "load", read)
    signed_out = app(False)
    signed_out.query_params["incident"] = incident_id
    signed_out.run()
    assert not signed_out.exception
    read.assert_not_called()
    signed_in = app()
    signed_in.query_params["incident"] = incident_id
    signed_in.run()
    assert not signed_in.exception
    read.assert_called_once_with(incident_id)
    assert any("Redacted evidence" in item.value for item in signed_in.text_area)


def test_brand_assets_exist_and_are_transparent_pngs():
    from PIL import Image

    for name in ("kira-mark.png", "kira-logo-white.png", "kira-logo-black.png"):
        with Image.open(ROOT / "assets" / name) as image:
            assert image.format == "PNG" and image.mode == "RGBA"
