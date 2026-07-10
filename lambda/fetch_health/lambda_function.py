import boto3
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

DEFAULT_CLUSTER = "eks-cluster"
DEFAULT_NAMESPACE = "boutique"
REGION = "us-east-1"
PROMETHEUS_URL = "http://<YOUR_PROMETHEUS_ELB_URL>:9090"

def prometheus_query(query):
    """Run an instant PromQL query and return the result."""
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())["data"]["result"]


def check_eks_health(cluster_name, k8s_namespace):
    eks = boto3.client("eks", region_name=REGION)
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)

    # 1. Check EKS cluster status
    cluster = eks.describe_cluster(name=cluster_name)["cluster"]
    cluster_healthy = cluster["status"] == "ACTIVE"

    # 2. Check node group health
    nodegroup_names = eks.list_nodegroups(clusterName=cluster_name)["nodegroups"]
    nodegroups = []
    for ng_name in nodegroup_names:
        ng = eks.describe_nodegroup(clusterName=cluster_name, nodegroupName=ng_name)["nodegroup"]
        issues = ng.get("health", {}).get("issues", [])
        nodegroups.append({
            "name": ng_name,
            "status": ng["status"],
            "desired_nodes": ng["scalingConfig"]["desiredSize"],
            "healthy": ng["status"] == "ACTIVE" and not issues,
            "issues": [i["message"] for i in issues],
        })

    # 3. Check all deployment replica status via Prometheus
    desired_results = prometheus_query(
        f'kube_deployment_spec_replicas{{namespace="{k8s_namespace}"}}'
    )
    available_results = prometheus_query(
        f'kube_deployment_status_replicas_available{{namespace="{k8s_namespace}"}}'
    )
    available_map = {r["metric"].get("deployment"): int(float(r["value"][1])) for r in available_results}

    deployments = []
    unhealthy_deployments = []
    for r in desired_results:
        name = r["metric"].get("deployment")
        desired = int(float(r["value"][1]))
        available = available_map.get(name, 0)
        healthy = desired > 0 and available == desired
        issue = "scaled to zero" if desired == 0 else (f"{desired - available} replica(s) unavailable" if not healthy else None)
        deployments.append({"name": name, "desired": desired, "available": available, "healthy": healthy})
        if not healthy:
            unhealthy_deployments.append({"name": name, "issue": issue})

    # 4. Check pod restart counts via Prometheus
    restart_results = prometheus_query(
        f'increase(kube_pod_container_status_restarts_total{{namespace="{k8s_namespace}"}}[1h])'
    )
    crashing_pods = [
        {
            "pod": r["metric"].get("pod"),
            "container": r["metric"].get("container"),
            "restarts": round(float(r["value"][1]), 1),
        }
        for r in restart_results if float(r["value"][1]) > 0
    ]
    crashing_pods.sort(key=lambda x: x["restarts"], reverse=True)

    all_healthy = (
        cluster_healthy
        and all(n["healthy"] for n in nodegroups)
        and not unhealthy_deployments
        and not crashing_pods
    )

    return {
        "cluster": cluster_name,
        "ns": k8s_namespace,
        "cluster_status": cluster["status"],
        "nodes_healthy": all(n["healthy"] for n in nodegroups),
        "deployments": deployments,
        "unhealthy_deployments": unhealthy_deployments,
        "crashing_pods": crashing_pods,
        "all_healthy": all_healthy,
    }


def lambda_handler(event, context):
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    cluster_name = params.get("cluster_name", DEFAULT_CLUSTER)
    k8s_namespace = params.get("namespace", DEFAULT_NAMESPACE)

    try:
        eks_health = check_eks_health(cluster_name, k8s_namespace)
        result = {
            "status": "success",
            "overall_healthy": eks_health["all_healthy"],
            "details": {
                "eks": eks_health
            },
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
                    "body": json.dumps(result, separators=(',', ':'))
                }
            },
        },
    }
