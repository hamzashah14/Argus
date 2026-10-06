"""Customer-owned Phase 4 observation entrypoint."""

from kira.observability import observer


def lambda_handler(event, context):
    return observer(event, context)
