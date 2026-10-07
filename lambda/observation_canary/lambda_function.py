"""Customer-owned observation observation entrypoint."""

from kira.observability import canary_sender


def lambda_handler(event, context):
    return canary_sender(event, context)
