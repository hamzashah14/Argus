"""Repair missed streams and expired leases."""

from argus import pipeline


def lambda_handler(event, context):
    return pipeline.reconcile(event, context)
