"""SQS ingress: commit the source event and first intents atomically."""

from argus import pipeline


def lambda_handler(event, context):
    return pipeline.ingest(event, context)
