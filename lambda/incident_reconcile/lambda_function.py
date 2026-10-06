"""Repair missed streams and expired leases."""

from kira import pipeline


def lambda_handler(event, context):
    return pipeline.reconcile(event, context)
