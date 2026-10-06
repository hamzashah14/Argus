"""Publish an independent minimal initial alert."""

from kira import pipeline


def lambda_handler(event, context):
    return pipeline.initial(event, context)
