"""Killable SDK client for the separate, qualified chat Lambda; no retry/fallback."""

import json
import os
import re
import sys
import time

from kira import agentcore
from kira.runtime import sdk_client


def invoke(payload, *, arn=None, region=None, account=None, deadline=None, client=None):
    arn = arn or os.environ["CHAT_FUNCTION_ARN"]
    region = region or os.environ["MONITOR_REGION"]
    account = account or os.environ["EXPECTED_ACCOUNT_ID"]
    deadline = deadline or time.time() + 180
    if (
        not re.fullmatch(
            rf"arn:aws:lambda:{re.escape(region)}:{account}:function:[A-Za-z0-9_-]+:[1-9][0-9]*", arn
        )
        or len(json.dumps(payload).encode()) > 96000
    ):
        raise ValueError("Qualified customer chat gateway required")
    if client is None:
        raw = agentcore.run_child(
            [sys.executable, "-m", "kira.chat_gateway"],
            json.dumps(
                {"payload": payload, "arn": arn, "region": region, "account": account, "deadline": deadline}
            ).encode(),
            deadline,
        )
        result = json.loads(raw)
        agentcore.validate_result(result, payload)
        return result
    response = client.invoke(
        FunctionName=arn,
        InvocationType="RequestResponse",
        Payload=json.dumps({"runtime_chat": payload}).encode(),
    )
    stream = response["Payload"]
    try:
        data = stream.read(96001)
    finally:
        stream.close()
    if (
        response.get("FunctionError")
        or response.get("StatusCode") != 200
        or len(data) > 96000
        or time.time() >= deadline
    ):
        raise RuntimeError("Chat gateway interrupted; no automatic retry")
    result = json.loads(data)
    agentcore.validate_result(result, payload)
    return result


def main():
    try:
        request = json.loads(sys.stdin.buffer.read(102400))
        request["client"] = sdk_client("lambda", request["region"], 190)
        print(json.dumps(invoke(**request)))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
