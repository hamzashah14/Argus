"""
Write test log data for one instance under the monitored prefix, including a
deliberate 10-minute silent gap, so you can check Kira end to end: that
discovery finds the group and that the gap shows up in silent_gaps.

Usage:
    python3 scripts/generate_sample_data.py --region <MONITOR_REGION> --instance-id <instance-id>
Then ask Kira: "What happened on <instance-id> around <the gap start it prints> UTC?"
"""

import argparse
import random
import time

import boto3

NORMAL = [
    "INFO Request completed - GET /api/health - 200 OK - 12ms",
    "INFO Request completed - GET /api/clubs - 200 OK - 48ms",
    "WARN Slow query: SELECT * FROM orders WHERE status=pending - 3400ms",
    "INFO Scheduler tick - 0 jobs due",
]
BEFORE_GAP = "INFO Report job: generating PDF for ClubId=231"
AFTER_GAP = "ERROR TimeoutException: render did not complete within 180000 ms"


def main(region, instance_id, prefix):
    logs = boto3.client("logs", region_name=region)
    group = f"{prefix.rstrip('/')}/{instance_id}/sample-app"
    for create, kwargs in (
        (logs.create_log_group, {"logGroupName": group}),
        (logs.create_log_stream, {"logGroupName": group, "logStreamName": instance_id}),
    ):
        try:
            create(**kwargs)
        except logs.exceptions.ResourceAlreadyExistsException:
            pass
    logs.put_retention_policy(logGroupName=group, retentionInDays=1)

    now_ms = int(time.time() * 1000)
    gap_start, gap_end = now_ms - 30 * 60_000, now_ms - 20 * 60_000
    events = [
        {"timestamp": t, "message": random.choice(NORMAL)}
        for t in range(now_ms - 50 * 60_000, now_ms - 60_000, 20_000)
        if not gap_start <= t < gap_end
    ]
    events += [
        {"timestamp": gap_start - 1_000, "message": BEFORE_GAP},
        {"timestamp": gap_end, "message": AFTER_GAP},
    ]
    events.sort(key=lambda e: e["timestamp"])
    logs.put_log_events(logGroupName=group, logStreamName=instance_id, logEvents=events)

    print(f"Wrote {len(events)} lines to {group} ({region}), with no lines between")
    print(
        f"  {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(gap_start / 1000))} and "
        f"{time.strftime('%H:%M:%S', time.gmtime(gap_end / 1000))} UTC. The group expires after 1 day."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True, help="MONITOR_REGION")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--prefix", default="/aiops", help="LOG_GROUP_PREFIX")
    args = parser.parse_args()
    main(args.region, args.instance_id, args.prefix)
