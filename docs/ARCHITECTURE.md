# Architecture and workflows

Kira is customer-operated software. The web UI runs on a customer workstation or
customer-managed HTTPS host. Backend processing runs in the customer's AWS account.
No maintainer account, control plane or managed database is required.

## Components and storage

| Component | Responsibility |
| --- | --- |
| Streamlit UI | Native OIDC login, scoped chat, incident status and report access |
| Session issuer and qualified chat gateway | Release-bound identity, audit and distributed work allowances |
| Shared Python runtime | Bedrock token counting/Converse, bounded read-only tools, redaction and structured diagnosis |
| Standalone Lambda or AgentCore hosts | Separate incident/chat execution with pinned versions and policies |
| SNS, SQS and durable pipeline | Accepted-event capture, dispatch, independent notifications and fenced workers |
| DynamoDB incident ledger/outbox | Dedupe, transitions, leases, budgets, delivery intents and recovery accounting |
| Separate DynamoDB identity storage | Grants, epochs, sessions, audit and distributed allowances |
| Private versioned S3 and KMS | Redacted checkpoints/reports, artifacts and retained audit objects |
| Secrets Manager | Independent cursor and session signing secrets pinned to exact versions |
| CloudWatch, schedules and optional observers | Telemetry, health/freshness, queue/delivery monitoring and notification canaries |

There is no local SQL database to install. AWS storage is provisioned by the
deployment templates. DynamoDB TTL and S3 lifecycle are asynchronous cleanup;
application checks deny expired or erased evidence independently.

## Administrator onboarding

1. Establish scoped AWS identities, model access, regions, quotas and budget.
2. Identify existing workloads and install/configure telemetry and heartbeat.
3. Register OIDC/MFA, exact callback/origin, authorized users and notification recipients.
4. Generate private settings, review the offline plan and run read-only preflight.
5. Apply from clean committed source. The CLI builds inventory-bound packages,
   provisions foundations, pins storage/secret versions and seals candidates.
6. Configure native UI login and a release-bound investigator grant. Obtain a
   private staging ticket and explicitly authorize the paid bounded canary.
7. Resume reviewed routing, confirm subscriptions and prove actual primary/fallback
   inbox delivery. Configure the operational UI role and connection references.
8. Complete staging/load/security/recovery acceptance and a reviewed production
   cutover. Provisioning alone leaves investigations paused.

Use the [administrator checklist](ADMINISTRATOR_SETUP_CHECKLIST.md) and
[automation guide](DEPLOYMENT_AUTOMATION.md) for exact commands and human dependencies.

## Chat workflow

1. Native OIDC authenticates the browser user; the UI workload separately assumes
   its scoped AWS role. A browser login does not grant direct AWS resource access.
2. The issuer checks recent MFA and the immutable subject's enabled grant,
   instance scope, role, epoch and release binding, then retains an audited session.
3. An investigator selects an authorized instance. The qualified chat gateway
   validates session/scope, reserves distributed allowances and invokes the runtime.
4. The runtime counts the exact model request before inference. Each handoff checks
   deadline, token/tool/query budgets and permitted instance/time window.
5. Pinned tools discover and retrieve bounded CloudWatch evidence. Redaction runs
   before subsequent model requests and persisted/delivered output.
6. Structured diagnosis validates citations, correlation and uncertainty. The UI
   displays the qualified answer; viewer grants do not authorize investigation.

## Automatic incident workflow

1. A configured alarm/event reaches SNS and the ingress queue. Ingestion checks
   source, account, instance and transition, deduplicates and accepts a durable event.
2. The ledger/outbox records independent initial notification and investigation
   intents. Dispatch can retry accepted intents without losing their identities.
3. The notifier sends the initial alert without waiting for Bedrock. A fenced
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

See [operations](OPERATIONS.md), [identity](IDENTITY.md) and
[security operations](SECURITY_OPERATIONS.md) for recovery and data boundaries.
