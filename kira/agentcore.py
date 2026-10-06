"""Bounded SigV4 AgentCore adapter. Never retry/fail over an ambiguous invocation."""

import json
import re
import time

from kira.runtime import RuntimeStop, sdk_client

MAX_WIRE_BYTES = 96000


def validate_target(arn, qualifier, region, account):
    if (
        not isinstance(arn, str)
        or not re.fullmatch(
            rf"arn:aws:bedrock-agentcore:{re.escape(region)}:{re.escape(account)}:runtime/[A-Za-z][A-Za-z0-9_]*-[A-Za-z0-9]{{10}}",
            arn,
        )
        or not isinstance(qualifier, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", qualifier)
        or qualifier == "DEFAULT"
    ):
        raise ValueError("AgentCore requires an explicit release endpoint in the intended account/region")


def invoke(payload, *, arn, qualifier, region, account, session_id, deadline, client=None):
    validate_target(arn, qualifier, region, account)
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{33,256}", session_id):
        raise ValueError("Invalid AgentCore session identifier")
    wire = json.dumps(payload).encode()
    if len(wire) > 96000 or deadline - time.time() < 25:
        raise RuntimeStop("REQUEST_LIMIT")
    client = client or sdk_client("bedrock-agentcore", region, 15)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier=qualifier,
        runtimeSessionId=session_id,
        contentType="application/json",
        accept="text/event-stream",
        payload=wire,
    )
    stream = response.get("response")
    if stream is None:
        raise RuntimeError("Remote execution response missing")
    try:
        if (
            response.get("statusCode") != 200
            or response.get("contentType", "").split(";")[0] != "text/event-stream"
        ):
            raise RuntimeError("Remote execution response unsupported")
        size, lines, data = 0, 0, []
        for raw in stream.iter_lines(chunk_size=1):
            size += len(raw) + 1
            lines += 1
            if time.time() >= deadline or size > MAX_WIRE_BYTES or lines > 512:
                raise RuntimeError("Remote execution limit reached")
            if raw.startswith(b"data: "):
                data.append(raw[6:])
            elif raw == b"" and data:
                event = json.loads(b"\n".join(data))
                data = []
                if event.get("event") == "error":
                    raise RuntimeError("Remote execution failed; inspect the durable incident")
                if event.get("event") == "result":
                    result = event["result"]
                    if (
                        not isinstance(result, dict)
                        or type(result.get("version")) is not int
                        or result.get("version") != 1
                        or result.get("release") != payload["release"]
                        or type(result.get("complete")) is not bool
                        or not isinstance(result.get("text"), str)
                        or len(result["text"].encode()) > 64000
                        or not isinstance(result.get("code"), str)
                        or len(result["code"]) > 128
                        or not isinstance(result.get("usage"), dict)
                        or set(result["usage"]) != {"input_tokens", "output_tokens"}
                        or any(type(v) is not int or v < 0 for v in result["usage"].values())
                        or any(
                            not isinstance(result.get(key), list)
                            or any(
                                not isinstance(v, str) or v not in {"fetch_logs", "fetch_metrics"}
                                for v in result[key]
                            )
                            or len(result[key]) != len(set(result[key]))
                            for key in ("tools", "evidence")
                        )
                    ):
                        raise RuntimeError("Remote result contract mismatch")
                    return result
        raise RuntimeError("Remote execution ended without a result")
    finally:
        stream.close()
