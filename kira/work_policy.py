"""Customer-selected limits with safe defaults and checked ceilings."""

import json
import os
from dataclasses import asdict

from kira.runtime import Limits

DEFAULT = {
    "login_user": 10,
    "login_global": 100,
    "chat_user": 4,
    "chat_global": 8,
    "tokens_user": 96000,
    "tokens_global": 192000,
    "audit_days": 30,
    "chat_limits": asdict(
        Limits(tokens_reserved=24000, model_steps=6, tool_calls=6, log_queries=12, output_tokens=1024)
    ),
}


def validate(value):
    if set(value) != set(DEFAULT):
        raise ValueError("Explicit complete work policy required")
    for key, maximum in [
        ("login_user", 100),
        ("login_global", 1000),
        ("chat_user", 100),
        ("chat_global", 1000),
        ("tokens_user", 1000000),
        ("tokens_global", 10000000),
        ("audit_days", 90),
    ]:
        if type(value[key]) is not int or not 1 <= value[key] <= maximum:
            raise ValueError("Invalid work policy allowance")
    if (
        value["login_user"] > value["login_global"]
        or value["chat_user"] > value["chat_global"]
        or value["tokens_user"] > value["tokens_global"]
    ):
        raise ValueError("User allowance exceeds shared allowance")
    limits = Limits(**value["chat_limits"])
    if limits.tokens_reserved > value["tokens_user"]:
        raise ValueError("Request tokens exceed user allowance")
    return value


def configured():
    raw = os.environ["KIRA_WORK_POLICY"]
    if len(raw) > 4096:
        raise ValueError("Work policy too large")
    return validate(json.loads(raw))
