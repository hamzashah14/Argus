"""
Generate sample CloudWatch log data for AIOps demo.
Run this in AWS CloudShell or locally with valid AWS credentials.

Usage:
    python generate_sample_data.py --region eu-north-1
"""

import boto3
import time
import random
import argparse

ERRORS = [
    "ERROR PostgreSQL connection pool exhausted - max_connections=100, active=100, waiting=47",
    "ERROR 503 Service Unavailable - Cannot acquire database connection from pool",
    "ERROR Request timeout after 30000ms - POST /api/orders - upstream connection refused",
    "ERROR Circuit breaker OPEN for payment-service - failure rate 78%",
    "WARN High latency detected: p99=4523ms p95=2100ms for /api/search",
    "WARN Slow query: SELECT * FROM orders WHERE status=pending - 3400ms",
    "ERROR OOM Kill in container task-id=abc123 - memory limit 512MB exceeded",
    "INFO Health check passed - all dependencies OK",
    "INFO Request completed - GET /api/health - 200 OK - 12ms",
    "ERROR Connection refused to Redis at redis-prod.cache.amazonaws.com:6379",
    "ERROR 503 Service Unavailable - /api/checkout - db pool exhausted",
    "WARN DatabaseConnections approaching limit: 95/100",
    "ERROR Failed to acquire lock for order processing - timeout 5000ms",
    "ERROR Connection pool timeout after 30s - all 100 connections busy",
    "INFO Retrying database connection (attempt 3/5)...",
]


def main(region: str):
    logs = boto3.client("logs", region_name=region)
    log_group = "/app/production"
    log_stream = "api-server"

    # Create log group and stream (ignore if already exists)
    try:
        logs.create_log_group(logGroupName=log_group)
        print(f"Created log group: {log_group}")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"Log group already exists: {log_group}")

    try:
        logs.create_log_stream(logGroupName=log_group, logStreamName=log_stream)
        print(f"Created log stream: {log_stream}")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"Log stream already exists: {log_stream}")

    # Build 100 events spread over the last hour
    now = int(time.time() * 1000)
    events = []
    for _ in range(100):
        t = now - random.randint(0, 3_600_000)
        msg = random.choice(ERRORS)
        events.append({"timestamp": t, "message": msg})

    events.sort(key=lambda x: x["timestamp"])

    # Get sequence token if stream already has events
    kwargs = {
        "logGroupName": log_group,
        "logStreamName": log_stream,
        "logEvents": events,
    }
    try:
        stream_info = logs.describe_log_streams(
            logGroupName=log_group, logStreamNamePrefix=log_stream
        )
        token = stream_info["logStreams"][0].get("uploadSequenceToken")
        if token:
            kwargs["sequenceToken"] = token
    except Exception:
        pass

    logs.put_log_events(**kwargs)
    print(f"Done! 100 log entries pushed to {log_group} in {region}")
    print(f"\nTest with: aws logs filter-log-events --log-group-name {log_group} --filter-pattern ERROR --region {region}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="eu-north-1", help="AWS region")
    args = parser.parse_args()
    main(args.region)
