"""Customer-owned Phase 4 observation entrypoint."""

from kira.observability import canary_sender


def lambda_handler(event, context):
    return canary_sender(event, context)
