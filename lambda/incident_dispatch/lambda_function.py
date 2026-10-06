"""DynamoDB stream: send durable intents to isolated queues."""

from kira import pipeline


def lambda_handler(event, context):
    return pipeline.dispatch(event, context)
