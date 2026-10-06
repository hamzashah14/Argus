"""SQS ingress: commit the source event and first intents atomically."""

from kira import pipeline


def lambda_handler(event, context):
    return pipeline.ingest(event, context)
