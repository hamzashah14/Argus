from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from kira import chat
from kira.config import AppConfig

SETTINGS = AppConfig("eu-central-1", "ABCDEFGHIJ", "ABCDEFGHIJ", "synthetic-password")


def factory(stream):
    client = MagicMock()
    client.invoke_agent.return_value = {"completion": stream}
    return lambda settings: client


def test_client_construction_failure_handled():
    def fail(settings):
        raise NoCredentialsError()

    result = chat.invoke("investigate", "session", SETTINGS, factory=fail)
    assert result.code == "CREDENTIALS_UNAVAILABLE" and result.reference


@pytest.mark.parametrize(
    "code,expected",
    [
        ("ExpiredTokenException", "CREDENTIALS_EXPIRED"),
        ("AccessDeniedException", "ACCESS_DENIED"),
        ("ResourceNotFoundException", "AGENT_UNAVAILABLE"),
    ],
)
def test_provider_errors_are_safe(code, expected):
    client = MagicMock()
    client.invoke_agent.side_effect = ClientError(
        {"Error": {"Code": code, "Message": "DO-NOT-DISPLAY-secret"}}, "InvokeAgent"
    )
    result = chat.invoke("investigate", "session", SETTINGS, factory=lambda settings: client)
    assert result.code == expected and "DO-NOT" not in repr(result)


def test_partial_content_preserved_on_stream_failure():
    def stream():
        yield {"chunk": {"bytes": b"Useful evidence"}}
        raise RuntimeError("private-provider-details")

    result = chat.invoke("investigate", "session", SETTINGS, factory=factory(stream()))
    assert result.status == "partial" and result.text == "Useful evidence"
    assert "private-provider" not in repr(result)


def test_utf8_split_across_chunks_is_preserved():
    raw = "Evidence: 界🙂".encode()
    stream = [{"chunk": {"bytes": raw[i : i + 1]}} for i in range(len(raw))]
    result = chat.invoke("investigate", "session", SETTINGS, factory=factory(stream))
    assert result.status == "ok" and result.text == "Evidence: 界🙂"


@pytest.mark.parametrize(
    "stream,expected",
    [
        ([], "EMPTY_RESPONSE"),
        ([{"accessDeniedException": {"message": "secret"}}], "AGENT_STREAM_FAILED"),
        ([{"returnControl": {}}], "AGENT_CONFIGURATION"),
    ],
)
def test_empty_or_unsupported_stream(stream, expected):
    assert chat.invoke("investigate", "session", SETTINGS, factory=factory(stream)).code == expected


def test_output_limit_and_stream_close():
    stream = MagicMock()
    stream.__iter__.return_value = iter([{"chunk": {"bytes": ("界" * 30000).encode()}}])
    result = chat.invoke("investigate", "session", SETTINGS, factory=factory(stream))
    assert result.code == "OUTPUT_LIMIT" and len(result.text.encode()) <= chat.MAX_OUTPUT_BYTES
    stream.close.assert_called_once()


def test_request_deadline_between_events():
    ticks = iter([0, 0, 1, 181])
    result = chat.invoke(
        "investigate",
        "session",
        SETTINGS,
        factory=factory([{"chunk": {"bytes": b"first"}}, {"chunk": {"bytes": b"too late"}}]),
        clock=lambda: next(ticks),
    )
    assert result.text == "first" and result.code == "REQUEST_LIMIT"


@pytest.mark.parametrize("prompt", ["", "   ", "x" * 4001, None])
def test_input_limits_do_not_construct_client(prompt):
    client_factory = MagicMock()
    assert chat.invoke(prompt, "session", SETTINGS, factory=client_factory).code == "INVALID_PROMPT"
    client_factory.assert_not_called()


def test_bounded_history_and_attempt_window():
    messages = []
    for _ in range(100):
        messages = chat.append_exchange(messages, "question", chat.ChatResult("answer", "ok"))
    assert len(messages) == chat.MAX_HISTORY_MESSAGES
    assert chat.recent_attempts([0, 100, 3601], 3700) == [3601]


def test_incomplete_final_utf8_cannot_silently_exceed_output_budget():
    stream = [{"chunk": {"bytes": b"x" * (chat.MAX_OUTPUT_BYTES - 1) + b"\xf0"}}]
    result = chat.invoke("investigate", "session", SETTINGS, factory=factory(stream))
    assert result.code == "OUTPUT_LIMIT" and result.status == "partial"
    assert len(result.text.encode()) <= chat.MAX_OUTPUT_BYTES
