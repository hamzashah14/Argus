# Phases 1–4 engineering review — 6 October 2026

**Historical review: eight findings, originally five P1 and three P2.**
Subsequent user-authorized batches A–C are now implemented locally; R01–R08 are
VERIFYING pending customer qualification. Read [CORRECTIONS.md](CORRECTIONS.md)
for current behavior/evidence and the R01 scope correction. Phase 5 remains
NOT_STARTED. Original diagnostic evidence below is preserved as historical data.

Reviewed application source: `175d7e9858b40aa2e5fa68ab7d163fde6bab1fd2`
(Phase 4 implementation `832a4e5`, followed by documentation). This review changes
records and adds an offline diagnostic; it does not remediate application code,
deploy infrastructure, install Floci, change dependencies or close gates.

The repository implementations of Phases 1–4 have local evidence. They are not
four completed production gates: P1.01 hosted CI and actual G2/G3/G4 qualification
remain pending. The tracker remains 13/52 DONE, with 20 original findings OPEN.
The eight R findings below are additional review records, linked to existing
tasks; they do not replace or close the original audit findings.

## Scope and evidence

Reviewed the configuration/UI/chat and tool contracts; release bindings, staged
promotion and IAM checks; incident ingress/outbox/claims/budgets/retries/evidence/
notifications; both execution adapters; observers, delivery canary, alarms,
dashboards and runbooks. Compared the current implementation with the task
acceptance requirements, supported same/split-region layouts and existing tests.

`python -m pytest -q`: **349 passed in 2.78s**. Eight independent negative
diagnostics reproduced the gaps below with injected clients, denied AWS client
construction and denied socket connections. Simulated elapsed times are clock
advances, not measurements of AWS or real waiting. Render inspection establishes
template omissions, not measured remote metric ingestion. See
[reproduce.py](reproduce.py) and
[sanitized reproductions](../evidence/review-phases-1-4/reproductions.json).

For current acceptance, run `python -m pytest -q`. The historical diagnostic
requires application source at the reviewed revision in a separate checkout and
a copy of this runner at the same repository-relative path (it was added during
the review). Do not run it against corrected source or overwrite original evidence.
Historical commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python docs/implementation/review-phases-1-4/reproduce.py --output .build/review-reproductions.json
```

The diagnostic exits zero when these OPEN defects reproduce. That is not a
remediation PASS. After repairs, preserve the historical evidence and add positive
regression/fault tests in the responsible implementation suites.

## Findings

Historical priority P1 means a release/reliability gate blocker under the stated
condition; P2 means an operational correctness or visibility gap. Current status
is VERIFYING; R01 specifically concerns the standalone verifier and exact role
binding, as clarified below.

| ID | Priority | Existing tasks | Gap and consequence | Evidence |
|---|---|---|---|---|
| R01 | P1 | P2.02, P2.05 | Standalone durable runtime verification omits actual execution-role verification. Full promotion already checked grants separately; exact stack-role binding was also absent. | Six unreviewed function roles produced PASS; no IAM call. |
| R02 | P1 | P3.03, P3.07, P3.08 | Reconciliation scans expired leases first with a shared budget and restarts from the first page. Repeated slow/failing early rows can prevent overdue incidents and pending outbox work from being visited. | Three sweeps, twelve failing recoveries; zero overdue/pending queries. |
| R03 | P1 | P2.05, P4.01, P4.03 | First deployment has a health-metric dependency before the documented observer activation; paused observations also require their missing metrics. The customer can be blocked from promoting the pipeline. | Coverage fails on the first health descriptor for both enabled and disabled observation specs. |
| R04 | P1 | P3.05, P3.08 | AgentCore stream bounds are checked after an entire line is read. An unterminated trickling line can exceed the absolute deadline and accumulate beyond the intended byte bound. | Actual botocore StreamingBody iterator performed 96,002 reads before detecting a simulated 30-second deadline violation. |
| R05 | P1 | P4.01, P4.02, P4.05 | Accepted observer inventories have no aggregate time admission or fair service scheduling; health publication occurs only after every service. Slow reads can discard already collected checks and repeatedly exclude later services. | Valid three-service config aborted after simulated 26 seconds, with zero health publications. |
| R06 | P2 | P4.04 | AgentCore model/tool widgets use the monitoring region, omit remote runtime log sources/native runtime health, and do not manage host log retention. Split-region remote execution is incompletely observable. | Split-region render: host us-east-1, model widget eu-central-1; no host log widget/retention resource. |
| R07 | P2 | P3.04, P3.06, P4.06 | A crash during the third notification attempt leaves an expired SENDING row that neither notifier nor reconciler finalizes. DLQ visibility exists, but durable notification state and safe recovery are incomplete. | Valid intent with expired third lease returns batch failure without terminal/recovery write. |
| R08 | P2 | P3.06, P4.05 | The receipt consumer retains the first SNS message ID, while successful retry acknowledgement stores the later publication ID. Valid duplicate delivery can permanently fail that canary slot's receipt comparison. | First receipt plus accepted second publish produced CANARY_RECEIPT_MISSED despite a current valid inbox attestation. |

### R01 — Verify the six pipeline roles

[infra/durable_ops.py](../../../infra/durable_ops.py), `verify_runtime` lines 215–255,
checks code, environment, timeout, memory, architecture and reserved concurrency.
At the reviewed revision, the standalone command never verified role
trust/grants/attachments. Full `owned_ops.verify_candidate` did verify all six
pipeline roles after calling it. The original promotion-wide claim was overstated.
The corrective implementation consolidates shared checks and enforces exact
stack-role binding; historical diagnostic PASS describes standalone only.
A sealed CloudFormation stack does not establish that IAM grants still match.

Repair: bind each function to its expected execution role and verify its actual
trust, inline policy, attachments and effective restrictions against the reviewed
template. Cover both removed grants and unexpected broad grants, all six roles,
and both runtime targets. Verify required KMS/DynamoDB/S3/SNS actions with the
actual customer role in staging. Do not infer effective permission from JSON alone.

### R02 — Fair, resumable recovery scans

[kira/pipeline.py](../../../kira/pipeline.py), `reconcile` lines 143–202,
gives all three indexes one 45-second budget. Each sweep starts its cursor at None;
expired work can consume the budget before overdue or pending work starts. The
diagnostic uses five persistently failing early rows and a simulated 12-second
read/write latency per row, within combined SDK time budgets. Four rows consume
48 seconds; the same prefix recurs on subsequent sweeps.

Repair: guarantee each recovery class a share of the budget, persist progress or
partition/rotate work, bound each row operation by remaining time and isolate
repeated per-row failures without deleting the durable intent. Make overlapping
sweeps safe. Test several pages, continuous arrivals, slow/denied writes and
poison prefixes; prove pending initial/report intents are serviced and every
accepted incident ends terminal or in an explicit recoverable state.

### R03 — Separate first bootstrap from steady-state coverage

[infra/verify.py](../../../infra/verify.py), `coverage` line 68, requires every
descriptor from [infra/spec.py](../../../infra/spec.py), including observer Health
metrics regardless of `observability.enabled`. `owned_ops.promotion_gate` calls
coverage before durable routing. The Phase 4 guide activates that routing before
observation schedules; the disabled observer returns without publishing anything.
The documented first-deployment path cannot generate the metrics it demands.

Repair: define separate bootstrap and steady-state receipts. Establish/verify
collector telemetry first; explicitly invoke the pinned enabled observer to seed
health before the appropriate strict coverage gate, or stage health qualification
after activation with a separately enforced gate. Specify safe disabled behavior.
Retain fail-closed service telemetry validation; do not remove all coverage checks
to unblock deployment. Exercise the entire fresh-account stage order in tests,
including missing canary/inbox warnings, and then rehearse it in customer staging.

### R04 — Bound stream reads before line buffering

[kira/agentcore.py](../../../kira/agentcore.py), `invoke` lines 26–93,
uses `iter_lines(chunk_size=1)` and checks limits only after a yielded line.
Botocore accumulates an unterminated line internally. Socket read timeouts limit
an idle read, not an overall connection receiving repeated small fragments.
One-byte reads also add unnecessary per-byte processing.

Repair: bounded incremental framing with byte/time checks during reads, plus a
mechanism that interrupts a blocked read at the absolute attempt deadline. Avoid
an unbounded reader thread that keeps executing after cancellation. Test a real
local socket with silence, slow fragments, oversized unterminated lines, valid
heartbeats, mid-result disconnects and late valid results. Prove closure and
fencing with both Lambda and actual AgentCore. Local closure still does not prove
upstream model cancellation or eliminate ambiguous invocation charges.

### R05 — Make observer cost fit its supported inventory

[kira/observability.py](../../../kira/observability.py), `observer` line 236,
executes probes and two telemetry reads per service sequentially. A fixed
20-second freshness reserve aborts the next service after 26 simulated seconds in
a valid three-service config. Metrics already collected are unpublished. The
post-service canary reads and paged recipient checks also lack a shared remaining
time guard. Missing-heartbeat alarms reveal a failing observer; they do not
recover the omitted per-service health measurements.

Repair: admit inventory against an explicit aggregate time/call budget or split
it into independently scheduled partitions; publish completed health batches,
rotate service order and give delivery/backlog checks independent execution
budgets. Bound subscription pagination and per-call timeouts by time remaining.
Persist/emit explicit incomplete checks instead of treating them as healthy.
Test supported inventory limits, slow APIs, several failing services, maintenance
exit and observer retries; prove each service receives its promised check cadence.

### R06 — Observe the remote host explicitly

[infra/observation_templates.py](../../../infra/observation_templates.py) lines
374–499 give every widget the monitoring region and use only pipeline/observer
Lambda log sources. Model/tool telemetry executes in the AgentCore host for that
target. [infra/owned_runtime.py](../../../infra/owned_runtime.py), `agentcore_release`
line 118, grants host logging in the Bedrock region but creates no retained host
log group with `log_retention_days`. The render omission is reproduced; actual
stdout-to-EMF extraction remains unqualified. AWS documents runtime-specific
standard log destinations, which also need explicit binding in this release.
[AWS AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html).

Repair: bind the qualified runtime/endpoint log destination after its identity is
collected, configure retention, include appropriate native remote errors/throttles/
latency and read custom metrics from their actual region. Prove EMF ingestion or
use an explicitly supported metric emission path. Include authorized local UI
execution telemetry in the visibility contract; stdout in a customer's UI process
alone is not CloudWatch telemetry. Test both same/split regions and real host logs.

### R07 — Finalize ambiguity and provide notification recovery

[kira/pipeline.py](../../../kira/pipeline.py), `notify` line 394, rejects attempts
>=3 before any lease recovery. [kira/ledger.py](../../../kira/ledger.py),
`claim_notification` line 797, also refuses a third expired SENDING lease. A crash
after claim or SNS send can strand that state. Existing FAILED handling covers a
handled publish exception, not a process kill or lost acknowledgement write.

Repair: reconcile expired notification leases into an explicit terminal ambiguous
outcome, retain stable IDs, and add a reviewed notification-only replay/reattempt
procedure with its own audit/budget/fencing. Never rerun completed model work to
resend an alert. Distinguish accepted, failed, ambiguous and recipient-confirmed
delivery. Also respect the Lambda context across serial two-record notifier
batches so a late first record cannot start a second unsafe attempt.

### R08 — Correlate receipts across legitimate duplicate publications

[kira/observability.py](../../../kira/observability.py), `recipient` line 99,
uses `if_not_exists` for the first receipt ID. `verify_canary` line 196 demands
that ID equal the final notification publisher ID. A send succeeds, its ledger
ack fails, the receiver records the first send, and the retry succeeds with a
second SNS ID: later receipts cannot update the retained first ID.

Repair: correlate the stable notification identity and maintain bounded,
authenticated accepted-publication/receipt IDs, or an equivalent durable
per-publication record. Do not relax source/topic/incident checks or confuse SQS
delivery with a real inbox receipt. Test send/ack crash windows, reordered
receipts, duplicate messages, receipt-before-ack and recipient rotation.

## Capacity and existing limitations to retain

These are not eight further newly reproduced defects. They are documented design
constraints or unmeasured risks requiring explicit qualification:

- **Two investigation workers:** with a 400-second worst-case attempt budget,
  a continuously busy pair offers roughly 0.3 attempts/minute before overhead.
  This is a bound calculation, not a benchmark. It cannot sustain the tentative
  one unique incident/minute if attempts approach that duration. Burst excess
  must become truthful degraded results by deadline while initial alerts remain
  independent. Measure service time, backlog and accepted-event accounting before
  increasing concurrency or making full-report latency promises.
- **Central index keys:** PendingIntents, ActiveLeases and DueIncidents use fixed
  PENDING/ACTIVE/OPEN partition keys and ALL projections. They centralize queue
  traffic and duplicate growing metadata. Streams process unrelated ledger
  mutations as well. Benchmark index/query/write pressure; consider sharding,
  narrower projections and intent filtering when observed scale warrants it.
  No numeric AWS throughput claim or present pilot saturation is established.
- **Recovery ceilings:** each sweep is capped at ten 100-row pages per index,
  shares one budget and runs every minute. Measure iterator lag and sweep
  completeness, not only whether a heartbeat exists. Fix R02 before load sizing.
- **Release drain:** an incident pins its original execution release and policy.
  Shared queues do not automatically route it back to that release after a
  promotion. The existing guide requires draining/recovering accepted incidents;
  enforce that prerequisite or add release-aware routing before claiming rolling
  upgrades. Retained old artifacts alone do not satisfy it.
- **Spend and retention:** bounded tokens/calls/output are not a hard monthly
  spend cap or billed Logs Insights scan-byte limit. Retained candidate resources,
  custom metrics, logs and checkpoints have lifecycle/cost implications. Actual
  quotas, region/model access and cost remain customer-specific, with the previously
  observed Lambda quota of 10 still unresolved. Floci cannot close that blocker.
- **Identity/evidence:** shared UI password, process/session-local chat limits,
  no individual resource authorization and incomplete end-to-end data governance
  remain planned Phase 5 work. Do not expose this as a public multi-user production
  application until those gates pass. We did not implement Phase 5 during review.
- **Detection reach:** static inventory and public HTTPS probes do not cover
  arbitrary VPC-only services or dynamic fleets. Customers must install real
  collectors/readiness/heartbeat writers and refresh inventory. Fallback paths
  inside one AWS region do not cover a whole regional outage; the runbook already
  assigns an external monitor/channel for that condition.
- **Qualification:** hosted CI, ARM64 host boot, actual IAM/KMS behavior, concurrent
  transactions, real delivery/receipt, rollback/restore, fault/load accounting and
  the sustained staging observation period remain pending. A local suite cannot
  establish any of these simply by increasing its test count.

## Corrective sequence — current progress

| Batch | Work | Completion evidence | Status |
|---|---|---|---|
| A — Release gates | R01 pipeline role binding/checks; R03 bootstrap/paused coverage and full stage-order procedure | Reject role drift and missing required telemetry; fresh standalone/AgentCore local deployment contract works without disabling safeguards | LOCAL IMPLEMENTATION PASS / LIVE VERIFYING |
| B — Durable execution | R02 fair resumable sweep; R04 interruptible bounded reader; R07 notification ambiguity/replay | Multi-page poison-prefix recovery; real socket deadline tests; third-attempt kill/ack-loss records and notification-only replay | LOCAL IMPLEMENTATION PASS / LIVE VERIFYING |
| C — Observability | R05 aggregate/partitioned observer; R08 duplicate-aware receipts; R06 remote-region/native metrics/log retention | Every supported service checked on cadence; send/receipt reorder matrix; both target/region templates and host metric evidence | LOCAL IMPLEMENTATION PASS / LIVE VERIFYING |
| D — Cost-conscious integration | Evaluate pinned Floci subset using the [compatibility plan](FLOCI.md), scripted model and local host tests | Explicit PASS/UNSUPPORTED matrix with no AWS egress; accepted-event fault accounting and measured local latency | PROPOSED |
| E — Customer qualification | Separately budgeted actual AWS staging checks when prerequisites exist | IAM/model/host/queue/receipt/rollback/cost evidence; preserve pending G1/G2/G3/G4 until their full acceptance passes | PENDING INPUTS |

Batches A–C repair existing-phase omissions; they are not a new phase or Phase 5.
The user subsequently authorized continuation. A–C now have local fixes/tests
recorded in [CORRECTIONS.md](CORRECTIONS.md). D remains proposed and E remains
pending actual inputs/budget. They do not authorize Phase 5 or AWS deployment.
