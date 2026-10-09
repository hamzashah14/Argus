"""Bounded Bedrock chat requests with safe failures and recoverable partial text."""

import time
from dataclasses import dataclass, field

from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from kira import identity, safety
from kira.runtime import RuntimeStop
from kira.transport import clip_utf8, error_result

MAX_PROMPT_CHARS = 4000
MAX_OUTPUT_BYTES = 32_000
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
    usage: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "text", safety.text(self.text))


def failure(code, message, partial=""):
    problem = error_result(code, message)
    return ChatResult(partial, "partial" if partial else "error", code, message, problem["request_id"])


def invoke(prompt, session_id, settings, *, history=(), access_ticket=None, allowed=None):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        return failure("INVALID_PROMPT", f"Enter a question of 1–{MAX_PROMPT_CHARS} characters.")
    if settings.problems():
        return failure(
            "NOT_CONFIGURED", "Complete the agent connection settings before starting an investigation."
        )
    text = ""
    try:
        if identity.required():
            identity.Sessions().authorize(access_ticket, "chat")
        from kira import agentcore, execution

        payload = {
            "version": 1,
            "release": "local" if settings.local_tools else settings.runtime_release,
            "mode": "chat",
            "prompt": prompt.strip(),
            "history": [
                {"role": m["role"], "content": m["content"]}
                for m in history[-MAX_HISTORY_MESSAGES:]
                if m.get("content")
            ],
        }
        if identity.required():
            payload["access_ticket"] = access_ticket
        if identity.required():
            from kira.chat_gateway import invoke as invoke_gateway

            result = invoke_gateway(payload)
        elif settings.runtime_target == "standalone":
            options = {}
            if settings.local_tools:
                from kira import local_tools

                options["local"] = local_tools.load(settings.local_tools)
            if allowed is not None:
                options["allowed"] = frozenset(allowed)
            result = execution.execute(payload, **options)
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
            if len(result["text"].encode()) > MAX_OUTPUT_BYTES:
                return failure(
                    "OUTPUT_LIMIT",
                    "The validated report exceeds the display budget. Narrow the investigation.",
                    text,
                )
            return ChatResult(text, "ok", usage=result.get("usage") or {})
        if result.get("code") in {"USER_OR_SHARED_ALLOWANCE_EXHAUSTED", "ADMISSION_UNAVAILABLE"}:
            return failure(
                "WORK_ALLOWANCE",
                "Your user or shared work allowance is unavailable. Wait for the next window or contact your operator.",
            )
        if result.get("code") == "ACCESS_DENIED":
            return failure("ACCESS_DENIED", "Sign in again or ask your operator to review access.")
        return failure(
            "INVESTIGATION_INCOMPLETE",
            "Investigation stopped with incomplete evidence or an execution limit.",
            text,
        )
    except RuntimeStop as exc:
        if str(exc) in {"USER_OR_SHARED_ALLOWANCE_EXHAUSTED", "ADMISSION_UNAVAILABLE"}:
            return failure(
                "WORK_ALLOWANCE",
                "Your user or shared work allowance is unavailable. Wait for the next window or contact your operator.",
            )
        return failure("INVESTIGATION_INCOMPLETE", "Investigation stopped at an execution limit.")
    except identity.AccessDenied:
        return failure("ACCESS_DENIED", "Sign in again or ask your operator to review access.")
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
            "The agent is unavailable. Check the region, runtime, model access and service status.",
            text,
        )
    except Exception:
        return failure(
            "REQUEST_FAILED",
            "The investigation connection failed. Any received text is preserved; you can retry.",
            text,
        )


def recent_attempts(attempts, now):
    return [stamp for stamp in attempts if now - stamp < 3600][-MAX_REQUESTS_PER_HOUR:]


def append_exchange(messages, prompt, result):
    return (
        messages
        + [
            {"role": "user", "content": safety.text(prompt)},
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
