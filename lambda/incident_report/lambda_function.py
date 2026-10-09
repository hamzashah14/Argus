"""Publish a follow-up reference without exposing private report content."""

from argus import pipeline


def lambda_handler(event, context):
    return pipeline.report(event, context)
