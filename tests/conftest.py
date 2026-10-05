import socket

import boto3
import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests must mock AWS explicitly; never use the operator's credentials."""

    def denied(*args, **kwargs):
        raise AssertionError("Network/AWS call not mocked in this test")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(boto3, "client", denied)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("ALLOWED_INSTANCE_IDS", "i-0123456789abcdef0")
    monkeypatch.setenv("LOG_CURSOR_SECRET", "synthetic-cursor-key-for-offline-tests-only")
