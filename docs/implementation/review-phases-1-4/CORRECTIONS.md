# Phases 1–4 corrective implementation — 6 October 2026

The user authorized continuation after the review. Batches A–C now have repository
fixes and positive regression tests. R01–R08 are **VERIFYING**, not production
qualified; hosted CI and actual G2/G3/G4 remain pending. Phase 5 has not started.
Floci batch D remains proposed. No cloud resources, inference or notifications
were created by this work. The customer-owned open-source operating model is unchanged.

## Changes and acceptance evidence

| Finding | Implemented behavior | Local acceptance | Remaining qualification |
|---|---|---|---|
| R01 | Shared durable verifier checks sealed template, each of six stack-owned role bindings and actual role trust/grants/attachments/path/boundary | Every function rejects binding or policy drift; role trust, removed/extra grants, attached/inline policy and restrictions rejected | Actual customer IAM, KMS and service calls |
| R02 | Four independent minute-scheduled scan classes, persisted CAS cursors and checkpoint before row work | Repeated slow poisoned prefixes advance to later intents across invocations; overlapping stale scans stop; notification recovery unaffected by worker scan failure | Concurrent DynamoDB/GSI behavior, sustained arrivals, real latency/load and terminal accounting |
| R03 | Paused inventory explicitly skips only observer Health descriptors; enabled coverage remains strict; explicit verified `seed-health` before promotion | Paused absence passes, enabled absence fails, enabled presence passes; bootstrap invokes each reviewed service on the qualified observer | Fresh-account stage rehearsal and real telemetry publication |
| R04 | SDK invocation/stream reader runs in a killable child, absolute caller deadline, incremental byte/line bounds; no retry/failover | Real loopback SDK silence, trickle, oversized unterminated body, disconnect and short valid result on an open connection; child reaped | Linux Lambda/ARM64 host behavior, upstream cancellation and billing ambiguity |
| R05 | Per-service health schedules and separate delivery invocation; publish availability before freshness; guard SDK/ledger reads and bounded recipient discovery | Independent slow-service progress, prior publications survive freshness failures, incomplete tail checks return explicit attention | Maximum inventory cadence, quota/throttle/fault/maintenance/load tests |
| R06 | Remote model/tool widgets use Bedrock region; qualified AgentCore native health and log widgets; retained qualified and DEFAULT log groups before endpoint creation; live retention verifier | Same/split-region renders, exact native endpoint dimensions/log names, absent/drifted retention rejected | Actual AgentCore log and EMF ingestion; native metrics/dimensions after invocation |
| R07 | Indexed notification leases become PENDING with atomic retry intent or terminal AMBIGUOUS after third expiry; reviewed notification-only replay with audit and CAS; serial batch time admission | Attempt 1/2 retry and 3 ambiguity, stale fencing, replay refusal on drift/success/expiry/allowance; second unsafe record retained | Process kills/send–ack faults with actual SNS/DynamoDB, DLQ and audited customer operator |
| R08 | Trusted topic/incident/stable initial notification correlation and bounded receipt/publication ID sets | Delivered first publication with lost ack and later accepted retry remains delivered; forged notification scope denied; no inbox inference | Reordered/duplicate deliveries through actual SNS/SQS and mailbox/recipient rotation |

**R01 scope correction:** the original review overstated this as a promotion
omission. The full `owned_ops.verify_candidate` already checked pipeline grants
after `verify_runtime`. The diagnostic exercised the standalone verifier. The
fix moves IAM checks into that shared verifier and adds exact stack-role binding,
path/boundary and deployed-template checks. It strengthens the standalone command
and removes duplicate promotion checks; it does not imply prior promotion ignored
all IAM. Historical observations and source checksums are preserved.

Local checkpoint `99695cf`: **410 tests (61 new), 64 templates and 13
deterministic ZIP pairs/import checks PASS**. Both 6/8 and 9/11-stage release
layouts reran from clean source; synthetic cloud commands remained refused.
This records local implementation, not a live gate.

Current tests live in `tests/test_review_corrections.py` plus the updated existing
runtime, incident and observation suites. SDK/account calls are denied in the
parent test process. Socket regressions use a local HTTP server, dummy credentials
and an explicit loopback SDK endpoint in a child. They are not AWS/AgentCore service
tests. Sanitized commands, results, artifact/source hashes and limits are in
[corrective validation](../evidence/review-phases-1-4/corrections-validation.json).

## Bootstrap and deployment changes

Use a **new immutable release ID** and rebuild tools, pipeline, optional host and
observers from reviewed source. Do not update sealed candidate stacks or combine
old ZIPs with new environment/schedules. Follow the normal inspect/execute/seal
workflow with actual private customer inputs and budget. No infrastructure exists
in the user's account yet; the following is a procedure, not an executed deployment.

1. Establish customer inventory, IAM, quota, endpoints/readiness and collector
   metrics/logs/heartbeat. Resolve the previous Lambda concurrency quota gap.
2. Review retained foundation diffs, including durable capture and observation
   dead-letter queue policies. The latter must authorize each exact health rule
   as well as the delivery/canary rules.
3. Build/deploy/seal owned tools and, if selected, the AgentCore runtime. Collect
   the runtime ID/version before rendering its endpoint. That endpoint stage
   pre-creates both standard application log groups with spec retention. Do not
   invoke an endpoint before its groups exist; if a group already exists, use a
   separately reviewed ownership/import decision, not deletion to bypass a conflict.
4. Create/seal durable and observation runtimes; bind their qualified versions.
   Verify shared runtime IAM/code/configuration and observer runtime.
5. For **enabled** observations, run the explicit bootstrap operation below before
   strict coverage/canary/promotion. It invokes only health for each declared
   service; it does not run a model, send notifications or activate schedules.
   The observer may make the approved external HTTPS probes and CloudWatch writes.
   Allow metric discovery time, then rerun strict coverage. Missing Health metrics
   remain a blocker. Intentionally paused specs record Health as disabled while
   retaining strict collector/application telemetry checks.
6. Qualify the normal owned model/tool canary and promotion/retirement gates.
   Drain/recover old release incidents before cutover as required by Phase 3.
7. Apply routing and observations; verify all four recovery targets, each health
   target, delivery/canary schedules, mappings, alarms, recipients and dashboard.
   Complete initial notification canary, actual primary/fallback emails and inbox
   attestation, then the pending fault/load/rollback gates. Bootstrap is not G4.

```bash
.venv/bin/python -m infra.durable_ops seed-health --bundle "$BUNDLE" --review-hash "$REVIEW_HASH" --output .local/customer/health-bootstrap.json
```

The command rejects reference specs before clients. It requires reviewed clean
source and sealed observer verification; invocation uses no SDK retries and a
185-second read timeout for the 180-second observer. Its `SEEDED` receipt records
services, not healthy production qualification. A non-CHECKED/function-error
result stops bootstrap. Maintenance-mode bootstrap is refused. Operators need
scoped qualified Lambda invocation in addition to verification reads.

## Recovery and safe notification-only replay

Reconcile is a 60-second Lambda with at most 50 seconds of internal scan budget;
SDK/row time admission reserves time for progress and fenced work. Each invocation
handles exactly one of `pending`, `overdue`, `expired`, `notifications`. The schedule
invokes all four separately. An empty manual payload handles **pending only**;
manual fault exercises must invoke all relevant classes explicitly. Progress is
CAS-fenced and advances before row work. A failed/killed row remains durable and
is revisited after cursor wrap. Up to ten 100-row pages remain a ceiling, not a
throughput promise. Incomplete scans emit failure and retain due work; sustained
incomplete scans require load/capacity investigation. No durable row is dropped
to make the scan appear successful.

Notifiers use 60-second Lambdas, 60-second leases and 360-second queue visibility.
A record is retained before claiming if less than 45 seconds remains. Expired
attempt 1/2 creates a notification-only intent; expired attempt 3 becomes
**AMBIGUOUS**, never falsely accepted/delivered. Queue DLQ records remain evidence.
Do not edit attempts/fences by hand or replay a completed investigation.

For an unexpired FAILED/AMBIGUOUS notification, inspect the plan, diagnose the
cause and review duplicates/cost before applying its **exact** JSON:

```bash
.venv/bin/python scripts/replay_notification.py --spec .local/customer/deployment.json --incident-id "$INCIDENT_ID" --kind INITIAL --output .local/customer/notification-review.json
.venv/bin/python scripts/replay_notification.py --spec .local/customer/deployment.json --incident-id "$INCIDENT_ID" --kind INITIAL --apply .local/customer/notification-review.json --output .local/customer/notification-replay-result.json
```

Use `--kind REPORT` for the report notification. Application UI roles do not get
these operational writes. The customer operator needs account-checked STS,
GetItem and TransactWriteItems on the intended table. The transaction changes
only notification state, writes its retry intent and an operator audit; it never
resets model budgets or changes the completed report. Two explicit replay runs
are allowed, each up to three attempts: **at most nine sends** including the
original run. Drift, acceptance, expiry or exhausted allowance refuses replay.
The stable notification ID remains unchanged so recipients can recognize duplicates.

SQS receipt correlation remains scoped to the trusted reports topic and declared
canary incident/initial notification. Up to nine receipt/publication IDs are
retained; duplicate receipt IDs are idempotent and the first time/ID is preserved.
An accepted retry can confirm a slot already delivered by an earlier lost-ack
publication. An accepted send alone still does not prove SQS receipt, and SQS
receipt still does not prove a mailbox. Existing explicit inbox attestation remains.

## Monitoring, capacity and cost changes

Health uses one independently scheduled invocation per service; delivery/backlog
uses another. The shared Observer Lambda now allows 180 seconds, with at most
150 seconds internally and 15 seconds reserved from the actual context. Routes
are bounded in child processes, SDK calls are admitted before starting, and
subscription discovery allows at most two pages per topic. An incomplete delivery
check emits CHECKS_INCOMPLETE/ATTENTION; health-only work does not emit a successful
delivery heartbeat. Availability is published before potentially failed freshness
reads. Native Lambda/queue error and missing-heartbeat signals remain independent.

At the default five-minute cadence, **S services means 288 × (S + 1) observer
invocations/day**, plus one daily canary and its receipt/pipeline work. One service
means 576 observer invocations/day, formerly 288. Recovery has four minute targets,
up to 5,760 scheduled invocations/day before retries, formerly 1,440. Extra cursor
writes and notification lease index entries add DynamoDB request/index volume.
These are request-count formulas, not an AWS invoice or a free-tier claim. Paused
specs do not activate observations; retained storage/alarms and base pipeline may
still cost money. Simultaneous schedules also require adequate customer concurrency.

AgentCore dashboards bind native Operation/Name/Resource dimensions to the actual
qualified endpoint, including errors, throttles, invocation counts and latency.
Remote model/tool metrics and application logs use the Bedrock region. Source:
[AWS CDK runtime metric implementation](https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-bedrockagentcore/lib/runtime/runtime-base.ts),
[AWS runtime logs and metrics](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-runtime-metrics.html).
The endpoint stage manages both retained standard groups; actual retention is
verified before promotion. Dashboard correctness is not proof of ingestion.
Stdout EMF extraction in the real host must pass G4. Local web UI stdout stays local
unless the customer supplies a reviewed log/metric transport; cloud monitoring
does not currently certify local UI execution. Do not infer remote native alarms
from dashboard widgets; worker Lambda failures/fallback remain the alert path.

The killable AgentCore SDK child bounds the client's wait and is reaped; it does
**not** prove cancellation of upstream execution or refund paid reservations.
There is no automatic standalone failover or ambiguous retry. Existing two-worker
throughput, fixed index partitions, release drain, static/public-only inventory,
regional dependencies, UI identity/evidence and hard spend limits remain as
documented in the review. Do not close those gates based on these fixes.

## Resume and verification

Read STATE, tracker and WORK_LOG first. Reproduce tests, schema/template validation,
13 deterministic build pairs/import checks and both complete owned release renders
using the commands recorded in corrective evidence. Local socket tests need loopback
binding; the desktop sandbox required an approved test-only escalation, with no AWS
permission or egress. Preserve the original review/reproductions as historical data.
The old defect runner targets application source at the reviewed revision; it is
not the current acceptance suite and should not overwrite historical evidence.

Next: customer staging qualification when actual prerequisites/budget exist, or
explicitly select the proposed Floci compatibility harness. Floci is not installed
and cannot establish AWS IAM/AgentCore/real-delivery production acceptance. Phase 5
requires the user's separate direction.
