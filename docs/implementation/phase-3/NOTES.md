# Phase 3 checkpoint — 6 October 2026

Repository implementation and local verification are complete for this checkpoint.
P3.01–P3.08 are **VERIFYING**, G3 NOT_RUN. G1 hosted CI and G2 live staging remain
pending. No Phase 4 work has started and no audit finding is closed.

Branch: `codex/phase-3-durable-incidents`; parent `01e4ce8`. The user authorized
this phase, selected owned Python orchestration, required customer choice of
standalone or AWS AgentCore, and asked for affordable deployment/setup guidance.
No project AWS API calls, resources, model invocations, notifications, remote push
or hosted CI dispatch occurred in this checkpoint. Official documentation and
public dependency advisories were accessed; these are not account validation.

## Implemented behavior

- Validated SNS source/inventory and stable event identity; atomic durable incident,
  event, notification and work intents; conditional claims and attempt fencing.
- Streams/queues plus scheduled repair for missed dispatch, expired leases and
  overdue incidents. Retry and reviewed replay preserve identity and allowances.
- Independent initial/follow-up consumers, stable IDs, bounded publication and
  PUBLISHER_ACCEPTED status. Private encrypted, versioned reports/checkpoints are
  read through bounded, checksum/version/retention checks in the authorized UI.
- Shared SDK-based Converse loop for chat and incidents. Exact CountTokens before
  inference, conservative durable token/step/tool/query reservations across
  attempts, observed usage, deadlines, scoped inventory and strict tool contracts.
- Standalone executes in the customer Lambda worker (chat executes in the UI
  process). AgentCore runs the same loop behind IAM with an explicit release
  endpoint, validated requests/results, SSE heartbeats, two host slots and no
  ambiguous retry or automatic failover. Remote failures wait for lease recovery.
- Six incident functions, owned tool versions, optional ARM64 direct-code host and
  pinned endpoint; deterministic builds, same/split-region rendering, candidate
  drift checks, scoped IAM and explicitly paid staging canary/promotion gates.
- Investigation pause preserves capture/initial alerts/recovery. Initial reserved
  capacity and work concurrency of 2 are planned; actual account capacity is unproven.

## Boundaries and next steps

Read [validation](VALIDATION.md), [operator guide](GUIDE.md),
[runtime decision](RUNTIME_DECISION.md) and [deployment/cost guide](DEPLOYMENT_AND_COST.md).
The new paths have no Agents Classic creation dependency. Existing Classic code
is compatibility code; its account eligibility is not established.

1. Resolve actual regions/model, distinct identities, pilot inventory/telemetry,
   verified recipients, stable HTTPS UI URL and approved staging budget. The prior
   regional Lambda quota of 10 is a capacity gap, not proof of reserved capacity.
2. Run hosted CI and selected-target G2 candidate/coverage/IAM/canary checks.
   AgentCore requires actual ARM64 service boot and endpoint verification.
3. Run G3 on real DynamoDB/SQS/SNS: concurrent reservations/claims, blocked streams,
   hard worker/host termination, missed Streams, stale completions, evidence and
   publication faults, delivery latency/load and 1,000 accepted-event accounting.
4. Query count/window bounds are not a pre-query scan-byte or dollar cap. Record
   measured spend and resolve this acceptance limitation before qualification.
   Chat has a per-request budget; per-user limits belong to Phase 5.
5. Keep Phase 4 NOT_STARTED until explicitly authorized. Local passing tests do
   not establish production readiness, delivery, isolation or actual AWS recovery.
