**Kira production implementation plan — phased execution and verification**

**Confirmed operating model (1 October 2026).** This is an open-source project deployed and operated in each customer's own cloud account. The project supplies code, templates and instructions for web chat, automatic alert investigations and notifications; a local desktop client follows later. Operations/production owners in this plan mean the deployment operator/customer. No maintainer-operated hosting or managed service is planned. The existing 52 reliability tasks remain applicable. Publication and desktop work are tracked separately in [OPEN_SOURCE_PRODUCT_PLAN.md](/Users/hamzashoaib/Documents/Side-hustles/AIOps-Agent/OPEN_SOURCE_PRODUCT_PLAN.md).

Prepared 1 October 2026. Source: [PRODUCTION_READINESS_AUDIT.md](/Users/hamzashoaib/Documents/Side-hustles/AIOps-Agent/PRODUCTION_READINESS_AUDIT.md). Progress is maintained in [IMPLEMENTATION_TRACKER.md](/Users/hamzashoaib/Documents/Side-hustles/AIOps-Agent/IMPLEMENTATION_TRACKER.md). This is a plan for implementation; no implementation task or production release is complete merely because this document exists.

The scope is all 20 audit findings, dependable alert delivery, reproducible releases, production access controls, and operational handover. Existing Bedrock tools and the Streamlit UI remain the starting point. Automatic remediation, multi-tenant SaaS, a multi-region disaster-recovery build, and replacing the application framework are outside this release unless the service requirements explicitly add them. Existing uncommitted user work must be preserved.

**Execution and tracking rules.** Work in the dependency order below, using one reviewable change per task or a tightly related task group. Each task has a stable ID, suggested owner role, prerequisite tasks, deliverable, and observable acceptance condition. Roles are not assigned people. The tracker is the source of truth for status, actual owner, PR/commit, evidence, and blockers; it starts with all 52 tasks NOT_STARTED. Run tests appropriate to the change and record results. Mark DONE only after the task's acceptance condition has evidence and any required live verification has passed. Passing the original 21 tests does not close the findings. No recurring automation is created by this plan.

Use NOT_STARTED → IN_PROGRESS → IN_REVIEW → VERIFYING → DONE; use BLOCKED only with the missing dependency, owner, next action, and review date recorded. At the beginning of a work session, select the earliest eligible task and record its owner; at the end, update evidence and next actions. Keep at most one primary implementation task active per engineer. A phase closes only when all its tasks and its gate pass. Findings close through the separate coverage map, not through a code-merged percentage.

**Architecture selected for planning.** Keep a small AWS-native system: CloudWatch/EventBridge → scoped SNS/SQS intake → normalized incident/event records in DynamoDB → transactional outbox → separate investigation and notification queues → bounded Lambda worker and notifier → private report/evidence storage. A DynamoDB Streams dispatcher provides prompt dispatch; a scheduled reconciler recovers pending outbox work and abandoned/overdue incidents. Initial notifications have separate capacity and do not wait for Bedrock. The UI uses authenticated, authorized access to the approved agent and stored reports. Infrastructure defaults to SAM/CloudFormation; use an existing organization standard if one exists.

A database commit followed by an unprotected queue write is insufficient: incident state and dispatch intent must be atomic, with an idempotent dispatcher and reconciliation. DynamoDB Streams retains changes for only 24 hours, so the stream must not be the only recovery record; keep pending outbox records until acknowledged and reconciled. [AWS Streams documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html).

For SQS consumers, configure visibility from the actual function timeout and batching window, use partial batch responses, and define DLQs/retention/replay. AWS recommends at least six times the function timeout plus the batching window for visibility; test the resulting retry delay against the incident deadline. Do not assume the old Lambda asynchronous retry configuration governs SQS processing. [AWS SQS/Lambda configuration](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html).

Use separate incident lifecycle, investigation, and notification status fields. Lifecycle: OPEN → RECOVERED → CLOSED. Investigation: QUEUED → RUNNING → SUCCEEDED / PARTIAL / FAILED / EXPIRED, with explicit retry scheduling. Notification: PENDING → PUBLISH_ACCEPTED → DELIVERY_VERIFIED where verifiable, or RETRY_PENDING / DEAD_LETTER. Persist event identity, incident/correlation ID, source and receive times, actor/scope, release version, attempt/lease/fencing token, evidence references, error classification, and next action. Provider acceptance is not proof of an email reaching a human. Store large evidence in object storage, not queue messages or database items.

Exactly-once model execution or email delivery cannot be promised across ambiguous network failures. Conditional claims and fencing prevent simultaneous legitimate processing and stale writes; bounded retries and stable report IDs limit duplicates. Model work may continue upstream after a local cancellation. If the bounded worker prototype cannot meet reliability requirements or investigations must span attempts with richer checkpoints, adopt a Step Functions Standard workflow at P3.05 and revise the estimate/manifest; external workflow errors and timeouts need explicit handling. [AWS workflow error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html).

**Proposed acceptance targets, pending P0.03.** Measure from durable ingress receive time. Initial notification: p95 ≤60 seconds under the agreed steady/burst profile. Investigation: completed or explicitly degraded status and follow-up intent ≤10 minutes; backlog delay counts in this budget. Detection targets are per service and separate from pipeline latency. Suggested pilot availability target: detect a failed critical endpoint within 2 minutes; choose evaluation periods to balance noise. A hard worker timeout must leave room for external reconciliation within the overall target. Suggested engineering prototype: ≤7-minute normal attempt, ≤8-minute Lambda ceiling, ≤1-minute overdue reconciliation, with measured queue and notification headroom. These are starting budgets, not guarantees; retries must fit or yield a degraded report and visible recovery state. Accepted-event accounting is 100% in the injected test set, not a claim of infallible infrastructure.

**Decisions to record before dependent integrations.** P0.02–P0.05 collect the AWS accounts/regions and fleet, identity provider/hosting, fallback notification channel and owner, capacity/budget targets, data classification/retention, and production change process. Repository-level work can proceed with synthetic fixtures while those details are collected. Staging deployments need verified account/model access; SSO needs an actual identity provider; production cutover requires a concrete qualified release decision. A decision with no owner or evidence remains unresolved.

**Effort and sequencing.** The fully decomposed scope is approximately 17–26 engineer-days, plus a 3–7-calendar-day staging observation and production rollout observation. This refines the audit's earlier 12–19-day estimate by including outbox recovery, identity integration, migration, and operational handover explicitly. Assume one engineer familiar with AWS; account/identity lead time is additional. Estimates are not scheduled dates. The default execution path is phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Individual prerequisite lists allow independent repository/security work to proceed earlier; this does not authorize unattended deployments or delegation.

| Phase | Focus | Tasks | Effort | Phase gate |
|---|---|---:|---|---|
| 0 | Baseline and production requirements | 6 | 1–2 days | G0: Baseline, inventory, targets, decision owners, prerequisites, and regression cases recorded. |
| 1 | Correctness fixes and automated checks | 8 | 2–3 days | G1: Reproducible CI and all deterministic correctness fixes pass their regression/contract checks. |
| 2 | Isolated infrastructure and safe release mechanics | 6 | 2–3 days | G2: Isolated staging and immutable candidate release work; no draft action changes the live release. |
| 3 | Durable incident processing and notification | 8 | 4–6 days | G3: All accepted fault-injected incidents are durable, deduplicated, and completed or recoverable; initial alerts survive model outage. |
| 4 | Detection coverage and operational visibility | 6 | 2–3 days | G4: Service and telemetry failures are detected; an independent canary proves pipeline failures are visible. |
| 5 | Identity, evidence safety, and diagnostic quality | 6 | 3–4 days | G5: Identity, scope, redaction, retention, and diagnosis-quality evaluations meet recorded acceptance requirements. |
| 6 | Integration, capacity, and release qualification | 6 | 2–3 days plus 3–7 calendar days observation | G6: Frozen staging candidate passes integration, failure, capacity, rollback, observation, and finding-closure review. |
| 7 | Controlled production rollout and handover | 6 | 1–2 days plus rollout observation | G7: Production fleet coverage and delivery verified, migration complete, and operational ownership accepted. |

**Phase 0: Baseline and production requirements.** Agree scope and establish an implementation baseline before cloud writes. Suggested effort: 1–2 days. Gate G0: Baseline, inventory, targets, decision owners, prerequisites, and regression cases recorded.

**P0.01 — Capture the intended project baseline.** Prerequisites: none. Suggested owner: Engineering. Findings: F18.

Review existing modified, deleted, and untracked files; preserve their contents; identify the intended release; record a commit and build identity when implementation starts. Create a development branch without discarding user work.

Acceptance: A fresh checkout of the selected revision contains every required file and the existing 21 tests can be reproduced.

**P0.02 — Inventory services and dependencies.** Prerequisites: none. Suggested owner: Operations. Findings: F05, F10, F12.

Record each instance/service, environment, account, monitor/model region, hostname, health endpoint, log groups, metric dimensions, critical dependency, owner, and maintenance policy. Identify static versus autoscaled inventory.

Acceptance: Every in-scope service has an owner and a detection/evidence source; unsupported services are explicitly listed.

**P0.03 — Set reliability and capacity targets.** Prerequisites: none. Suggested owner: Operations. Findings: F01, F02, F03, F05, F06.

Define initial-alert and report targets, normal/burst event volume, per-user chat volume, required recovery time, notification channel, and a monetary budget. Separate alarm detection delay from pipeline latency.

Acceptance: Targets, load profile, budget limits, and notification owner are recorded; tentative defaults are identified as tentative.

**P0.04 — Record deployment and security decisions.** Prerequisites: P0.02, P0.03. Suggested owner: Engineering + Operations. Findings: F04, F07, F08, F10.

Record environment/account separation, infrastructure framework, identity provider, UI hosting, evidence retention/classification, key management, fallback notification channel, and workload identity. Use the defaults below until a real integration requires a specific choice.

Acceptance: Decision register identifies each selected option, owner, unresolved dependency, and the task it blocks.

**P0.05 — Verify target-account prerequisites.** Prerequisites: P0.02, P0.04. Suggested owner: Operations. Findings: F04, F06, F09, F10.

Use read-only inspection to confirm account/regions, model availability and invocation permissions, quotas, existing resources, log access, and delivery subscriptions. Inventory legacy resource ownership before migration. Do not print credentials.

Acceptance: Preflight evidence lists actual capabilities and gaps; accounts and production resources are unambiguously identified.

**New-deployment clarification (1 October 2026).** The user confirmed that this
project has no deployed AWS infrastructure. For this starting point, P0.05 and G0
assess readiness to begin engineering: verify the configured account identity,
inspect regional service access/capacity and existing project resources, and record
missing capabilities with owners and dependent tasks. Existing EC2 instances,
Bedrock agents, runtime roles and subscriptions are not prerequisites for completing
this assessment. Their creation and effective-permission/delivery checks belong to
P2/P3/P6. An empty inventory or an explicitly recorded capacity gap is an assessment
result, not a passed deployment test. Final region/model/budget decisions remain
required before cloud provisioning. This clarification does not qualify production.

**P0.06 — Establish regression fixtures and evidence rules.** Prerequisites: P0.01. Suggested owner: Engineering. Findings: F01, F03, F12, F13, F14, F15, F16, F20.

Preserve the audit reproductions as deterministic fixtures: duplicate records, blocked streams, Unicode reports, timezone offsets, dimensionless metrics, large discovery, minimal config, and invalid schema. Define the evidence folder/CI artifact convention.

Acceptance: Each reproduction names its expected corrected behavior; baseline failures are documented without making a permanently failing main CI suite.


**Phase 1: Correctness fixes and automated checks.** Correct deterministic defects and establish fast CI before adding new cloud behavior. Suggested effort: 2–3 days. Gate G1: Reproducible CI and all deterministic correctness fixes pass their regression/contract checks.

**P1.01 — Create reproducible builds and CI.** Prerequisites: P0.01, P0.06. Suggested owner: Engineering. Findings: F18.

Convert embedded checks into discoverable tests; pin Python and dependencies using one lock strategy; separate application/development dependencies; pin and package the Lambda SDK. Add linting, shell checks, schema validation, secret/dependency scans, and clean-build checks.

Acceptance: All 21 existing checks run in CI; builds record dependency and artifact hashes; scan findings are triaged rather than silently ignored.

**P1.02 — Repair and validate tool contracts.** Prerequisites: P1.01. Suggested owner: Engineering. Findings: F20.

Define datapoints with named timestamp/value fields or a valid fully specified array schema; keep handler and OpenAPI responses synchronized; specify statuses and error shapes; validate actual fixtures against the contract.

Acceptance: Both OpenAPI documents validate and successful, no-data, partial, and error fixtures match their declared schemas.

**P1.03 — Centralize and validate configuration.** Prerequisites: P1.01. Suggested owner: Engineering. Findings: F16.

Use a typed configuration model and explicit export to child processes. Validate account/environment, regions, names, prefix, thresholds, retention, concurrency, required secrets, and production aliases before mutation. Reject unknown keys.

Acceptance: Required-only configuration works; invalid settings fail before any cloud write; production rejects draft aliases and zero worker capacity unless an explicit maintenance mode is selected.

**P1.04 — Normalize timestamps and retain uncertainty.** Prerequisites: P1.01. Suggested owner: Engineering. Findings: F14.

Share parsing rules for UTC/ISO-8601 timestamps. Normalize offsets, reject unsupported values, preserve raw event timestamps, and distinguish incident time, state-change time, receive time, and processing time.

Acceptance: Offset-equivalent inputs query identical windows; malformed event time creates an explicit degraded record rather than silently substituting the current time.

**P1.05 — Resolve metrics using exact dimensions.** Prerequisites: P0.02, P1.02. Suggested owner: Engineering. Findings: F12.

Build an allowlisted metric descriptor with namespace, name, statistic, unit, and exact dimensions. Support the dimensionless Nginx series and configured instance/path/process/volume series; carry the firing alarm descriptor into the incident.

Acceptance: Fixtures prove each supported alarm can retrieve its own metric; unauthorized/unsupported descriptors fail explicitly; no-data is distinct from metric access failure.

**P1.06 — Bound log discovery and all tool responses.** Prerequisites: P1.02. Suggested owner: Engineering. Findings: F15.

Add paginated discovery with continuation and completeness markers; validate opaque tokens against instance/environment scope. Apply a UTF-8 budget to the full response envelope, including discovery and error metadata; preserve the nearest useful evidence.

Acceptance: More than 250 groups can be traversed without silent omission; long names and multibyte messages stay within the configured complete-envelope budget.

**P1.07 — Make report payloads byte-safe.** Prerequisites: P1.01. Suggested owner: Engineering. Findings: F13.

Apply one UTF-8 sizing utility to the complete SNS message, metadata, and truncation markers; reject oversized subject/control characters; create a short fallback report even when output is malformed. Later route full reports through restricted storage.

Acceptance: Boundary tests pass for ASCII, emoji, CJK, metadata, and empty output; no produced publish request exceeds the configured transport limit.

**P1.08 — Handle UI failures and bound sessions.** Prerequisites: P1.01, P1.03. Suggested owner: Engineering. Findings: F19.

Catch client construction and stream errors, handle empty/partial answers, distinguish configured status from connectivity, and set input/history/output/work limits. Provide stable error IDs and safe user messages; preserve useful partial content.

Acceptance: UI tests cover absent/expired credentials, unavailable model, empty stream, long history, and retry; secrets and raw tracebacks are not exposed.


**Phase 2: Isolated infrastructure and safe release mechanics.** Create the deployment boundary before changing the production incident flow. Suggested effort: 2–3 days. Gate G2: Isolated staging and immutable candidate release work; no draft action changes the live release.

**P2.01 — Define infrastructure as code and migration ownership.** Prerequisites: P0.04, P0.05, P1.03. Suggested owner: Engineering. Findings: F10, F11, F18.

Default to AWS SAM/CloudFormation for this Lambda-oriented project unless an existing organizational standard is selected. Parameterize environment/account/regions and tag resources. Build separate regional stacks where monitoring and Bedrock differ. Document import versus replacement of existing resources and retain data stores on stack deletion.

Acceptance: Staging deploys from a clean environment without changing production; a reviewed resource plan identifies ownership and migration behavior.

**P2.02 — Separate roles, secrets, and resource access.** Prerequisites: P2.01. Suggested owner: Engineering. Findings: F07, F08, F10.

Define distinct least-privilege identities for ingestion, tools, investigation, dispatch, notifications, UI, CI, and deployment. Scope log/metric descriptors to inventory; restrict evidence and KMS access; define secret rotation and account/region checks.

Acceptance: Policy tests and staging calls demonstrate intended access and reject cross-environment or unrelated data access; no application identity can deploy infrastructure.

**P2.03 — Build immutable Lambda releases.** Prerequisites: P1.01, P2.01. Suggested owner: Engineering. Findings: F04, F18.

Package dependencies deterministically and publish qualified function versions with version-specific configuration. Record source SHA, SDK/runtime, code hashes, and qualified ARNs in a release manifest. Keep active versions available through the rollback window.

Acceptance: Changing a draft build leaves the active function version and its configuration unchanged; artifacts can be rebuilt or retrieved by hash.

**P2.04 — Bind agent releases to exact tool versions.** Prerequisites: P1.02, P2.02, P2.03. Suggested owner: Engineering. Findings: F04, F20.

Create candidate agent releases referencing the matching qualified tool versions and schemas. Add version-scoped grants before removing anything obsolete. Verify actual Bedrock support; if qualified executors are incompatible, use release-specific immutable function names. Include model, prompt, alias routing, and schema hashes in the manifest.

Acceptance: Candidate invocation works in staging; the active agent retains old behavior until promotion; failed grants cannot remove live permissions.

**P2.05 — Make deployment verification fail accurately.** Prerequisites: P2.01, P1.03. Suggested owner: Engineering. Findings: F09, F16.

Inspect PutTargets per-entry results and other partial outcomes; distinguish missing telemetry from access/API errors; validate required metric filters with real fixtures. Produce a deployment coverage manifest and stop promotion when required components fail.

Acceptance: Injected registration failure, denied metric discovery, wrong account, missing required metric, or unsupported concurrency produces a clear non-success result.

**P2.06 — Reconcile retired alarms and subscribers.** Prerequisites: P0.02, P2.01, P2.05. Suggested owner: Engineering + Operations. Findings: F11.

Calculate desired versus owned resources, show the retirement diff, disable obsolete alarm actions before cleanup, remove retired subscriptions, and preserve unrelated resources/history. Generate CWAgent settings from the same inventory/configuration.

Acceptance: Removing an instance, disabling a feature, changing a prefix, or replacing an email recipient produces the expected reviewed changes; former recipients stop receiving reports.


**Phase 3: Durable incident processing and notification.** Make initial alerting independent of model execution and recover every accepted incident. Suggested effort: 4–6 days. Gate G3: All accepted fault-injected incidents are durable, deduplicated, and completed or recoverable; initial alerts survive model outage.

2026-10-06 implementation decision: the user selected an owned Python orchestration
layer using Bedrock models, with customer choice of standalone Lambda execution
(default) or AWS AgentCore hosting. Both use the same durable pipeline and model/tool
contracts. New deployments have no Agents Classic creation dependency. Substitute
owned model/tool/runtime release verification for the Classic-specific P2.04 path;
retain its isolation, candidate, promotion and rollback gates. See the
[decision record](docs/implementation/phase-3/RUNTIME_DECISION.md). Token/step/tool/query
reservations and deadlines are implemented locally. Query count/window/result-byte
limits do not satisfy a hard billed scan-byte/dollar cap; this acceptance limitation
remains open alongside actual G2/G3 validation. No Phase 4 advancement is implied.

**P3.01 — Add durable ingress and incident schema.** Prerequisites: P2.01, P2.02, P1.04. Suggested owner: Engineering. Findings: F02, F03, F19.

Route SNS/EventBridge events into SQS with delivery failure queues and source checks. Normalize source/account/region/instance identifiers and define versioned incident, event, attempt, evidence, and notification records in DynamoDB. Use stable native event identity where available plus semantic keys for alarm transitions.

Acceptance: Accepted means durably received, not merely logged; duplicate and malformed events are classified; source identity and original event are retained under the data policy.

**P3.02 — Implement idempotency, leases, and incident correlation.** Prerequisites: P3.01. Suggested owner: Engineering. Findings: F03.

Claim work with conditional writes, bounded leases, attempt counters, and monotonically increasing fencing tokens. Ignore completed events; recover abandoned attempts only after execution safety checks. Correlate related alerts without dropping evidence or suppressing recovery/new incidents.

Acceptance: Concurrent delivery of the same event creates one active claim; stale workers cannot overwrite newer results; distinct incidents are never deduplicated only because they share an instance.

**P3.03 — Close the persistence-to-dispatch gap.** Prerequisites: P3.01, P3.02. Suggested owner: Engineering. Findings: F02, F03.

Write incident state and outgoing investigation/initial-notification intents atomically. Dispatch intents through DynamoDB Streams into dedicated queues; deduplicate dispatch and retain pending intents. Add a scheduled reconciler for missed stream records, expired leases, and overdue incidents.

Acceptance: Faults between database commit and queue send do not lose work; dispatcher restart and missed-stream simulations recover pending intents without repeating terminal work.

**P3.04 — Send initial alerts independently.** Prerequisites: P3.03, P1.07. Suggested owner: Engineering. Findings: F02, F05, F06.

Create a notification consumer for minimal initial alerts with incident ID, known trigger, timestamp, and status link. Reserve capacity separate from model work, retry transient publication failures, verify recipients, and expose permanent failures through the fallback route.

Acceptance: With Bedrock denied, throttled, or disabled, an initial alert still arrives within the agreed target under the agreed load; no sensitive raw evidence is emailed.

**P3.05 — Enforce worker deadlines and checkpoint evidence.** Prerequisites: P2.04, P3.02, P3.03, P1.06. Suggested owner: Engineering. Findings: F01, F02.

Set one absolute attempt deadline and bounded connection/read/retry budgets across worker and tools. Prototype cancellation of a blocked stream in the actual runtime; close streams and stop queries where possible. Persist redacted checkpoints and use the external reconciler to mark overdue attempts when a worker is killed. Fence late results.

Acceptance: Blocked reads, SDK retries, Lambda termination, and tool timeouts yield a durable partial/failed status and follow-up intent; the design does not depend on a killed Lambda executing finally or sending email.

**P3.06 — Store results and retry follow-up delivery separately.** Prerequisites: P3.03, P3.04, P3.05. Suggested owner: Engineering. Findings: F02, F08, F13, F19.

Store classified/redacted evidence and full reports in private encrypted object storage with retention, access checks, and immutable report versions. Atomically record report references and notification intents. Retry publication without rerunning the model; distinguish publisher acceptance from recipient delivery.

Acceptance: A successful investigation survives notifier failure; full report access requires authorization; ambiguous SNS acknowledgement uses a stable notification ID and does not claim exactly-once email.

**P3.07 — Add bounded retry, replay, and load controls.** Prerequisites: P3.02, P3.05, P3.06. Suggested owner: Engineering. Findings: F01, F02, F03, F06.

Use small batches, partial batch failures, visibility settings, queue retention, DLQs, and exponential backoff with jitter. Bound model attempts, concurrency, queue age, and per-incident scan/token budgets. Add inspected replay with audit records; replay reuses event identity.

Acceptance: Poison events reach recovery storage; valid adjacent work progresses; replay avoids repeating completed model work; alarm bursts cannot starve initial notifications or consume unlimited model budget.

**P3.08 — Prove durable flow under failure.** Prerequisites: P3.01, P3.02, P3.03, P3.04, P3.05, P3.06, P3.07. Suggested owner: Engineering + Operations. Findings: F01, F02, F03, F06, F13.

Exercise a failure matrix at every handoff: accepted event, conditional claim, state/outbox commit, enqueue, model completion, evidence write, publication, and acknowledgement. Include lost stream processing and late worker completion.

Acceptance: Every injected accepted incident is terminal or visibly recoverable with an owner; tests show no unexplained missing record or concurrent valid lease.


**Phase 4: Detection coverage and operational visibility.** Measure service availability, telemetry health, and the entire incident path. Suggested effort: 2–3 days. Gate G4: Service and telemetry failures are detected; an independent canary proves pipeline failures are visible.

**Phase 4 implementation checkpoint (6 October 2026).** The user authorized this phase. Repository implementation and local checks pass; P4.01–P4.06 remain VERIFYING and G4 NOT_RUN pending customer staging faults, exact telemetry and real primary/fallback receipts plus a second-operator rehearsal. Prior gates and all findings remain open. See [Phase 4 records](docs/implementation/phase-4/NOTES.md); no Phase 5 advancement is implied.

**Cross-phase review (6 October 2026).** The subsequent user-requested review
reproduced eight additional OPEN gaps, despite all 349 existing tests passing.
See the [review and corrective batches](docs/implementation/review-phases-1-4/REVIEW.md)
and [Floci compatibility proposal](docs/implementation/review-phases-1-4/FLOCI.md).
Repair release verification/bootstrap, recovery/stream/notification behavior and
observer/receipt/remote visibility under the existing tasks before relying on
their acceptance. The user subsequently authorized continuation; corrective
batches A–C now have local implementation and regression evidence, with R01–R08
VERIFYING pending live acceptance. R01 originally overstated full promotion scope;
its actual gap was standalone verification and exact role binding. See the
[corrective checkpoint](docs/implementation/review-phases-1-4/CORRECTIONS.md).
Emulator integration remains proposed and deferred. Phase 5 was authorized on 7 October 2026; P5.01 is IN_PROGRESS. Prior live acceptance gates remain pending.

**P4.01 — Add availability and dependency probes.** Prerequisites: P0.02, P2.05, P3.04. Suggested owner: Engineering + Operations. Findings: F05.

Define externally observed HTTP/service checks for critical routes and essential dependencies, response-time thresholds, and recovery signals. Cover services with little traffic and failures that leave the instance running; keep probes outside the failing process.

Acceptance: A stopped listener, hung endpoint, stopped Nginx, and unhealthy dependency trigger an initial alert; recovery is observable and linked to the incident.

**P4.02 — Detect stale or absent telemetry.** Prerequisites: P0.02, P2.06. Suggested owner: Engineering. Findings: F05, F17.

Add collector heartbeat and metric/log freshness signals with maintenance-aware expectations. Distinguish no traffic from a missing collector; define per-metric missing-data behavior rather than making all absence healthy.

Acceptance: Stopping CWAgent or log shipping produces a telemetry alert; an idle healthy service does not become an asserted application hang.

**P4.03 — Validate complete alarm-to-evidence coverage.** Prerequisites: P1.05, P2.05, P4.01, P4.02. Suggested owner: Engineering. Findings: F05, F09, F12, F17.

Map every alarm to its actual metric/log/health descriptor. Decide explicitly on 500/503 coverage, request versus log-event counting, process dimensions, disk paths, and autoscaled inventory refresh. Validate timestamps and field extraction against real sanitized Nginx data.

Acceptance: The coverage manifest contains all mandatory services and alarm evidence; each alarm is exercised and any duplicate Nginx counting is removed or explicitly represented.

**P4.04 — Add structured telemetry and dashboards.** Prerequisites: P3.08. Suggested owner: Engineering. Findings: F06, F19.

Emit correlation IDs and outcome metrics for ingestion, deduplication, queue delay, attempts, tool failure/no-data, deadline exhaustion, model usage, report persistence, notification acceptance, and delivery checks. Add component/error/backlog dashboards and configured log retention without raw secret logging.

Acceptance: An operator can trace an incident across stages and distinguish model failure, tool failure, queue delay, and notification failure.

**P4.05 — Add independent canary and escalation.** Prerequisites: P3.04, P4.04, P0.04. Suggested owner: Operations + Engineering. Findings: F06.

Create a scheduled synthetic incident with an expected record and notification receipt. Verify actual recipient delivery through an instrumented test destination and separate periodic real-channel checks. Alarm on missed canaries, DLQ growth, queue age, drops, stale outbox work, and denied deliveries using a separately monitored route.

Acceptance: Disabling the primary notifier or subscription is detected by the independent route; SNS publish acceptance alone does not count as delivered email.

**P4.06 — Write operating and recovery runbooks.** Prerequisites: P2.06, P3.07, P4.03, P4.05. Suggested owner: Operations. Findings: F02, F05, F06, F09, F11.

Document triage, backlog replay, broken collector, model outage, recipient changes, cost emergency, credential rotation, maintenance suppression, and recovery handling. Name an owner for every alarm and recovery queue.

Acceptance: An operator other than the implementer follows the runbooks successfully in staging; escalation ownership and safe replay boundaries are explicit.


**Phase 5: Identity, evidence safety, and diagnostic quality.** Protect production data before broad access or real-data evaluation. Suggested effort: 3–4 days. Gate G5: Identity, scope, redaction, retention, and diagnosis-quality evaluations meet recorded acceptance requirements.

**P5.01 — Integrate individual identity and session controls.** Prerequisites: P0.04, P2.02, P1.08. Suggested owner: Engineering. Findings: F07.

Integrate the chosen SSO/OIDC or authenticated access gateway; enforce identity on every entry path and prevent direct-origin bypass. Add authorization roles, idle/absolute expiry, logout, and revocation; require organization MFA policy.

Acceptance: Unauthenticated, expired, revoked, and unauthorized users cannot invoke tools or fetch reports; user identity appears in audit records.

**P5.01 checkpoint (7 October 2026).** Individual session controls and optional deployment wiring are implemented locally: encrypted store/generated secret, pinned version IAM, scoped issuer/UI/runtime roles, reviewed grant changes, rollback key labels and a native staging-ticket canary path. 522 tests, 82 templates, 13 package pairs/imports and eight synthetic releases pass. P5.01 remains IN_PROGRESS pending actual customer IdP/MFA/origin/IAM qualification; P5.02–P5.06 NOT_STARTED. See [setup and pending gates](docs/implementation/phase-5/SETUP.md). No project AWS resources or paid invocations.

**P5.02 — Enforce per-user access and work budgets.** Prerequisites: P5.01, P3.07. Suggested owner: Engineering. Findings: F07, F08.

Enforce service/environment allowlists in the backend, not the prompt or frontend. Add distributed login/investigation limits and bounded chat work with separate capacity from automatic incidents. Record actor, purpose, and accessed scope.

Acceptance: Manipulated prompts, requests, and report IDs cannot cross authorized scope; one chat user cannot exhaust the incident worker or model budget.

**P5.03 — Redact and govern evidence end to end.** Prerequisites: P2.02, P3.06. Suggested owner: Engineering + Operations. Findings: F08, F19.

Apply approved secret/PII redaction before model input and before report/log storage or delivery. Enforce storage encryption, TTL/lifecycle, access auditing, deletion policy, and authenticated report retrieval. Keep URLs/headers/log-derived data untrusted.

Acceptance: Sensitive fixtures do not appear in model requests, emails, operational logs, or unauthorized reports; retention and restore/deletion behavior are exercised.

**P5.04 — Strengthen evidence and uncertainty rules.** Prerequisites: P4.02, P4.03, P5.03. Suggested owner: Engineering. Findings: F08, F17.

Revise agent/tool descriptions to treat logs as data and distinguish facts, hypotheses, confidence, limitations, and human-reviewed fixes. Require source/time references and corroboration for a hang; implement deterministic output validation and budget guards where feasible.

Acceptance: No-traffic, collector failure, dropped logs, and genuine hangs produce differentiated findings; unsupported causal claims are flagged rather than accepted as evidence.

**P5.05 — Build model/security evaluation fixtures.** Prerequisites: P5.02, P5.03, P5.04. Suggested owner: Engineering. Findings: F08, F17.

Create sanitized cases for prompt injection, secret-bearing logs, fabricated directives, cross-service access attempts, contradictory evidence, known incidents, and insufficient data. Run deterministic control tests plus repeated model evaluations with recorded model/prompt versions.

Acceptance: The approved fixture set passes access/redaction controls and a reviewed diagnosis-quality threshold; probabilistic model tests are not presented as proof that injection is impossible.

**P5.06 — Complete identity and security operations.** Prerequisites: P5.01, P5.02, P5.03, P5.05. Suggested owner: Operations + Engineering. Findings: F07, F08, F11, F18.

Exercise credential rotation/revocation and recipient removal; remove stale access; review dependency/secret scan results and IAM boundaries. Record data classification, access review cadence, incident ownership, and any accepted residual risk with expiry.

Acceptance: There are no unowned security findings; former users and recipients lose access; critical security controls have test evidence.


**Phase 6: Integration, capacity, and release qualification.** Qualify a frozen candidate using real staging integrations and rehearsed recovery. Suggested effort: 2–3 days plus 3–7 calendar days observation. Gate G6: Frozen staging candidate passes integration, failure, capacity, rollback, observation, and finding-closure review.

**P6.01 — Run the real AWS integration suite.** Prerequisites: P1.02, P2.04, P3.08, P4.03, P5.06. Suggested owner: Engineering. Findings: F04, F06, F09, F12, F20.

Freeze a candidate manifest and test actual Bedrock/model availability, qualified tool invocation, IAM conditions, regional paths, SNS/EventBridge delivery, metric filters, and confirmed notification destinations. Use synthetic/sanitized evidence only until data controls pass.

Acceptance: Each supported event and tool contract works with the actual deployed identities; current AWS limits and integrations are verified rather than inferred from mocks.

**P6.02 — Inject failures and reconcile accepted events.** Prerequisites: P6.01, P4.05. Suggested owner: Engineering + Operations. Findings: F01, F02, F03, F05, F06.

Run worker hard-kill, blocked-stream, throttling, API denial, queue expiry, stream-dispatch outage, duplicate/reordered events, partial batch failure, bad payload, storage failure, and notifier failure scenarios. Reconcile source events to terminal/recovery records.

Acceptance: Every accepted test event is accounted for; overdue events escalate; retry and replay retain identity and evidence; no stale worker overwrites a newer attempt.

**P6.03 — Measure load, latency, and cost.** Prerequisites: P6.01, P0.03. Suggested owner: Engineering. Findings: F01, F03, F06, F07.

Run the recorded steady/burst profile plus concurrent chat, measure queue delay and p95/p99 processing/notification latency, and estimate measured cost per incident and peak-day spend. Tune concurrency and budgets within verified quotas.

Acceptance: Agreed targets hold at the agreed volume; initial notifications remain responsive; saturation causes visible degradation and bounded spending rather than silent loss.

**P6.04 — Rehearse promotion and rollback.** Prerequisites: P6.01, P2.06. Suggested owner: Engineering + Operations. Findings: F04, F10, F11.

Promote a candidate and then roll back tools, agent routing, configuration, and schemas as one compatible release. Interrupt deployment mid-step, test stale permissions, and confirm additive data/schema compatibility and retained evidence.

Acceptance: The prior release is restored within the agreed recovery target without dropping accepted incidents or deleting retained state; draft updates do not change the active release.

**P6.05 — Complete the staging observation period.** Prerequisites: P6.02, P6.03, P6.04. Suggested owner: Operations. Findings: F05, F06, F17, F19.

Observe the frozen candidate for 3–7 calendar days with scheduled canaries, recovery drills, queue reconciliation, and false-positive/diagnosis review. Record an evidence report; material fixes require targeted requalification and a justified observation reset.

Acceptance: No unexplained missing incident, sustained backlog, or missed canary remains; the last stable candidate has sufficient representative evidence.

**P6.06 — Close findings and assemble release evidence.** Prerequisites: P6.05. Suggested owner: Engineering + Operations. Findings: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20.

Attach evidence per finding, exact release hashes, test/scan/evaluation outcomes, dashboard links, service coverage, capacity results, rollback results, runbooks, and residual-risk decisions. Check every release gate below.

Acceptance: All P1 findings are verified closed; P2 findings are closed or have explicit time-limited owner acceptance and compensating controls; release decision is recorded against one candidate.


**Phase 7: Controlled production rollout and handover.** Use the qualified release, verify real production coverage, and hand over operations. Suggested effort: 1–2 days plus rollout observation. Gate G7: Production fleet coverage and delivery verified, migration complete, and operational ownership accepted.

**P7.01 — Prepare the cutover and decision record.** Prerequisites: P6.06. Suggested owner: Operations + Engineering. Findings: F04, F10, F11.

Choose a low-risk pilot service, change window, on-call owner, active/previous manifests, abort thresholds, source-routing change, and rollback commands. Confirm production recipients and account identity. Present the exact production change for the release decision.

Acceptance: The candidate is qualified and the production release decision names the exact account, scope, version, migration actions, and recovery owner.

**P7.02 — Run a shadow production pilot.** Prerequisites: P7.01. Suggested owner: Operations + Engineering. Findings: F05, F06, F08.

Process copied pilot events under production access controls with human-facing duplicate notifications suppressed. Preserve the existing alert route. Compare coverage, incident correlation, redaction, outcomes, latency, and cost.

Acceptance: Pilot output agrees with source events; no data exposure, unexplained event loss, or unacceptable load/cost is observed.

**P7.03 — Cut over the pilot without dual notifications.** Prerequisites: P7.02. Suggested owner: Operations + Engineering. Findings: F02, F03, F04.

Switch ownership of pilot notifications using a recorded routing/version transition; retain idempotency across the overlap and drain old accepted work. Trigger a controlled synthetic incident and recovery.

Acceptance: Initial and follow-up production delivery are verified; overlapping consumers do not create uncontrolled duplicate reports; rollback remains immediately available.

**P7.04 — Expand to the remaining service inventory.** Prerequisites: P7.03. Suggested owner: Operations. Findings: F05, F09, F10.

Roll out by service group, verify coverage and actual notification delivery after each group, and stop on abort thresholds. Compare the deployed inventory with the approved inventory before declaring full coverage.

Acceptance: Every approved service is monitored, owns valid evidence sources, and has verified notification routing; each rollout group has an evidence entry.

**P7.05 — Retire legacy resources safely.** Prerequisites: P7.04. Suggested owner: Operations + Engineering. Findings: F04, F11.

After the observation and rollback window, drain old queues, preserve required evidence, remove only owned obsolete rules/alarms/functions/grants/subscribers, and document retained rollback artifacts. Do not delete queues with unexplained backlog.

Acceptance: No required alert route, accepted incident, evidence store, or unrelated resource is removed; legacy recipients and grants are retired.

**P7.06 — Complete handover and recurring ownership.** Prerequisites: P7.04, P7.05. Suggested owner: Operations. Findings: F06, F07, F18, F19.

Assign ownership for canaries, backlog/DLQs, access review, dependency upgrades, model/prompt evaluations, restore drills, and cost review. Set an operational review cadence and update user/setup documentation with actual measured limitations.

Acceptance: The tracker contains final evidence and owner acceptance; operators can triage, replay, rotate access, promote, and roll back using the delivered runbooks.

**Release validation matrix.** Attach CI artifacts for offline checks and sanitized event/execution/report IDs for live checks. Do not paste secrets or full production logs into the tracker.

| Check | Required scenario | Responsible task(s) | Passing evidence |
|---|---|---|---|
| V01 | Clean install/build, all original tests, scans | P1.01 | Runtime/lock/artifact hashes and CI result |
| V02 | Schema and handler contract, including invalid inputs | P1.02, P6.01 | Schema validation plus live tool invocation |
| V03 | Minimal/invalid config and wrong account | P1.03, P2.05 | Fail-before-write evidence |
| V04 | UTC offsets, malformed times, source/receive time | P1.04 | Equivalent windows and explicit uncertainty |
| V05 | Dimensionless Nginx and exact metric dimensions | P1.05, P4.03 | Matching published and queried descriptors |
| V06 | >250 groups and oversized/multibyte responses | P1.06, P1.07 | Completeness markers and byte measurements |
| V07 | Duplicate/reordered events and concurrent workers | P3.02, P3.08 | Single valid lease, stable incident IDs, fenced stale writes |
| V08 | Database/queue handoff failure and missed streams | P3.03, P3.08 | Pending work recovered from durable intents |
| V09 | Silent model stream, hard worker kill, SDK retry exhaustion | P3.05, P6.02 | Durable degraded state and independent follow-up |
| V10 | SNS denial, timeout, ambiguous acknowledgement | P3.04, P3.06 | Retry state and stable report IDs; no repeated completed analysis |
| V11 | Poison message, expiry, queue/DLQ replay | P3.07, P6.02 | Accounting reconciliation and bounded retries |
| V12 | Failed listener/Nginx/dependency and collector outage | P4.01, P4.02 | Distinct service/telemetry alarms and verified recovery |
| V13 | Missing metric, bad filter, failed target registration | P2.05, P4.03 | Deployment gate fails with an actionable cause |
| V14 | Disabled notifier or unconfirmed/removed recipient | P4.05, P5.06 | Canary/fallback detects it; retired recipient stops receiving |
| V15 | Unauthenticated/expired/revoked identity and scope bypass | P5.01, P5.02 | Backend denials and attributed audit events |
| V16 | Secrets, hostile logs, no-traffic versus hang | P5.03, P5.04, P5.05 | Redaction/access tests and reviewed model evaluations |
| V17 | Full traffic/burst plus simultaneous chat | P6.03 | Latency, backlog, quota, cost and degradation measurements |
| V18 | Candidate deploy, interruption, rollback, retirement | P6.04, P7.05 | Active release unchanged until promotion; compatible rollback |

**Change and rollout safeguards.** Implement changes in reviewable increments. Every candidate manifest records code, tools, schema, prompt, model, configuration, regional stack outputs, and test versions. Use additive data migrations and maintain compatibility with the immediately previous release; do not assume reverting code reverts stored data. If a legacy resource cannot be imported safely, create a parallel owned replacement and switch routing through the pilot. Keep current operational alerting active until the new route is verified; define one owner of human-facing notifications during overlap. Pause expansion and invoke the recorded rollback if accepted incidents cannot be accounted for, initial-alert latency repeatedly breaches target, access/redaction fails, DLQs grow without recovery, or model/query costs exceed the agreed limit. Preserve queues and evidence during rollback. Record exact numerical abort thresholds in P7.01 from the measured baseline.

**Definition of production completion.** All P1 audit findings must be verified closed. P2 findings must be closed or carry an explicit time-limited acceptance with owner, compensating control, and follow-up date. Every required service must appear in the deployed coverage manifest. The release must have measured staging/production delivery, capacity and cost evidence, a tested rollback, recoverable accepted incidents, and named operational ownership. A merged PR, passing unit tests, empty error dashboard, or successful SNS publish alone does not satisfy completion.
