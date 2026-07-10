import json
import urllib.request
import urllib.parse
from datetime import datetime

PROMETHEUS_URL = "http://<YOUR_PROMETHEUS_ELB_URL>:9090"

DEFAULT_NAMESPACE = "boutique"

METRIC_QUERIES = {
    "pod_cpu_utilization": 'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}", container!=""}}[5m])) by (pod)',
    "pod_memory_utilization": 'sum(container_memory_working_set_bytes{{namespace="{namespace}", container!=""}}) by (pod)',
    "pod_restarts": 'increase(kube_pod_container_status_restarts_total{{namespace="{namespace}"}}[1h])',
    "deployment_replicas_unavailable": 'kube_deployment_status_replicas_unavailable{{namespace="{namespace}"}}',
    "deployment_replicas_available": 'kube_deployment_status_replicas_available{{namespace="{namespace}"}}',
}


def prometheus_query(query):
    """Run an instant PromQL query."""
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())["data"]["result"]


def prometheus_range_query(query, hours_back, step="5m"):
    """Run a range PromQL query and return time-series data."""
    end = int(datetime.utcnow().timestamp())
    start = end - (hours_back * 3600)
    url = (
        f"{PROMETHEUS_URL}/api/v1/query_range"
        f"?query={urllib.parse.quote(query)}"
        f"&start={start}&end={end}&step={step}"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())["data"]["result"]


def lambda_handler(event, context):
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    metric_name = params.get("metric_name", "pod_cpu_utilization")
    namespace = params.get("namespace", DEFAULT_NAMESPACE)
    hours_back = int(params.get("hours_back", "1"))

    try:
        if metric_name in METRIC_QUERIES:
            query = METRIC_QUERIES[metric_name].format(namespace=namespace)
        else:
            # Allow raw PromQL queries
            query = metric_name.format(namespace=namespace)

        raw_results = prometheus_range_query(query, hours_back)

        if not raw_results:
            result = {"status": "no_data", "metric": metric_name, "ns": namespace}
        else:
            series = []
            for r in raw_results[:10]:  # cap at 10 series
                label = r["metric"].get("pod") or r["metric"].get("deployment") or "unknown"
                values = [float(v[1]) for v in r["values"]]
                series.append({
                    "pod": label,
                    "cur": round(values[-1], 3),
                    "avg": round(sum(values) / len(values), 3),
                    "max": round(max(values), 3),
                })

            result = {"status": "ok", "metric": metric_name, "ns": namespace, "data": series}

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
                    "body": json.dumps(result, separators=(',', ':'))
                }
            },
        },
    }
