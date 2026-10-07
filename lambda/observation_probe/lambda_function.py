"""Customer-owned observation observation entrypoint."""

from kira.observability import observer


def lambda_handler(event, context):
    return observer(event, context)
