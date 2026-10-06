"""Bounded Bedrock chat requests with safe failures and recoverable partial text."""

import codecs
import time
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from kira.transport import clip_utf8, error_result

MAX_PROMPT_CHARS = 4000
MAX_OUTPUT_BYTES = 32_000
MAX_STREAM_EVENTS = 2048
MAX_REQUEST_SECONDS = 180
MAX_HISTORY_MESSAGES = 24
MAX_REQUESTS_PER_HOUR = 20
SESSION_SECONDS = 1800


@dataclass(frozen=True)
class ChatResult:
    text: str
    status: str
    code: str = ""
    message: str = ""
    reference: str = ""


def failure(code, message, partial=""):
    problem = error_result(code, message)
    return ChatResult(partial, "partial" if partial else "error", code, message, problem["request_id"])


def make_client(settings):
    return boto3.client(
        "bedrock-agent-runtime",
        region_name=settings.region,
        config=Config(
            connect_timeout=5, read_timeout=45, retries={"total_max_attempts": 1, "mode": "standard"}
        ),
    )


def invoke(prompt, session_id, settings, *, factory=make_client, clock=time.monotonic, history=()):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        return failure("INVALID_PROMPT", f"Enter a question of 1–{MAX_PROMPT_CHARS} characters.")
    if settings.problems():
        return failure(
            "NOT_CONFIGURED", "Complete the agent connection settings before starting an investigation."
        )
    started = clock()
    stream = None
    text = ""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    try:
        if settings.runtime_target in {"standalone", "agentcore"}:
            from kira import agentcore, execution

            payload = {
                "version": 1,
                "release": settings.runtime_release,
                "mode": "chat",
                "prompt": prompt.strip(),
                "history": [
                    {"role": m["role"], "content": m["content"]}
                    for m in history[-MAX_HISTORY_MESSAGES:]
                    if m.get("content")
                ],
            }
            if settings.runtime_target == "standalone":
                result = execution.execute(payload)
            else:
                result = agentcore.invoke(
                    payload,
                    arn=settings.agentcore_arn,
                    qualifier=settings.agentcore_endpoint,
                    region=settings.region,
                    account=settings.account_id,
                    session_id="chat_" + session_id,
                    deadline=time.time() + MAX_REQUEST_SECONDS,
                )
            text = clip_utf8(result["text"], MAX_OUTPUT_BYTES)
            if result["complete"]:
                return ChatResult(text, "ok")
            return failure(
                "INVESTIGATION_INCOMPLETE",
                "Investigation stopped with incomplete evidence or an execution limit.",
                text,
            )
        client = factory(settings)  # Credential resolution/client creation is inside the error boundary.
        if clock() - started >= MAX_REQUEST_SECONDS:
            return failure("REQUEST_TIMEOUT", "Connection setup exceeded the request time budget.")
        response = client.invoke_agent(
            agentId=settings.agent_id,
            agentAliasId=settings.alias_id,
            sessionId=session_id,
            inputText=prompt.strip(),
        )
        stream = response.get("completion")
        if stream is None:
            return failure(
                "EMPTY_RESPONSE", "The agent returned no answer. You can retry in a new conversation."
            )
        for count, event in enumerate(stream, 1):
            if clock() - started >= MAX_REQUEST_SECONDS or count > MAX_STREAM_EVENTS:
                return failure(
                    "REQUEST_LIMIT",
                    "Investigation stopped at its request limit. Any text received is preserved.",
                    text,
                )
            if not isinstance(event, dict):
                return failure("INVALID_RESPONSE", "The agent returned an unsupported response.", text)
            if any(key.endswith("Exception") for key in event):
                return failure(
                    "AGENT_STREAM_FAILED",
                    "The agent interrupted its response. Check model access and service availability.",
                    text,
                )
            if "returnControl" in event:
                return failure(
                    "AGENT_CONFIGURATION",
                    "This agent requires a tool execution mode the chat client does not support.",
                    text,
                )
            payload = (event.get("chunk") or {}).get("bytes", b"")
            text += decoder.decode(payload)
            if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                return failure(
                    "OUTPUT_LIMIT",
                    "Response reached the display limit. Narrow the investigation.",
                    clip_utf8(text, MAX_OUTPUT_BYTES),
                )
        text += decoder.decode(b"", final=True)
        if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
            return failure(
                "OUTPUT_LIMIT",
                "Response reached the display limit. Narrow the investigation.",
                clip_utf8(text, MAX_OUTPUT_BYTES),
            )
        if not text.strip():
            return failure(
                "EMPTY_RESPONSE", "The agent returned no answer. You can retry in a new conversation."
            )
        return ChatResult(clip_utf8(text, MAX_OUTPUT_BYTES), "ok")
    except (NoCredentialsError, PartialCredentialsError):
        return failure(
            "CREDENTIALS_UNAVAILABLE",
            "AWS credentials are unavailable. Sign in to the intended profile or check the workload role.",
            text,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {
            "ExpiredToken",
            "ExpiredTokenException",
            "UnrecognizedClientException",
            "InvalidClientTokenId",
        }:
            return failure(
                "CREDENTIALS_EXPIRED",
                "AWS credentials are no longer valid. Refresh your sign-in and retry.",
                text,
            )
        if code in {"AccessDeniedException", "UnauthorizedException"}:
            return failure(
                "ACCESS_DENIED",
                "The configured identity cannot invoke this agent or its model. Check the role and model access.",
                text,
            )
        return failure(
            "AGENT_UNAVAILABLE",
            "The agent is unavailable. Check the region, alias, model access and service status.",
            text,
        )
    except Exception:
        return failure(
            "REQUEST_FAILED",
            "The investigation connection failed. Any received text is preserved; you can retry.",
            text,
        )
    finally:
        if stream is not None and callable(getattr(stream, "close", None)):
            try:
                stream.close()
            except Exception:
                pass


def recent_attempts(attempts, now):
    return [stamp for stamp in attempts if now - stamp < 3600][-MAX_REQUESTS_PER_HOUR:]


def append_exchange(messages, prompt, result):
    return (
        messages
        + [
            {"role": "user", "content": prompt},
            {
                "role": "assistant",
                "content": result.text,
                "status": result.status,
                "code": result.code,
                "message": result.message,
                "reference": result.reference,
            },
        ]
    )[-MAX_HISTORY_MESSAGES:]
