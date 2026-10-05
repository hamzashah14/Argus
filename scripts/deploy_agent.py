"""Create or update the Bedrock Agent and its action groups. Run via ./deploy.sh."""

import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = os.environ["BEDROCK_REGION"]
MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
AGENT_NAME = os.environ["AGENT_NAME"]
ACCOUNT_ID = os.environ["ACCOUNT_ID"]
AGENT_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/{os.environ['AGENT_ROLE_NAME']}"
ACTION_GROUPS = [
    {
        "name": "fetch_logs",
        "function": os.environ["FETCH_LOGS_FUNC"],
        "schema": "fetch_logs.json",
        "description": "Discover an EC2 instance's log groups, or search one around an incident time",
    },
    {
        "name": "fetch_metrics",
        "function": os.environ["FETCH_METRICS_FUNC"],
        "schema": "fetch_metrics.json",
        "description": "Fetch one CloudWatch EC2 or CWAgent metric for one EC2 instance",
    },
]
OUR_FUNCTION_MARKER = ":function:aiops-"
BUSY = {"CREATING", "UPDATING", "PREPARING", "VERSIONING"}

bedrock = boto3.client("bedrock-agent", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)


def fail(message):
    print(f"  ✗ {message}", file=sys.stderr)
    sys.exit(1)


def wait_until_settled(agent_id, want=None, timeout_s=600):
    deadline = time.time() + timeout_s
    while True:
        agent = bedrock.get_agent(agentId=agent_id)["agent"]
        status = agent["agentStatus"]
        if status == "FAILED":
            fail(f"Agent is FAILED: {agent.get('failureReasons')}")
        if status not in BUSY and (want is None or status == want):
            return status
        if time.time() > deadline:
            fail(f"Agent still {status} after {timeout_s}s")
        time.sleep(5)


def find_agent():
    for page in bedrock.get_paginator("list_agents").paginate():
        for summary in page["agentSummaries"]:
            if summary["agentName"] == AGENT_NAME:
                return summary["agentId"]
    return None


def upsert_agent(instruction):
    fields = {
        "agentName": AGENT_NAME,
        "agentResourceRoleArn": AGENT_ROLE_ARN,
        "foundationModel": MODEL_ID,
        "instruction": instruction,
        "idleSessionTTLInSeconds": 1800,
        "description": "Kira — AIOps incident investigation for EC2",
    }
    agent_id = find_agent()
    if agent_id:
        wait_until_settled(agent_id)
        bedrock.update_agent(agentId=agent_id, **fields)
        print(f"  ✓ Updated agent {agent_id} (instruction, model, role)")
    else:
        agent_id = bedrock.create_agent(**fields)["agent"]["agentId"]
        print(f"  ✓ Created agent {agent_id}")
    wait_until_settled(agent_id)
    return agent_id


def existing_action_groups(agent_id):
    groups = {}
    for page in bedrock.get_paginator("list_agent_action_groups").paginate(
        agentId=agent_id, agentVersion="DRAFT"
    ):
        for summary in page["actionGroupSummaries"]:
            groups[summary["actionGroupName"]] = summary["actionGroupId"]
    return groups


def sync_action_groups(agent_id):
    existing = existing_action_groups(agent_id)
    wanted = {g["name"] for g in ACTION_GROUPS}

    for group in ACTION_GROUPS:
        with open(os.path.join(ROOT, "schemas", group["schema"])) as f:
            schema = f.read()
        fields = {
            "agentId": agent_id,
            "agentVersion": "DRAFT",
            "actionGroupName": group["name"],
            "description": group["description"],
            "actionGroupExecutor": {
                "lambda": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{group['function']}"
            },
            "apiSchema": {"payload": schema},
            "actionGroupState": "ENABLED",
        }
        if group["name"] in existing:
            bedrock.update_agent_action_group(actionGroupId=existing[group["name"]], **fields)
            print(f"  ✓ Updated action group {group['name']} (schema + Lambda)")
        else:
            bedrock.create_agent_action_group(**fields)
            print(f"  ✓ Created action group {group['name']}")

    # Remove action groups an older version of this project created (e.g. the
    # EKS-era fetch_service_health), but never ones pointing elsewhere.
    for name, group_id in existing.items():
        if name in wanted:
            continue
        group = bedrock.get_agent_action_group(
            agentId=agent_id, agentVersion="DRAFT", actionGroupId=group_id
        )["agentActionGroup"]
        executor = group.get("actionGroupExecutor", {}).get("lambda", "")
        if OUR_FUNCTION_MARKER not in executor:
            print(f"  - Left action group {name} alone (not created by this project)")
            continue
        if group.get("actionGroupState") == "ENABLED":
            bedrock.update_agent_action_group(
                agentId=agent_id,
                agentVersion="DRAFT",
                actionGroupId=group_id,
                actionGroupName=name,
                actionGroupExecutor=group["actionGroupExecutor"],
                apiSchema=group["apiSchema"],
                actionGroupState="DISABLED",
            )
        bedrock.delete_agent_action_group(
            agentId=agent_id, agentVersion="DRAFT", actionGroupId=group_id, skipResourceInUseCheck=True
        )
        print(f"  ✓ Removed stale action group {name} (was calling {executor.split(':')[-1]})")


def grant_lambda_permissions(agent_id):
    agent_arn = f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent/{agent_id}"
    for group in ACTION_GROUPS:
        fn = group["function"]
        # AllowBedrockInvoke was the old, unconditioned grant: any Bedrock agent
        # in any account could have invoked this Lambda.
        for statement_id in ("AllowBedrockInvoke", "AllowBedrockAgentInvoke"):
            try:
                lambda_client.remove_permission(FunctionName=fn, StatementId=statement_id)
            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
        lambda_client.add_permission(
            FunctionName=fn,
            StatementId="AllowBedrockAgentInvoke",
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
            SourceArn=agent_arn,
            SourceAccount=ACCOUNT_ID,
        )
        print(f"  ✓ {fn}: invocable only by agent {agent_id}")


def main():
    print("[0/4] Pre-flight")
    for group in ACTION_GROUPS:
        try:
            lambda_client.get_function(FunctionName=group["function"])
        except ClientError:
            fail(f"Lambda {group['function']} not found in {REGION} — run ./setup-lambdas.sh first.")
    print("  ✓ Tool Lambdas exist")
    with open(os.path.join(ROOT, "agent-instruction.txt")) as f:
        instruction = f.read().strip()

    print("[1/4] Agent")
    agent_id = upsert_agent(instruction)
    print("[2/4] Action groups")
    sync_action_groups(agent_id)
    print("[3/4] Lambda permissions")
    grant_lambda_permissions(agent_id)
    print("[4/4] Prepare (can take a minute)")
    bedrock.prepare_agent(agentId=agent_id)
    wait_until_settled(agent_id, want="PREPARED")
    print("  ✓ PREPARED")

    try:
        lambda_client.get_function(FunctionName="aiops-fetch-health")
        stale_fn = True
    except ClientError:
        stale_fn = False

    print(f"""
Done. Agent ID: {agent_id}

Manual Bedrock steps (console: Bedrock → Agents → {AGENT_NAME}):
  1. Test the DRAFT in the console's test pane.
  2. Aliases → Create alias (e.g. "live"). This snapshots the prepared DRAFT
     as a numbered version. Put its alias ID in config.env as
     BEDROCK_AGENT_ALIAS_ID, and in the chat UI's environment.
  3. After every later ./deploy.sh: edit that alias → "Create a new version
     and associate it to this alias". Until you do, production keeps running
     the previous version — the alias does not follow the DRAFT.
  4. Set BEDROCK_AGENT_ID={agent_id} in config.env and the chat UI environment.""")
    if stale_fn:
        print(f"""  5. Delete the old EKS-era Lambda nothing uses any more:
       aws lambda delete-function --function-name aiops-fetch-health --region {REGION}""")
    print()


if __name__ == "__main__":
    main()
