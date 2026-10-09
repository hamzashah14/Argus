"""DynamoDB stream: send durable intents to isolated queues."""

from argus import pipeline


def lambda_handler(event, context):
    return pipeline.dispatch(event, context)
