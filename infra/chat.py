"""Dedicated chat capacity and exact release binding, independent of automatic work."""

import re

from infra import owned_runtime
from infra.spec import name
from infra.templates import add_function, statement, template
from infra.verify import VerificationError


def version(spec, bindings):
    arn = bindings.get("chat_version", {}).get("ChatVersionArn", "")
    prefix = f"arn:aws:lambda:{spec['monitor_region']}:{spec['account_id']}:function:{name(spec, 'chat-investigate', True)}:"
    if not re.fullmatch(re.escape(prefix) + r"[1-9][0-9]*", arn):
        raise VerificationError("Bind the dedicated qualified chat version")
    return arn


def environment(spec, config, bindings):
    env = owned_runtime.environment(spec, config, bindings)
    env["EXECUTION_PURPOSE"] = "chat"
    if config["runtime_target"] == "agentcore":
        remote = bindings.get("agentcore_chat")
        if not remote:
            raise VerificationError("Collect the independent chat AgentCore endpoint")
        env.update(AGENTCORE_RUNTIME_ARN=remote["RuntimeArn"], AGENTCORE_ENDPOINT=remote["EndpointName"])
        for key in ("LOGS_TOOL_ARN", "METRICS_TOOL_ARN"):
            del env[key]
    return env


def runtime(spec, config, bindings, artifact):
    t = template(spec, spec["monitor_region"], "Immutable dedicated chat gateway")
    if config["runtime_target"] == "standalone":
        permissions = owned_runtime.model_permissions(spec, bindings)
        permissions += owned_runtime.identity_permissions(spec, config, bindings, purpose="chat")
    else:
        remote = bindings["agentcore_chat"]
        permissions = [
            statement("bedrock-agentcore:InvokeAgentRuntime", [remote["RuntimeArn"], remote["EndpointArn"]])
        ]
    add_function(
        t,
        spec,
        "Chat",
        "chat_investigate",
        artifact,
        environment(spec, config, bindings),
        spec["monitor_region"],
        permissions,
        210,
    )
    t["Resources"]["Chat"]["Properties"]["ReservedConcurrentExecutions"] = 1
    return t


def ui_environment(spec, config, bindings):
    env = owned_runtime.environment(spec, config, bindings)
    for key in ("LOGS_TOOL_ARN", "METRICS_TOOL_ARN"):
        env.pop(key, None)
    env["CHAT_FUNCTION_ARN"] = version(spec, bindings)
    env["EXECUTION_PURPOSE"] = "chat"
    return env


def fixture_bindings(spec, bindings):
    """Offline synthetic bindings only, never cloud-discovered resources."""
    bindings["chat_version"] = {
        "ChatVersionArn": f"arn:aws:lambda:{spec['monitor_region']}:{spec['account_id']}:function:{name(spec, 'chat-investigate', True)}:1"
    }
    if "agentcore" in bindings:
        arn = f"arn:aws:bedrock-agentcore:{spec['bedrock_region']}:{spec['account_id']}:runtime/{name(spec, 'agentcore-chat', True).replace('-', '_')}-1234567890"
        endpoint = bindings["agentcore"]["EndpointName"]
        bindings["agentcore_chat"] = {
            "RuntimeArn": arn,
            "EndpointName": endpoint,
            "RuntimeVersion": "1",
            "EndpointArn": arn + "/runtime-endpoint/" + endpoint + "-1234567890",
        }
        bindings["agentcore_chat_candidate"] = {"RuntimeId": arn.split("/")[-1], "RuntimeVersion": "1"}
