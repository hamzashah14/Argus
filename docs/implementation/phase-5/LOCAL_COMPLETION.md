# Phase 5 local completion

7 October 2026. Code checkpoint `4d03640`, branch
`codex/phase-5-identity-evidence`. P5.01–P5.06 are **VERIFYING: local implementation complete**.
G5 remains **NOT_RUN**. The user explicitly deferred live verification. Earlier
AWS/hosted-CI gates, all 20 original findings and R01–R08 remain open/verifying.
No Phase 6 work, AWS deployment, paid model run, notification or Floci validation
is implied. Customers own infrastructure, identities, credentials and operations.

## Task-to-implementation record

| Task | Implemented locally | Required live/customer acceptance |
| --- | --- | --- |
| P5.01 | Native OIDC/MFA claim checks; authoritative grants/sessions; role/scope/expiry/revocation; pinned signing version; separate issuer/UI/runtime IAM; private staging-ticket workflow | Actual provider, callback/origin, browser protections, resource policies and IAM denials |
| P5.02 | Atomic per-actor/shared login/chat admission; reserved token allowance; bounded work; independent chat Lambda and optional independent AgentCore host; purpose isolation; pseudonymous audit | Real concurrency/contention/throttling, regional quotas, model capability and account budget |
| P5.03 | Redaction before model/tool/checkpoint/report/delivery boundaries; scoped authenticated report reads; encrypted retained storage; TTL/lifecycle; retained access audit and scoped CloudTrail; reviewed terminal-incident erasure | Customer classification/profile approval; actual delivery of access records; TTL/lifecycle, deletion and isolated backup restore |
| P5.04 | Versioned structured diagnosis; exact scalar/source/window citations; qualified evidence categories; strict corroboration for hang; uncertainty and human-reviewed advice; rejects unsupported diagnosis | Human review of real incidents and model-specific reliability |
| P5.05 | 16 versioned sanitized reference cases; adversarial control tests; CI offline evaluation; optional repeated paid synthetic-model runner with explicit total allowance and private validated reports | Selected model/prompt repeated runs, approved threshold and reviewed quality; not performed locally |
| P5.06 | Access-review CLI; conditional grant offboarding; rotation/rollback simulations; reviewed primary/fallback recipient retirement; security/restore/rotation runbooks; owned residual-risk register; dependency/secret/IAM checks | Customer names responsible operators, approves policies/expiry, rehearses actual rotation/offboarding and confirms recipient removal |

The engineering owner of every local task is Codex. Customer identity, security,
incident and cost owners are **pending assignment**, a deployment gate. Proposed
residuals are not accepted risks. See [security operations](SECURITY_OPERATIONS.md)
and [evaluation procedures](EVALUATIONS.md). Historical slices remain in
[NOTES](NOTES.md); authoritative validation counts are in
[local evidence](../evidence/phase-5/local-completion-validation.json).

## Runtime and capacity

The UI assumes the customer UI role and invokes only the exact qualified chat
Lambda. That worker shares verified Python code with automatic investigation but
has its own function, purpose, capacity and bounded request. In AgentCore mode it
invokes a separate chat Runtime/endpoint; automatic work retains a different host.
The UI receives no model, tool or AgentCore invocation grants. Automatic workers
reject chat envelopes and chat workers reject incident work. The chat runtime
cannot read/write automatic incident tables or reports; the UI report path keeps
its separately scoped read permission. Existing identity-free synthetic layouts
remain renderable; interactive staging/production access requires identity.

Default policy (`kira/work_policy.py`, also in the synthetic identity example):

| Allowance | Default |
| --- | --- |
| Successful login admission per UTC hour | 10/user, 100/deployment |
| Chat admission per UTC hour | 4/user, 8/deployment |
| Reserved chat tokens per UTC hour | 96,000/user, 192,000/deployment |
| One request | 24,000 reserved tokens, 6 model steps, 6 tool calls, 12 log queries, 1,024 output tokens/step |
| Request limits | 180 seconds, 48,000-byte model context, 20,000-byte tool response |
| Admission leases | One/user, two/deployment, 240-second expiry |
| Identity-enabled Lambda capacity | Chat reserved concurrency 1; investigation 2 |
| Retained application access records | 30 days (customer configurable, maximum 90) |

The complete request token allowance is charged **before** inference; partial,
failed or revoked requests do not refund it. A timed-out admission is not blindly
retried. Only a confirmed conditional transaction rejection may try the second
slot; transactions prevent partial counter updates. Leases recover independently
of asynchronous TTL cleanup. UTC hourly windows can permit a boundary burst;
this is not a sliding-window rate limit. Login quotas apply after verified claims
and grants, not to unauthenticated IdP/proxy traffic.

The Lambda capacity bound can be stricter than the two distributed leases and
there is no chat queue or automatic retry. Regional Lambda/Bedrock/AgentCore quotas
and model throughput remain shared customer dependencies. Chat isolation cannot
reserve provider-wide model throughput for automatic work; approve that capacity
and cost during live qualification. The prior account concurrency quota of 10
remains an unresolved AWS prerequisite. Policy changes alter the release binding
and require reviewed grant rebinding; never mutate a deployed policy in place.

## Evidence and diagnosis

`redaction-v1` bounds objects, depth and encoding and removes tested credential,
secret and PII patterns. Cursor continuation fields survive; session credentials
and secrets do not. Unvalidated model drafts are neither checkpoints nor final
reports. Public notifications remain metadata-only in the durable path; legacy
text delivery is also redacted. Pattern redaction is defense in depth and does
not certify arbitrary customer logs: approve the profile before real data use.

`diagnosis-v1` returns findings, facts, hypotheses, limitations and recommendations.
Facts cite exact scalar JSON pointers plus returned evidence IDs and observed
source/time windows. Confidence is low/medium; fixes require operator review.
Missing metrics are unknown. No-traffic needs complete access-log coverage and
fresh telemetry. Collector/transport failure describes failed freshness rather
than claiming a dead process. Hang correlation requires complete historical
application silence, fresh telemetry, access traffic and independent unhealthy
availability for the same instance, health service and overlapping window, with
actual corroborating samples inside the gap. A log gap alone, ingestion delay,
dropped logs, unrelated service or fabricated citation cannot satisfy that gate.
Contradiction requires conflicting samples of the same metric descriptor/time.
The validator checks evidence structure and qualification, not arbitrary prose
truth or a proven root cause.

Discovery exposes bounded, instance-scoped configured metric ID/name hints so the
model can request exact health series. Omitted hints explicitly mark incomplete
coverage. Metrics use the actual AWS-style dimensions array. Every evaluation
fixture is checked against the real tool-response schema. The default budget test
executes discovery plus four corroborating calls and a validated final turn.

## Deployment and manual work later

For a low-cost pilot, run the web UI locally. Cloud alerts/investigation/notification
workers run in the **customer's AWS account** even when that UI is closed.
Standalone is the default; AgentCore adds optional customer infrastructure. No
maintainer SaaS, control plane or mandatory UI server exists. A desktop application
is a later phase, not implemented by Phase 5.

Before cloud use the customer still supplies actual inventory/log collection,
regions/model access and budget; OIDC registration/MFA/callback/cookie/client
secrets; scoped workload/operator credentials; reviewed grants; confirmed primary
and fallback email recipients; responsible operators and retention/classification
policies. They review and execute generated change sets, verify live gates and
operate access reviews/rotations. Synthetic specs are undeployable references.
No project infrastructure or model/notification charges were created by this
local work. Local tests do not demonstrate a deployable account or production
readiness. Follow [setup](SETUP.md), not the legacy Agents Classic walkthrough.

## Pending acceptance matrix

| Gate | Status |
| --- | --- |
| Real OIDC/MFA/logout/origin, UI and issuer/runtime IAM denials | NOT_RUN |
| Actual atomic quotas, throttling and automatic/chat capacity under load | NOT_RUN |
| Selected Bedrock model and both actual runtime targets | NOT_RUN |
| Real sensitive-data profile/classification approval | CUSTOMER APPROVAL PENDING |
| CloudTrail/access record receipt, lifecycle/TTL and retained versions | NOT_RUN |
| Deletion, recovery from partial deletion and isolated backup restore | NOT_RUN |
| Key/client/cookie/cursor/workload credential rotation and rollback | NOT_RUN |
| Access owner attestation and primary/both fallback recipient removal | NOT_RUN |
| Repeated model quality evaluation and human-approved threshold | NOT_RUN / APPROVAL PENDING |
| Named operators, budget approval and residual-risk acceptance | CUSTOMER DECISION PENDING |
| Hosted CI, earlier phase live gates and G5 | PENDING / NOT_RUN |

Resume within Phase 5 for these gates only when the user authorizes live work.
Do not silently start Phase 6.
