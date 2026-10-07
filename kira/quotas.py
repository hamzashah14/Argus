"""Atomic shared admission; full request allowance charged before work, never refunded."""

import os
import time
import uuid

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.config import Config
from botocore.exceptions import ClientError

from kira import work_policy
from kira.runtime import RuntimeStop


def pack(value):
    return {k: TypeSerializer().serialize(v) for k, v in value.items()}


class Quotas:
    def __init__(self, table, clock=time.time, client=None):
        self.table, self.clock = table, clock
        self.client = client or boto3.client(
            "dynamodb",
            region_name=os.environ["MONITOR_REGION"],
            config=Config(connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 1}),
        )

    def admit(self, actor, purpose):
        policy = work_policy.configured()
        now = int(self.clock())
        hour = now // 3600
        token = uuid.uuid4().hex
        amount = policy["chat_limits"]["tokens_reserved"] if purpose == "chat" else 0
        if purpose not in {"login", "chat"}:
            raise ValueError("Unknown admission purpose")
        transaction = []
        for who, suffix in [(actor, "user"), ("global", "global")]:
            values = {":one": 1, ":cap": policy[f"{purpose}_{suffix}"] - 1, ":ttl": (hour + 2) * 3600}
            condition = "(attribute_not_exists(#n) OR #n <= :cap)"
            names = {"#n": "requests"}
            expression = "SET ttl=:ttl ADD #n :one"
            if purpose == "chat":
                names["#t"] = "tokens"
                values.update({":tokens": amount, ":token_cap": policy[f"tokens_{suffix}"] - amount})
                condition += " AND (attribute_not_exists(#t) OR #t <= :token_cap)"
                expression += ", #t :tokens"
            transaction.append(
                {
                    "Update": {
                        "TableName": self.table.name,
                        "Key": pack({"PK": f"QUOTA#{purpose}#{who}#{hour}", "SK": "META"}),
                        "UpdateExpression": expression,
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": names,
                        "ExpressionAttributeValues": pack(values),
                    }
                }
            )
        slots = (0, 1) if purpose == "chat" else (None,)
        for slot in slots:
            writes = list(transaction)
            if slot is not None:
                for who in (actor, f"global#{slot}"):
                    writes.append(
                        {
                            "Put": {
                                "TableName": self.table.name,
                                "Item": pack(
                                    {
                                        "PK": f"SLOT#{who}",
                                        "SK": "META",
                                        "owner": token,
                                        "until": now + 240,
                                        "ttl": now + 3600,
                                    }
                                ),
                                "ConditionExpression": "attribute_not_exists(PK) OR #until <= :now",
                                "ExpressionAttributeNames": {"#until": "until"},
                                "ExpressionAttributeValues": pack({":now": now}),
                            }
                        }
                    )
            try:
                self.client.transact_write_items(
                    TransactItems=writes, ClientRequestToken=token + (str(slot) if slot is not None else "l")
                )
                return {"owner": token, "actor": actor, "slot": slot}
            except ClientError as exc:
                # Only a confirmed conditional transaction rejection is safe to
                # try another slot. Timeout/unknown cancellation stays charged.
                reasons = exc.response.get("CancellationReasons", [])
                if (
                    exc.response.get("Error", {}).get("Code") != "TransactionCanceledException"
                    or not reasons
                    or not any(r.get("Code") == "ConditionalCheckFailed" for r in reasons)
                    or any(r.get("Code") not in {"None", "ConditionalCheckFailed"} for r in reasons)
                ):
                    raise RuntimeStop("ADMISSION_UNAVAILABLE") from None
        raise RuntimeStop("USER_OR_SHARED_ALLOWANCE_EXHAUSTED")

    def release(self, lease):
        if lease["slot"] is None:
            return
        for who in (lease["actor"], f"global#{lease['slot']}"):
            try:
                self.table.delete_item(
                    Key={"PK": f"SLOT#{who}", "SK": "META"},
                    ConditionExpression="#o=:owner",
                    ExpressionAttributeNames={"#o": "owner"},
                    ExpressionAttributeValues={":owner": lease["owner"]},
                )
            except Exception:
                pass  # TTL/explicit lease time permit recovery; no budget refund.
