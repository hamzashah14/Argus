"""Authenticated, expiring continuation bound to the deployment and instance."""

import base64
import hashlib
import hmac
import json
import os
import time

from kira.transport import dumps


def scope(instance_id, prefix, region):
    return {
        "instance": instance_id,
        "prefix": prefix,
        "region": region,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "account": os.getenv("EXPECTED_ACCOUNT_ID", "local"),
    }


def key():
    secret = os.getenv("LOG_CURSOR_SECRET", "")
    if len(secret.encode()) < 32:
        raise ValueError("LOG_CURSOR_SECRET must contain at least 32 bytes to paginate discovery.")
    return secret.encode()


def encode(next_token, expected_scope):
    payload = dumps(
        {"v": 1, "scope": expected_scope, "next": next_token, "expires": int(time.time()) + 3600}
    ).encode()
    signature = hmac.new(key(), payload, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(signature + payload).decode()
    if len(token) > 6000:
        raise ValueError("CloudWatch continuation exceeds the supported cursor limit.")
    return token


def decode(token, expected_scope):
    try:
        if not isinstance(token, str) or len(token) > 6000:
            raise ValueError()
        raw = base64.b64decode(token.encode(), altchars=b"-_", validate=True)
        signature, payload = raw[:32], raw[32:]
        if not hmac.compare_digest(signature, hmac.new(key(), payload, hashlib.sha256).digest()):
            raise ValueError()
        value = json.loads(payload)
        if value["v"] != 1 or value["scope"] != expected_scope or value["expires"] < time.time():
            raise ValueError()
        if not isinstance(value["next"], str) or not value["next"]:
            raise ValueError()
        return value["next"]
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("Continuation token is invalid, expired, or belongs to another scope.") from exc
