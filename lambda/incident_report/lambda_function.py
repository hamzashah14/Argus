"""Publish a follow-up reference without exposing private report content."""

from kira import pipeline


def lambda_handler(event, context):
    return pipeline.report(event, context)
