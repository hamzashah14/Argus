"""Independent customer observers: health/freshness, synthetic sender and recipient receipt."""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

from kira import probes
from kira.incident import normalize_sns
from kira.ledger import Ledger, conditional
from kira.pipeline import clients, env, partial_batch
from kira.telemetry import emit
from kira.time import iso_utc


def settings():
    value = json.loads(env("OBS_SETTINGS"))
    # Deployment render validates the full inventory. Never accept request overrides.
    if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
        raise ValueError("Observer settings unavailable")
    return value


def store():
    return Ledger(env("INCIDENT_TABLE"), region_name=env("MONITOR_REGION"))


def slot_at(now, config):
    period = config["canary_interval_minutes"] * 60
    return int(now) // period * period


def canary_payload(slot, config):
    return {
        "source": "kira.canary",
        "account": env("EXPECTED_ACCOUNT_ID"),
        "region": env("MONITOR_REGION"),
        "instance_id": config["services"][0]["instance_id"],
        "slot": slot,
        "time": iso_utc(datetime.fromtimestamp(slot, timezone.utc)),
    }


def canary_sender(event=None, context=None):
    config = settings()
    if not config["enabled"] or os.getenv("MAINTENANCE_MODE") == "true":
        return {"status": "DISABLED"}
    ledger, now = store(), int(time.time())
    slot = slot_at(now, config)
    payload = canary_payload(slot, config)
    envelope = json.dumps(
        {"Type": "Notification", "TopicArn": env("CANARY_TOPIC_ARN"), "Message": json.dumps(payload)}
    )
    normalized = normalize_sns(
        envelope,
        env("ALARMS_TOPIC_ARN"),
        env("EXPECTED_ACCOUNT_ID"),
        env("MONITOR_REGION"),
        {s["instance_id"] for s in config["services"]},
        env("ALARM_NAME_PREFIX"),
        canary_topic=env("CANARY_TOPIC_ARN"),
    )
    pk = f"CANARY#{slot}"
    expected = {
        "PK": pk,
        "SK": "META",
        "incident_id": normalized["incident_id"],
        "created_at": now,
        "due_epoch": now + config["receipt_deadline_seconds"],
        "ttl": now + 30 * 86400,
    }
    try:
        ledger.table.put_item(Item=expected, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as exc:
        if not conditional(exc):
            raise
    current = ledger.get(pk)
    if not current or current["incident_id"] != expected["incident_id"]:
        raise RuntimeError("Canary expectation binding missing")
    if current.get("published_message_id"):
        return {"status": "ALREADY_PUBLISHED"}
    response = clients("sns").publish(TopicArn=env("CANARY_TOPIC_ARN"), Message=json.dumps(payload))
    if not response.get("MessageId"):
        raise RuntimeError("Canary publication not acknowledged")
    ledger.table.update_item(
        Key={"PK": pk, "SK": "META"},
        UpdateExpression="SET published_message_id=:message",
        ConditionExpression="incident_id=:incident AND attribute_not_exists(published_message_id)",
        ExpressionAttributeValues={":message": response["MessageId"], ":incident": current["incident_id"]},
    )
    emit("canary", "PUBLISHED", incident_id=current["incident_id"], metrics={"Heartbeat": 1})
    return {"status": "PUBLISHED"}


def recipient(event, context=None):
    ledger = store()

    def one(record):
        if len(record["body"].encode()) > 128 * 1024:
            raise ValueError("Recipient envelope too large")
        message = json.loads(record["body"])
        if message.get("TopicArn") != env("REPORTS_TOPIC_ARN") or message.get("Type") != "Notification":
            raise ValueError("Unexpected recipient source")
        attrs = message.get("MessageAttributes", {})
        iid = attrs.get("kira_incident", {}).get("Value", "")
        if attrs.get("kira_canary", {}).get("Value") != "true" or not re.fullmatch(r"[0-9a-f]{32}", iid):
            raise ValueError("Receipt must identify a declared canary")
        incident = ledger.get(f"INCIDENT#{iid}")
        if not incident or "canary_slot" not in incident or incident.get("ttl", 0) <= time.time():
            raise ValueError("Canary incident missing or expired")
        pk = f"CANARY#{incident['canary_slot']}"
        now = int(time.time())
        ledger.table.update_item(
            Key={"PK": pk, "SK": "META"},
            UpdateExpression="SET recipient_received_at=if_not_exists(recipient_received_at,:now), recipient_message_id=if_not_exists(recipient_message_id,:message)",
            ConditionExpression="incident_id=:incident AND ttl>:now",
            ExpressionAttributeValues={":now": now, ":incident": iid, ":message": message["MessageId"]},
        )
        emit("receipt", "SQS_RECEIVED", incident_id=iid, metrics={"RecipientReceived": 1})

    return partial_batch(event, one, "receipt")


def check_freshness(service, config, cw, logs, now):
    with open("config/metric-catalog.json") as handle:
        catalog = json.load(handle)
    descriptor = next(d for d in catalog if d["id"] == service["collector_metric_id"])
    start = now - timedelta(seconds=service["freshness_seconds"])
    result = cw.get_metric_statistics(
        Namespace=descriptor["namespace"],
        MetricName=descriptor["metric_name"],
        Dimensions=[{"Name": k, "Value": v} for k, v in sorted(descriptor["dimensions"].items())],
        StartTime=start,
        EndTime=now,
        Period=60,
        Statistics=[descriptor["statistic"]],
    )
    metric_fresh = probes.fresh(
        [d["Timestamp"] for d in result["Datapoints"]], now.timestamp(), service["freshness_seconds"]
    )
    group = f"{env('LOG_GROUP_PREFIX')}/{service['instance_id']}/{service['heartbeat_log_group']}"
    events = logs.get_log_events(
        logGroupName=group,
        logStreamName=service["instance_id"],
        startTime=int(start.timestamp() * 1000),
        endTime=int(now.timestamp() * 1000),
        limit=10,
        startFromHead=False,
    )["events"]
    # Dedicated heartbeat writer emits a source timestamp. Arbitrary business logs never count.
    beats = []
    for event in events:
        try:
            if len(event["message"].encode()) > 1024:
                continue
            beat = json.loads(event["message"])
            if (
                set(beat) == {"type", "instance_id", "timestamp"}
                and beat["type"] == "kira.collector-heartbeat"
                and beat["instance_id"] == service["instance_id"]
            ):
                timestamp = datetime.fromisoformat(beat["timestamp"].replace("Z", "+00:00"))
                if (
                    timestamp.tzinfo is not None
                    and abs(timestamp.timestamp() - event["timestamp"] / 1000) <= 60
                ):
                    beats.append(timestamp)
        except (ValueError, TypeError, KeyError):
            continue
    return metric_fresh and probes.fresh(beats, now.timestamp(), service["freshness_seconds"])


def confirmed_recipient(sns, topic=None, email=None):
    entries = [
        s
        for page in sns.get_paginator("list_subscriptions_by_topic").paginate(
            TopicArn=topic or env("REPORTS_TOPIC_ARN")
        )
        for s in page["Subscriptions"]
        if s["Protocol"] == "email" and s["Endpoint"] == (email or env("PRIMARY_EMAIL"))
    ]
    if len(entries) != 1 or not entries[0]["SubscriptionArn"].startswith("arn:"):
        return False
    attrs = sns.get_subscription_attributes(SubscriptionArn=entries[0]["SubscriptionArn"])["Attributes"]
    return not json.loads(attrs.get("FilterPolicy", "{}"))


def recipient_fingerprint(topic, email):
    return hashlib.sha256((topic + "\n" + email).encode()).hexdigest()


def verify_canary(ledger, config, now):
    current_slot = slot_at(now, config)
    period = config["canary_interval_minutes"] * 60
    problem, received, ack_times = [], False, []
    fingerprint = recipient_fingerprint(env("REPORTS_TOPIC_ARN"), env("PRIMARY_EMAIL"))
    # Include last period to catch a lost receipt across the schedule boundary.
    for slot in (current_slot, current_slot - period):
        row = ledger.get(f"CANARY#{slot}")
        if not row:
            if slot == current_slot and now - slot > config["receipt_deadline_seconds"]:
                problem.append("CANARY_MISSING")
            continue
        incident = ledger.get(f"INCIDENT#{row['incident_id']}")
        notification = ledger.get(f"INCIDENT#{row['incident_id']}", "NOTIFICATION#INITIAL")
        valid = bool(
            incident
            and notification
            and notification.get("status") == "PUBLISHER_ACCEPTED"
            and row.get("recipient_received_at")
            and row.get("recipient_message_id") == notification.get("publisher_message_id")
        )
        received = received or valid
        if not valid and now >= row["due_epoch"]:
            problem.append("CANARY_RECEIPT_MISSED")
        if row.get("recipient_fingerprint") == fingerprint and 0 < row.get("email_received_at", 0) <= now:
            ack_times.append(int(row["email_received_at"]))
    email = ledger.get("OBS#EMAIL")
    if (
        email
        and email.get("ttl", 0) > now
        and 0 < email.get("email_received_at", 0) <= now
        and email.get("recipient_fingerprint") == fingerprint
    ):
        ack_times.append(int(email["email_received_at"]))
    age = now - max(ack_times) if ack_times else config["email_receipt_max_age_hours"] * 3600 + 1
    if age > config["email_receipt_max_age_hours"] * 3600:
        problem.append("EMAIL_RECEIPT_UNVERIFIED")
    return sorted(set(problem)), received, max(0, age)


def observer(event=None, context=None):
    config = settings()
    if not config["enabled"]:
        return {"status": "DISABLED"}
    now = datetime.now(timezone.utc)
    deadline = time.monotonic() + min(
        45, context.get_remaining_time_in_millis() / 1000 - 10 if context else 45
    )
    cw, logs, sns, ledger = clients("cloudwatch"), clients("logs"), clients("sns"), store()
    metrics, failures = [], []
    if os.getenv("MAINTENANCE_MODE") != "true":
        for service in config["services"]:
            for route in service["routes"]:
                if time.monotonic() + route["timeout_seconds"] + 1 >= deadline:
                    raise RuntimeError(
                        "Observer deadline exhausted; external heartbeat alarm must detect this"
                    )
                result = probes.bounded_check(route)
                metrics.append(
                    {
                        "MetricName": "Availability",
                        "Value": int(result["healthy"]),
                        "Unit": "Count",
                        "Timestamp": now,
                        "Dimensions": [
                            {"Name": "Service", "Value": service["id"]},
                            {"Name": "Route", "Value": route["id"]},
                        ],
                    }
                )
            if time.monotonic() + 20 >= deadline:
                raise RuntimeError("Observer deadline exhausted")
            try:
                healthy = check_freshness(service, config, cw, logs, now)
            except Exception:
                healthy = False
                failures.append("TELEMETRY_READ_FAILED")
            metrics.append(
                {
                    "MetricName": "TelemetryFresh",
                    "Value": int(healthy),
                    "Unit": "Count",
                    "Timestamp": now,
                    "Dimensions": [
                        {"Name": "Service", "Value": service["id"]},
                        {"Name": "Route", "Value": "telemetry"},
                    ],
                }
            )
        cw.put_metric_data(Namespace=env("HEALTH_NAMESPACE"), MetricData=metrics)
        problem, received, email_age = verify_canary(ledger, config, int(now.timestamp()))
        failures.extend(problem)
        if not confirmed_recipient(sns):
            failures.append("PRIMARY_SUBSCRIPTION_MISSING")
        if not confirmed_recipient(sns, env("FALLBACK_TOPIC_ARN"), env("FALLBACK_EMAIL")):
            failures.append("FALLBACK_SUBSCRIPTION_MISSING")
    else:
        received, email_age = False, 0
    oldest = 0
    pending, cursor = ledger.pending(iso_utc(now), limit=100)
    if pending:
        oldest = max(
            0,
            int(now.timestamp())
            - int(datetime.fromisoformat(pending[0]["due_at"].replace("Z", "+00:00")).timestamp()),
        )
        if oldest > 300 and os.getenv("MAINTENANCE_MODE") != "true":
            failures.append("OUTBOX_OVERDUE")
    for failure in sorted(set(failures)):
        emit("observer", failure)
    emit(
        "observer",
        "ATTENTION" if failures else "CHECKED",
        metrics={
            "Heartbeat": 1,
            "Failure": len(failures),
            "OldestOutboxSeconds": oldest,
            "EmailReceiptAgeSeconds": email_age,
        },
    )
    return {
        "status": "ATTENTION" if failures else "CHECKED",
        "instrumented_delivery": received,
        "email_delivery": "SUPPRESSED"
        if os.getenv("MAINTENANCE_MODE") == "true"
        else "OPERATOR_ATTESTED"
        if email_age <= config["email_receipt_max_age_hours"] * 3600
        else "UNVERIFIED",
    }
