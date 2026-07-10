import boto3
import json
import os
from datetime import datetime, timedelta

DEFAULT_LOG_GROUP = os.environ.get("LOG_GROUP_NAME", "/eks/boutique/pods")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-1")


def lambda_handler(event, context):
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    filter_pattern = params.get("filter_pattern", "ERROR")
    log_group_name = params.get("log_group_name", DEFAULT_LOG_GROUP)
    hours_back = int(params.get("hours_back", "1"))
    region = params.get("region", DEFAULT_REGION)

    cloudwatch_logs = boto3.client("logs", region_name=region)

    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000)

    try:
        response = cloudwatch_logs.filter_log_events(
            logGroupName=log_group_name,
            startTime=start_time,
            endTime=end_time,
            filterPattern=filter_pattern,
            limit=50,
        )

        events = response.get("events", [])

        if not events:
            result = {
                "status": "no_logs_found",
                "message": f"No logs matching '{filter_pattern}' in {log_group_name} ({region}) for the last {hours_back} hour(s).",
                "log_group": log_group_name,
                "filter": filter_pattern,
                "time_range_hours": hours_back,
                "region": region,
            }
        else:
            formatted_logs = []
            for e in events:
                timestamp = datetime.fromtimestamp(e["timestamp"] / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                formatted_logs.append(
                    {"timestamp": timestamp, "message": e["message"].strip()}
                )

            result = {
                "status": "logs_found",
                "log_group": log_group_name,
                "filter": filter_pattern,
                "time_range_hours": hours_back,
                "region": region,
                "total_events": len(formatted_logs),
                "logs": formatted_logs,
            }

    except cloudwatch_logs.exceptions.ResourceNotFoundException:
        result = {
            "status": "error",
            "message": f"Log group '{log_group_name}' does not exist in {region}.",
        }
    except Exception as e:
        result = {"status": "error", "message": str(e)}

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(result, indent=2)
                }
            },
        },
    }
