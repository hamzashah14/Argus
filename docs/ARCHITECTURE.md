# Architecture and workflows

Kira is customer-operated software. The web UI runs on a customer workstation or
customer-managed HTTPS host. Backend processing runs in the customer's AWS account.
No maintainer account, control plane or managed database is required.
Unfamiliar terms are defined in the [glossary](#glossary).

Three choices shape a deployment, and each is made when you deploy:

- **Sign-in.** The default is local single-user mode with one shared UI password. The
  optional identity module adds OIDC with MFA, grants, sessions, audit, per-user and
  shared quotas and a dedicated chat gateway. It is enabled by an `identity` block in
  `runtime.json` (`init --identity`), which sets `KIRA_AUTH_MODE=oidc` for the UI and
  runtime.
- **Model provider.** Amazon Bedrock is the default. A Model API (OpenAI-compatible
  or Anthropic Messages) is the alternative, for the standalone target only.
- **Runtime target.** Standalone Lambda is the default. AgentCore is Bedrock only.

## Components and storage

| Component | Responsibility |
| --- | --- |
| Streamlit UI | Shared-password sign-in by default (native OIDC login with the optional identity module), chat, incident status and report access |
| Session issuer and qualified chat gateway (optional identity module) | Release-bound identity, audit and distributed work allowances |
| Shared Python runtime | Token counting and inference through a model provider (Bedrock `CountTokens`/`Converse`, or the Model API adapter in `kira/model_api.py` selected by the `MODEL_API` setting), bounded read-only tools, redaction and structured diagnosis |
| Standalone Lambda or AgentCore hosts | Incident execution with pinned versions and policies. Dedicated chat hosts exist only with the identity module. By default chat runs in the UI process (standalone) or in the same AgentCore runtime as incidents. AgentCore is Bedrock only |
| SNS, SQS and durable pipeline | Accepted-event capture, dispatch, independent notifications and fenced workers |
| DynamoDB incident ledger/outbox | Dedupe, transitions, leases, budgets, delivery intents and recovery accounting |
| Separate DynamoDB identity storage (optional identity module) | Grants, epochs, sessions, audit and distributed allowances |
| Private versioned S3 and KMS | Redacted checkpoints/reports, artifacts and retained audit objects |
| Secrets Manager | Independent log cursor secret, plus the session signing secret (identity module) and the Model API key (Model API provider, created by you), each pinned to an exact version |
| CloudWatch, schedules and optional observers | Telemetry, health/freshness, queue/delivery monitoring and notification canaries |

There is no local SQL database to install. AWS storage is provisioned by the
deployment templates. DynamoDB TTL and S3 lifecycle are asynchronous cleanup;
application checks deny expired or erased evidence independently.

## Administrator onboarding

1. Establish scoped AWS identities, model access (Bedrock, or a Model API account and
   key), regions, quotas and budget.
2. Identify existing workloads and install/configure telemetry and heartbeat.
3. Register notification recipients. With the optional identity module, also register
   OIDC/MFA, the exact callback/origin and authorized users. With a Model API, create
   the key secret in Secrets Manager yourself.
4. Generate private settings, review the offline plan and run read-only preflight.
5. Apply from clean committed source. The CLI builds inventory-bound packages,
   provisions foundations, pins storage/secret versions and seals candidates.
6. Explicitly authorize the paid bounded canary. With the identity module, first
   configure native UI login and a release-bound investigator grant and obtain a
   private staging ticket.
7. Resume reviewed routing, confirm subscriptions and prove actual primary/fallback
   inbox delivery. Configure the operational UI role and connection references. In the
   default mode, export `APP_PASSWORD` in the shell that launches the UI.
8. Complete staging/load/security/recovery acceptance and a reviewed production
   cutover. Provisioning alone leaves investigations paused.

Use the [deployment guide](DEPLOY.md) for exact commands and human dependencies,
and [server setup](SERVERS.md) for telemetry and the heartbeat.

## Chat workflow

**Default (local single-user mode).** Chat has no gateway. There is no per-person
identity, shared spend cap or dedicated chat capacity.

1. The browser user signs in with the shared password. The session ends after 30 minutes.
2. The UI process checks the prompt and a throttle of 20 requests per hour, kept per
   browser session only.
3. With the standalone target, the UI process runs the shared runtime itself. With
   AgentCore, the UI role invokes the AgentCore runtime that also investigates
   incidents. Either way it uses the UI role's AWS credentials, the instance
   allowlist, bounded runtime limits and the release binding.

**With the optional identity module.**

1. Native OIDC authenticates the browser user; the UI workload separately assumes
   its scoped AWS role. A browser login does not grant direct AWS resource access.
2. The issuer checks recent MFA and the immutable subject's enabled grant,
   instance scope, role, epoch and release binding, then retains an audited session.
3. An investigator selects an authorized instance. The qualified chat gateway
   validates session/scope, reserves distributed allowances and invokes the runtime.

**Both modes continue here.**

4. The runtime counts the model request before inference (with a Model API, see
   [Model provider seam](#model-provider-seam)). Each handoff checks deadline,
   token/tool/query budgets and permitted instance/time window.
5. Pinned tools discover and retrieve bounded CloudWatch evidence. Redaction runs
   before subsequent model requests and persisted/delivered output.
6. Structured diagnosis validates citations, correlation and uncertainty. The UI
   displays the qualified answer. With the identity module, viewer grants do not
   authorize investigation.

### Model provider seam

`kira/runtime.py` drives any client that offers Bedrock's `count_tokens` and
`converse` calls. Bedrock needs no adapter. For a Model API, `kira/model_api.py`
offers the same two calls over HTTPS and answers in the same shapes, so budgets,
content rules and tool handling do not change. The runtime setting `MODEL_API`
selects it, and an unset value selects Bedrock. The adapter reads the API key from a
pinned Secrets Manager version, uses https only, follows no redirects, never retries a
billable request (the durable worker retries instead) and caps each HTTP call at
24 seconds. Incident investigations use the same seam.

The Anthropic protocol asks the provider's own count endpoint, which Anthropic
documents as an estimate, and checks the billed input after the call. The OpenAI
protocol has no count endpoint, so Kira reserves a local estimate: UTF-8 bytes divided
by `bytes_per_token` (default 3) plus 64. That estimate is not an upper bound. If the
provider later reports more input tokens than reserved, or no usage, the run stops
with `TOKEN_ACCOUNTING_MISMATCH`, after that call has already been made.

AgentCore is Bedrock only. A Model API with AgentCore is rejected in configuration
validation, release rendering, `plan()` and the AgentCore host's startup.

## Automatic incident workflow

1. A configured alarm/event reaches SNS and the ingress queue. Ingestion checks
   source, account, instance and transition, deduplicates and accepts a durable event.
2. The ledger/outbox records independent initial notification and investigation
   intents. Dispatch can retry accepted intents without losing their identities.
3. The notifier sends the initial alert without waiting for the model. A fenced
   worker acquires the investigation lease and reserves conservative allowances.
4. The selected runtime gathers evidence under the pinned policy/release. Timeouts
   and ambiguous upstream calls do not refund reservations or start a second target.
5. The worker persists private versioned evidence and a completed/degraded outcome.
   A separate durable notification intent delivers the follow-up report link.
6. Independent reconciliation recovers due intents and expired leases within
   attempt/aggregate limits. Optional observers check health, collector freshness,
   backlogs and synthetic delivery; actual mailbox acceptance remains a human check.
7. Authorized users open incident links through the UI. Recovery observations can
   link to prior incidents; they do not cancel running work or remediate workloads.

See [operations](OPERATE.md) for recovery and data boundaries, the
[deployment guide](DEPLOY.md) for the optional identity setup and the
[live acceptance checklist](ACCEPTANCE.md) for what to prove before relying on a deployment.

## Glossary

- **Allowance (quota) (identity module only):** A limit on logins, chat requests and reserved model tokens, per user and shared by everyone, counted per UTC hour. It is charged before work starts and is never refunded, even if the request fails. You choose the numbers in `runtime.json`.
- **Canary:** A deliberate test run with a known input. The staging canary is one paid chat request through the candidate chat function (the candidate investigation function in the default mode), run before promotion. A notification canary is a synthetic alarm that an optional observer sends through the alert path on a schedule, to check that the alert and its receipt still arrive.
- **Change set:** CloudFormation's preview of what a stack update would do. The deployment tooling creates one named `review-` plus the start of the review hash, checks it against the rendered template, and only then runs it. Deletions, replacements and drift stop the automation.
- **DLQ (dead-letter queue):** A queue that holds messages that could not be delivered or processed. The pipeline queues move a message there after five failed receives. Alarms watch these queues; inspect messages before deleting anything.
- **Epoch (identity module only):** A counter on each user grant. Every change to a grant, including revoking it with `enabled: false`, adds one. A session carries the epoch it was issued under and stops working when the stored epoch differs.
- **Grant (identity module only):** The record that lets one person use Kira. It is keyed by the identity provider's issuer and immutable subject (not an email address) and holds a role (`viewer` or `investigator`), the instances they are scoped to, an enabled flag, an epoch and a release binding. Viewers read reports; investigators can also start chat investigations.
- **Identity module (OIDC module):** The optional part of Kira that adds individual sign-in. It brings OIDC with MFA, grants, epochs, sessions, an audit trail, per-user and shared allowances, the qualified chat gateway, access review and erasure of identity data. You enable it with an `identity` block in `runtime.json`, for example by running `init --identity`. Without it Kira runs in local single-user mode.
- **Ledger:** The DynamoDB table that records each accepted event, its incident and the work still owed, written with conditional updates so duplicates are rejected. It also holds leases, budgets and recovery accounting.
- **Lease and fence:** A worker claims an incident by taking a time-limited lease (owner and expiry) in the ledger. Each claim increments a fencing token, and every later write must present the current token, so a slow worker whose lease expired cannot overwrite the newer attempt.
- **Local single-user mode:** The default. One shared password (`APP_PASSWORD`, at least 12 characters) protects the web UI, and chat runs without a gateway using the UI role's AWS credentials. There are no grants, sessions, per-person quotas or identity tables. The throttle of 20 requests per hour is kept per browser session.
- **Model API provider:** An alternative to Bedrock for the standalone target. It is an OpenAI-compatible Chat Completions endpoint with tool calling, or the Anthropic Messages API, set by `model_provider` and `model_api` in `deployment.json`. Its API key lives in a Secrets Manager secret that you create, and each release pins one version of it. Redacted excerpts leave your AWS account for that provider.
- **Outbox and intent:** An intent is a ledger row saying that something still has to happen, such as the initial notification, an investigation or the follow-up. Intents start as `PENDING` and become `SENT` once queued. The message is queued first, so a crash can cause a duplicate but never a lost intent. The set of pending intents is the outbox.
- **Plan hash and review hash:** The plan hash is a SHA-256 digest of the `dry-run` plan, and `apply` refuses to run without it. The review hash is the digest of a rendered release bundle (source, settings, templates and bindings); operator commands refuse a bundle that does not match it.
- **Qualified chat gateway (identity module only):** The dedicated chat function the UI calls when the identity module is enabled. "Qualified" means an exact numbered Lambda version in your account and region (not `$LATEST`) that was created and sealed as part of the release. It validates the session and scope, reserves allowances and runs the runtime. The UI role may invoke only this version.
- **Release binding (bindings):** The environment, account ID and release fingerprint. Every chat request must carry the running release's fingerprint. With the identity module they are also stored with each grant and session, which only work with the release they were issued for, so a new release needs reviewed grant rebinding. In the deployment tooling, `bindings` also means the recorded outputs (table names, secret and function versions) that a release is pinned to.
- **RuntimeConnection:** A CloudFormation output of the reviewed routing stack. It is JSON with the settings the UI needs (region, model, account, release fingerprint, limits, function or runtime ARNs, work policy, and the `MODEL_API` setting if you use one). It holds references, never secrets. `apply` copies it into `ui-connection.json`.
- **Sealed (seal):** After a release stack is created, the tooling attaches a stack policy that denies every update to it. A sealed release cannot be edited in place; changes need a new release ID.
- **Standalone vs AgentCore:** The two runtime targets, set by `runtime_target`. `standalone` runs investigations and chat in AWS Lambda. `agentcore` runs them in separate Amazon Bedrock AgentCore incident and chat runtimes with their own endpoints. Both use the same Python orchestration and read-only tools. AgentCore supports Bedrock only.
- **Tombstone and erasure:** Erasure removes an incident's report content and every stored version after a reviewed plan, and leaves a minimal tombstone (incident and event IDs, fence, review reference, no report content). The tombstone stops a replayed event from bringing the incident back. A revoked grant is likewise kept, disabled, so it cannot be recreated at epoch 1.
