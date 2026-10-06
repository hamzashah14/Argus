"""Claim and fence investigation work; save redacted versioned evidence."""

import os

from kira import agentcore, execution, pipeline


def lambda_handler(event, context):
    if set(event) == {"runtime_canary"}:
        if os.getenv("ALLOW_RUNTIME_CANARY") != "true" or event["runtime_canary"].get("mode") != "chat":
            raise ValueError("Runtime canary is staging-only")
        if execution.required("RUNTIME_TARGET") == "standalone":
            return execution.execute(event["runtime_canary"])
        import time
        import uuid

        return agentcore.invoke(
            event["runtime_canary"],
            arn=execution.required("AGENTCORE_RUNTIME_ARN"),
            qualifier=execution.required("AGENTCORE_ENDPOINT"),
            region=execution.required("BEDROCK_REGION"),
            account=execution.required("EXPECTED_ACCOUNT_ID"),
            session_id="canary_" + str(uuid.uuid4()),
            deadline=time.time() + min(180, context.get_remaining_time_in_millis() / 1000 - 30),
        )
    return pipeline.work(event, context)
