# Live acceptance checklist

**The maintainers have never run these checks against real AWS.** Kira's automated tests use fakes. They say nothing
about your IAM, quotas, identity provider, email delivery or recovery. Treat every box below as unproven until you
tick it with evidence from your own staging deployment.

Before you start, freeze the source revision, bundle and review hash, inventory, model and model provider, runtime
target, sign-in mode, owners and budget. Run on staging with an approved, bounded budget, and keep investigations paused while you qualify
the release. The paid canary is staging only, and going to production is a separate reviewed procedure of your own.
Record UTC times, receipts and safe causes. Keep raw logs, cloud responses and contacts private. Qualify each runtime
target you offer (standalone or AgentCore) and each model provider (Bedrock or a Model API) separately. Linux collector
checks do not prove Windows telemetry. Sections marked "only with the OIDC module" or "only with a Model API" apply
only if you enabled that option.

## Telemetry

- [ ] **Outages are detected, bounded and mailed.** Stopping the app listener (EC2 still running), stopping Nginx, and
  breaking a critical dependency each raise an alarm and an incident, and the initial email reaches a real inbox within
  your target. A stalled response, trickling body, or DNS or TLS failure ends at the route timeout without hanging
  the observer.
  How: break each on a staging host (and point one route at a slow endpoint), then check the alarm, incident, probe
  code and inbox. Restore, and confirm the alarm returns to OK and the incident shows `recovered_at`.
- [ ] **Collector faults differ from app faults.** Stopping CWAgent, the heartbeat timer or log shipping each raises a
  telemetry alarm, never an invented application hang. An idle healthy service, log rotation and clock skew raise no
  false alarm.
  How: stop each in turn and compare alarm names, then leave a quiet service through a full freshness window.
- [ ] **Coverage is exact.** Every monitored instance, metric, dimension, disk path, process and owner matches your
  inventory. Real sanitized Nginx lines with 500, 502, 503 and 504 match, and a 200 does not. Replacing or scaling an
  instance needs a reviewed inventory refresh, so no member goes unobserved.
  How: compare the rendered `coverage.json` with your real hosts. The strict coverage check also runs inside the paid
  canary ([DEPLOY.md](DEPLOY.md)).

## Notification delivery

- [ ] **Primary inbox.** Initial and follow-up emails reach the real mailbox, and the incident link opens the UI
  behind its sign-in over HTTPS.
  How: receive the marked canary, then record it with `attest-email`
  ([OPERATE.md](OPERATE.md#respond-to-an-alert-or-incident)). An SNS acceptance or SQS receipt is not enough.
- [ ] **Fallback route.** With the primary notifier or its mapping disabled, the initial email goes missing but the
  independent CloudWatch fallback email still arrives. A fallback delivery fault reaches the primary route.
  How: disable them on staging and keep the fallback inbox receipt. A primary attestation never covers it.
- [ ] **Lost pieces are noticed.** Removing, un-confirming or filtering a subscriber, or disabling the canary sender,
  observer or receipt consumer, raises an alarm that reaches a working route. DLQ growth and queue age page the named
  owner, and recovery drops nothing.
  How: do each on staging and watch the observer outcome codes (for example `CANARY_RECEIPT_MISSED`,
  `PRIMARY_SUBSCRIPTION_MISSING`) and the alarms.
- [ ] **Recipient change.** The old address gets nothing new, the new one gets real mail, and an attestation for the old
  address does not count.
  How: follow [Change alert recipients](OPERATE.md#change-alert-recipients). The observer reports
  `EMAIL_RECEIPT_UNVERIFIED` until you attest the new address.

## Sign-in and access

- [ ] **Local single-user mode (default): exposure and scope.** A wrong password is refused. The UI is reachable only as
  you intend: on `127.0.0.1`, or behind your own SSO or VPN proxy, and never on the open internet by its raw port. A
  question about an instance outside `ALLOWED_INSTANCE_IDS` is refused. The UI role can do no more than read incident
  evidence and invoke the model and tools, or the AgentCore runtime (with a Model API, it can also read the pinned key
  version). Your security owner accepts in writing that anyone with the shared password can use the model and tools
  and read every incident report, and that the throttle of 20 requests per hour is per browser session only.
  How: try a wrong password, a second browser session and an unlisted instance. Probe the UI host from outside. Assume
  the UI role and call forbidden AWS APIs directly.
- [ ] **Local single-user mode (default): chat works from the UI.** The staging canary calls the candidate
  investigation function, not the UI's own path. A real chat question from the launched UI returns a validated answer
  using the UI role.
  How: launch the UI with `run_customer_ui.py` and `APP_PASSWORD` exported, ask about one listed instance, and check the
  logs and the provider or Bedrock usage.
- [ ] **Sign-in (only with the OIDC module).** Native OIDC with MFA works, including logout and fresh sign-in.
  Wrong-audience, expired and unregistered users are rejected. A viewer cannot act as an investigator, and
  cross-instance requests are denied.
  How: test one user per role plus one unregistered user, and check the access audit records.
- [ ] **Revocation and fail-closed (only with the OIDC module).** After `enabled: false` the user's next action is
  denied and old-release tickets fail. Storage or secret outages deny access. The UI, issuer and runtime roles cannot
  write grants, scan the grants table, read foreign secret versions or reach tools and evidence directly.
  How: revoke a test user ([OPERATE.md](OPERATE.md#access-review-grants-revocation-and-secret-rotation)) and retry.
  Assume each role and call the forbidden AWS APIs directly.
- [ ] **Edge (team-hosted UI only, either mode).** Host and Origin checks, direct-origin bypass, XSRF, WebSocket,
  cookies, header impersonation and unauthenticated public paths behave as intended.
  How: probe the public hostname and the raw backend origin from outside.

## Bounded investigation canary

- [ ] **Investigation works and fails safely.** One paid canary returns a final answer from successful logs and metrics
  calls. Model denial or outage, tool error, no data, deadline and report failure each leave distinct logs, metrics and
  a durable terminal or degraded status. One incident traces end to end with no raw secrets in logs, and CloudTrail
  and audit records actually arrive.
  How: run `verify-candidate`, then the paid canary ([DEPLOY.md](DEPLOY.md)). With the OIDC module the canary goes
  through the chat gateway with a staging ticket. Otherwise it calls the candidate investigation function. Inject each
  fault on staging and trace by `incident_id` and `fence`.

## Model API (only with a Model API)

The maintainers have never run the Model API option against a live provider. Prove every item below on staging.

- [ ] **The canary proves key, model and protocol.** The paid canary returns a final answer through the provider. That
  shows the pinned key version can be read, the provider accepts the model name and the protocol's tool calling works.
  A call that takes more than 24 seconds fails, so a normal answer must arrive inside that cap.
  How: run `verify-candidate` and the paid canary ([DEPLOY.md](DEPLOY.md)). Check the provider's usage log for the
  request.
- [ ] **Data egress is approved.** Your data owner approved in writing that redacted log and metric excerpts and chat
  questions leave your AWS account for the provider's endpoint, under the provider's retention, region and terms.
  Redaction is best effort.
  How: record the decision with the provider terms and the `base_url`. Review redacted output on real samples.
- [ ] **Provider quota and budget hold.** The provider's quota, rate limits and billing alert cover your expected alert
  and chat load. Kira has no dollar cap, and the provider bills you outside AWS.
  How: set a limit or alert at the provider. Send a burst and watch for rate-limit errors. Kira does not retry inside a
  call, so the durable worker retries within its limits.
- [ ] **Token accounting fails closed.** A run stops with `TOKEN_ACCOUNTING_MISMATCH` and does not continue when the
  provider reports more input than Kira reserved, or no usage. With an OpenAI-compatible provider the reservation is a
  local estimate, not an upper bound. The Anthropic count endpoint is the provider's own estimate.
  How: observe the stop yourself. With the OpenAI protocol, on a staging release with `bytes_per_token` at 8 (the
  smallest estimate allowed), ask one chat question and expect the run to stop. Then compare real prompts with the
  provider's billed input and qualify the `bytes_per_token` you will use (default 3). Any change is a new release.
- [ ] **Diagnosis quality is measured on your model.** Quality on non-Claude models is unmeasured by the maintainers.
  How: run the paid evaluation with `MODEL_API` set ([evaluations](../evaluations/diagnostics/README.md)). A named
  person reads the results, not just the pass rate.

## Load and quota

- [ ] **Limits hold under load.** Chat and alert load, queue capacity, deadlines and hard worker termination meet your
  targets. With the OIDC module, so do the per-user and shared allowances. In the default mode there is no shared chat
  cap and chat shares capacity with incident work, so confirm that mix is acceptable. Every accepted event ends in the
  ledger as active, completed, degraded or a terminal failure.
  How: send a burst at your expected peak, then compare ledger counts with accepted events.

## Recovery drill

- [ ] **Restore and erase.** An isolated restore, purge-registry reconciliation and all-version erasure succeed. Reports
  stay denied after erasure, and no event or replay comes back.
  How: follow [Back up and restore](OPERATE.md#back-up-and-restore) and
  [erasure](OPERATE.md#retention-and-evidence-erasure) on staging.
- [ ] **Rollback and maintenance.** Rolling back and forward again keeps event accounting, epochs and pinned policies.
  Maintenance entry and exit suppress only planned checks, and the canary and receipt work after exit.
  How: follow [rollback](OPERATE.md#roll-back-and-retire-old-releases) and
  [maintenance](OPERATE.md#maintenance-pausing-and-spend).

## Handover

- [ ] **Owners, budget and CI.** Named primary and backup operators, service, security and budget owners approve the
  handover, emergency procedures and any time-limited exceptions (each with an owner and an expiry). A second operator
  completes the runbooks without help from the implementer. Spend matches your approved budget. CI passes on the
  frozen source.
  How: the second operator runs the drill and signs the record. Check your billing console and the CI run.
