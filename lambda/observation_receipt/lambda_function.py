"""Customer-owned Phase 4 observation entrypoint."""

from kira.observability import recipient


def lambda_handler(event, context):
    return recipient(event, context)
