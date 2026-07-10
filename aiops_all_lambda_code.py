"""
=============================================================================
AIOps Assistant — All Lambda Functions & OpenAPI Schemas
=============================================================================
This file contains all 3 Lambda function codes and their corresponding
OpenAPI schemas for reference. Copy each section into the respective
Lambda function in the AWS Console.
=============================================================================
"""


# =============================================================================
# LAMBDA 1: aiops-fetch-logs
# =============================================================================
# Purpose: Searches CloudWatch Logs for entries matching a filter pattern
# Trigger: Agent asks about errors, exceptions, warnings in logs
# =============================================================================

FETCH_LOGS_CODE = """
import boto3
import json
import os
from datetime import datetime, timedelta

DEFAULT_LOG_GROUP = os.environ.get("LOG_GROUP_NAME", "/app/production")
DEFAULT_REGION = os.environ.get("AWS_REGION", "eu-north-1")


def lambda_handler(event, context):
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    filter_pattern = params.get("filter_pattern", "ERROR")
    log_group_name = params.get("log_group_name", DEFAULT_LOG_GROUP)
    hours_back = int(params.get("hours_back", "1"))
    region = params.get("region", DEFAULT_REGION)

    # Create client for the specified region
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
"""


# =============================================================================
# LAMBDA 2: aiops-fetch-metrics
# =============================================================================
# Purpose: Pulls numerical metrics from CloudWatch
# Trigger: Agent asks about CPU, memory, latency, error rates, DB connections
# =============================================================================

FETCH_METRICS_CODE = """
import boto3
import json
from datetime import datetime, timedelta

cloudwatch = boto3.client("cloudwatch")


def lambda_handler(event, context):
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    metric_name = params.get("metric_name", "CPUUtilization")
    namespace = params.get("namespace", "AWS/ECS")
    hours_back = int(params.get("hours_back", "1"))
    period_minutes = int(params.get("period_minutes", "5"))
    statistic = params.get("statistic", "Average")
    dimension_name = params.get("dimension_name", "")
    dimension_value = params.get("dimension_value", "")

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    try:
        metric_params = {
            "Namespace": namespace,
            "MetricName": metric_name,
            "StartTime": start_time,
            "EndTime": end_time,
            "Period": period_minutes * 60,
            "Statistics": [statistic],
        }

        if dimension_name and dimension_value:
            metric_params["Dimensions"] = [
                {"Name": dimension_name, "Value": dimension_value}
            ]

        response = cloudwatch.get_metric_statistics(**metric_params)
        datapoints = response.get("Datapoints", [])

        if not datapoints:
            result = {
                "status": "no_data",
                "message": f"No data for {namespace}/{metric_name} in the last {hours_back} hour(s).",
                "metric": metric_name,
                "namespace": namespace,
            }
        else:
            datapoints.sort(key=lambda x: x["Timestamp"])

            formatted_points = []
            for dp in datapoints:
                formatted_points.append(
                    {
                        "timestamp": dp["Timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                        "value": round(dp.get(statistic, 0), 2),
                        "unit": dp.get("Unit", "None"),
                    }
                )

            values = [dp.get(statistic, 0) for dp in datapoints]
            summary = {
                "current": round(values[-1], 2),
                "average": round(sum(values) / len(values), 2),
                "maximum": round(max(values), 2),
                "minimum": round(min(values), 2),
            }

            result = {
                "status": "data_found",
                "metric": metric_name,
                "namespace": namespace,
                "statistic": statistic,
                "time_range_hours": hours_back,
                "total_datapoints": len(formatted_points),
                "summary": summary,
                "datapoints": formatted_points,
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
"""


# =============================================================================
# LAMBDA 3: aiops-fetch-service-health
# =============================================================================
# Purpose: Checks live status of ECS, RDS, and ALB
# Trigger: Agent asks if services are running or for a health check
# =============================================================================

FETCH_SERVICE_HEALTH_CODE = """
import boto3
import json


def lambda_handler(event, context):
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    service_type = params.get("service_type", "all")
    cluster_name = params.get("cluster_name", "")
    db_identifier = params.get("db_identifier", "")

    results = {}

    try:
        if service_type in ("ecs", "all") and cluster_name:
            ecs = boto3.client("ecs")
            services_response = ecs.list_services(
                cluster=cluster_name, maxResults=10
            )
            service_arns = services_response.get("serviceArns", [])

            if service_arns:
                details = ecs.describe_services(
                    cluster=cluster_name, services=service_arns
                )
                ecs_services = []
                for svc in details.get("services", []):
                    ecs_services.append({
                        "name": svc["serviceName"],
                        "status": svc["status"],
                        "desired_count": svc["desiredCount"],
                        "running_count": svc["runningCount"],
                        "pending_count": svc["pendingCount"],
                        "healthy": svc["runningCount"] == svc["desiredCount"],
                        "events": [e["message"] for e in svc.get("events", [])[:3]],
                    })
                results["ecs"] = {
                    "cluster": cluster_name,
                    "services": ecs_services,
                    "all_healthy": all(s["healthy"] for s in ecs_services),
                }
            else:
                results["ecs"] = {
                    "cluster": cluster_name,
                    "message": "No services found in this cluster",
                }

        if service_type in ("rds", "all"):
            rds = boto3.client("rds")
            if db_identifier:
                db_response = rds.describe_db_instances(
                    DBInstanceIdentifier=db_identifier
                )
            else:
                db_response = rds.describe_db_instances()

            rds_instances = []
            for db in db_response.get("DBInstances", []):
                rds_instances.append({
                    "identifier": db["DBInstanceIdentifier"],
                    "status": db["DBInstanceStatus"],
                    "engine": db["Engine"],
                    "instance_class": db["DBInstanceClass"],
                    "healthy": db["DBInstanceStatus"] == "available",
                })
            results["rds"] = {
                "instances": rds_instances,
                "all_healthy": all(i["healthy"] for i in rds_instances),
            }

        if service_type in ("alb", "all"):
            elbv2 = boto3.client("elbv2")
            tg_response = elbv2.describe_target_groups()
            alb_targets = []

            for tg in tg_response.get("TargetGroups", []):
                health = elbv2.describe_target_health(
                    TargetGroupArn=tg["TargetGroupArn"]
                )
                healthy_count = sum(
                    1 for t in health["TargetHealthDescriptions"]
                    if t["TargetHealth"]["State"] == "healthy"
                )
                unhealthy_count = sum(
                    1 for t in health["TargetHealthDescriptions"]
                    if t["TargetHealth"]["State"] != "healthy"
                )
                alb_targets.append({
                    "target_group": tg["TargetGroupName"],
                    "healthy_targets": healthy_count,
                    "unhealthy_targets": unhealthy_count,
                    "all_healthy": unhealthy_count == 0,
                })
            results["alb"] = {
                "target_groups": alb_targets,
                "all_healthy": all(t["all_healthy"] for t in alb_targets),
            }

        overall_healthy = all(
            results.get(svc, {}).get("all_healthy", True)
            for svc in ["ecs", "rds", "alb"]
            if svc in results
        )

        result = {
            "status": "success",
            "overall_healthy": overall_healthy,
            "services_checked": list(results.keys()),
            "details": results,
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
"""


# =============================================================================
# OPENAPI SCHEMA 1: fetch_logs
# =============================================================================
# Paste this in Bedrock Agent > Action Group > In-line API schema editor
# =============================================================================

FETCH_LOGS_SCHEMA = """
{
  "openapi": "3.0.0",
  "info": {
    "title": "CloudWatch Logs Fetcher",
    "version": "1.0.0",
    "description": "Fetches and filters application logs from AWS CloudWatch Logs"
  },
  "paths": {
    "/fetch_cloudwatch_logs": {
      "get": {
        "summary": "Fetch application logs from CloudWatch",
        "description": "Searches CloudWatch Logs for entries matching a filter pattern within a time range. Use this when the user asks about errors, exceptions, warnings, or any application-level issues visible in logs. Available log groups: /app/production (eu-north-1) for application logs, /aws/eks/eks-cluster/cluster (us-east-1) for Kubernetes EKS cluster logs.",
        "operationId": "fetch_cloudwatch_logs",
        "parameters": [
          {
            "name": "filter_pattern",
            "in": "query",
            "required": true,
            "description": "The search pattern to filter logs. Examples: ERROR, 503, timeout, connection refused, OutOfMemory, Unauthorized, Failed",
            "schema": { "type": "string" }
          },
          {
            "name": "log_group_name",
            "in": "query",
            "required": false,
            "description": "The CloudWatch Log Group name. Use /app/production for application logs. Use /aws/eks/eks-cluster/cluster for Kubernetes EKS logs.",
            "schema": { "type": "string", "default": "/app/production" }
          },
          {
            "name": "hours_back",
            "in": "query",
            "required": false,
            "description": "How many hours back to search. Use 1 for recent issues, 6 for trends, 24 for daily patterns.",
            "schema": { "type": "string", "default": "1" }
          },
          {
            "name": "region",
            "in": "query",
            "required": false,
            "description": "AWS region where the logs are stored. Use eu-north-1 for application logs (/app/production). Use us-east-1 for EKS cluster logs (/aws/eks/eks-cluster/cluster).",
            "schema": { "type": "string", "default": "eu-north-1" }
          }
        ],
        "responses": {
          "200": {
            "description": "Log entries matching the filter",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string" },
                    "total_events": { "type": "integer" },
                    "logs": {
                      "type": "array",
                      "items": {
                        "type": "object",
                        "properties": {
                          "timestamp": { "type": "string" },
                          "message": { "type": "string" }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


# =============================================================================
# OPENAPI SCHEMA 2: fetch_metrics
# =============================================================================

FETCH_METRICS_SCHEMA = """
{
  "openapi": "3.0.0",
  "info": {
    "title": "CloudWatch Metrics Fetcher",
    "version": "1.0.0",
    "description": "Fetches performance metrics from AWS CloudWatch"
  },
  "paths": {
    "/fetch_cloudwatch_metrics": {
      "get": {
        "summary": "Fetch performance metrics from CloudWatch",
        "description": "Retrieves metric data points from CloudWatch Metrics. Use when checking CPU usage, memory, error rates, latency, database connections, request counts, or any numerical performance data.",
        "operationId": "fetch_cloudwatch_metrics",
        "parameters": [
          {
            "name": "metric_name",
            "in": "query",
            "required": true,
            "description": "The CloudWatch metric name. Common metrics: CPUUtilization, MemoryUtilization, DatabaseConnections, FreeStorageSpace, ReadLatency, WriteLatency, 5XXError, 4XXError, RequestCount, TargetResponseTime, HealthyHostCount, UnHealthyHostCount",
            "schema": { "type": "string" }
          },
          {
            "name": "namespace",
            "in": "query",
            "required": true,
            "description": "The AWS service namespace. Use: AWS/ECS for containers, AWS/RDS for databases, AWS/ApplicationELB for load balancers, AWS/EC2 for instances, AWS/Lambda for functions, Custom/Application for app-level metrics",
            "schema": { "type": "string" }
          },
          {
            "name": "hours_back",
            "in": "query",
            "required": false,
            "description": "How many hours of data to retrieve.",
            "schema": { "type": "string", "default": "1" }
          },
          {
            "name": "period_minutes",
            "in": "query",
            "required": false,
            "description": "Granularity of data points in minutes.",
            "schema": { "type": "string", "default": "5" }
          },
          {
            "name": "statistic",
            "in": "query",
            "required": false,
            "description": "The statistic to retrieve.",
            "schema": { "type": "string", "default": "Average", "enum": ["Average", "Maximum", "Minimum", "Sum", "SampleCount"] }
          },
          {
            "name": "dimension_name",
            "in": "query",
            "required": false,
            "description": "Dimension name to filter by. Examples: ClusterName, ServiceName, DBInstanceIdentifier, LoadBalancer",
            "schema": { "type": "string" }
          },
          {
            "name": "dimension_value",
            "in": "query",
            "required": false,
            "description": "The value for the dimension filter.",
            "schema": { "type": "string" }
          }
        ],
        "responses": {
          "200": {
            "description": "Metric data points",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string" },
                    "summary": { "type": "object" },
                    "datapoints": { "type": "array" }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


# =============================================================================
# OPENAPI SCHEMA 3: fetch_service_health
# =============================================================================

FETCH_HEALTH_SCHEMA = """
{
  "openapi": "3.0.0",
  "info": {
    "title": "Service Health Checker",
    "version": "1.0.0",
    "description": "Checks health status of AWS services (ECS, RDS, ALB)"
  },
  "paths": {
    "/fetch_service_health": {
      "get": {
        "summary": "Check health of AWS services",
        "description": "Checks the health status of ECS services, RDS databases, and ALB target groups. Use when the user asks if services are running, if the database is healthy, or for a general system health check.",
        "operationId": "fetch_service_health",
        "parameters": [
          {
            "name": "service_type",
            "in": "query",
            "required": true,
            "description": "Which service to check. Use ecs for container services, rds for databases, alb for load balancer targets, or all for a full health check.",
            "schema": { "type": "string", "enum": ["ecs", "rds", "alb", "all"] }
          },
          {
            "name": "cluster_name",
            "in": "query",
            "required": false,
            "description": "ECS cluster name. Required when service_type is ecs or all.",
            "schema": { "type": "string" }
          },
          {
            "name": "db_identifier",
            "in": "query",
            "required": false,
            "description": "RDS instance identifier. If not provided, checks all RDS instances.",
            "schema": { "type": "string" }
          }
        ],
        "responses": {
          "200": {
            "description": "Service health status",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string" },
                    "overall_healthy": { "type": "boolean" },
                    "services_checked": { "type": "array" },
                    "details": { "type": "object" }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


# =============================================================================
# SAMPLE DATA GENERATOR
# =============================================================================
# Run this in CloudShell to create test logs in CloudWatch
# Replace REGION with your region (e.g., eu-north-1)
# =============================================================================

SAMPLE_DATA_SCRIPT = """
import boto3, time, random

logs = boto3.client('logs', region_name='YOUR_REGION_HERE')
logs.create_log_group(logGroupName='/app/production')
logs.create_log_stream(logGroupName='/app/production', logStreamName='api-server')

errors = [
    'ERROR PostgreSQL connection pool exhausted - max_connections=100, active=100, waiting=47',
    'ERROR 503 Service Unavailable - Cannot acquire database connection from pool',
    'ERROR Request timeout after 30000ms - POST /api/orders - upstream connection refused',
    'ERROR Circuit breaker OPEN for payment-service - failure rate 78%',
    'WARN High latency detected: p99=4523ms p95=2100ms for /api/search',
    'WARN Slow query: SELECT * FROM orders WHERE status=pending - 3400ms',
    'ERROR OOM Kill in container task-id=abc123 - memory limit 512MB exceeded',
    'INFO Health check passed - all dependencies OK',
    'INFO Request completed - GET /api/health - 200 OK - 12ms',
    'ERROR Connection refused to Redis at redis-prod.cache.amazonaws.com:6379',
]

now = int(time.time() * 1000)
events = []
for i in range(100):
    t = now - random.randint(0, 3600000)
    msg = random.choice(errors)
    events.append({'timestamp': t, 'message': msg})

events.sort(key=lambda x: x['timestamp'])
logs.put_log_events(logGroupName='/app/production', logStreamName='api-server', logEvents=events)
print('Done! 100 log entries pushed to /app/production')
"""


# =============================================================================
# STREAMLIT APP ENVIRONMENT VARIABLES (.env file)
# =============================================================================

ENV_TEMPLATE = """
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=eu-north-1
BEDROCK_AGENT_ID=
BEDROCK_AGENT_ALIAS_ID=
"""
