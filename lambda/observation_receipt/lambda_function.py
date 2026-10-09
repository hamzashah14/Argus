"""Customer-owned observation observation entrypoint."""

from argus.observability import recipient


def lambda_handler(event, context):
    return recipient(event, context)
