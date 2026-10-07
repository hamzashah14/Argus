# Backend deployment and release operations

Status: shared Python orchestration, standalone execution and AgentCore adapters
are implemented locally. This is not a qualified production release. Actual
model capability, AWS permissions, AgentCore boot, delivery, cancellation and load
must pass customer staging. Keep `investigation_paused: true` until qualification.

Every resource, credential and AWS bill belongs to the customer. Maintainers do
not operate a control plane or managed service. Keep customer inventory, addresses,
bindings, AWS responses and receipts in ignored `.local/`; no credentials in deployment JSON.
See [deployment and cost](DEPLOYMENT_AND_COST.md) for required manual setup,
local UI versus cloud processing, and the standalone pilot.

## Architecture and customer choice

Set `runtime_target` to `standalone` or `agentcore` in the durable configuration.
Both use `kira/runtime.py`, Bedrock Converse, the same pinned tool contracts and
incident ledger. Standalone runs in separate incident and chat Lambdas.
AgentCore hosts the same
package behind AWS IAM, with separate incident/chat hosts and release endpoints;
the UI invokes only its qualified chat Lambda gateway. See the current
[identity setup](IDENTITY.md) for the added identity/chat deployment stages.
Standalone still needs customer AWS credentials and connectivity.


## Local preparation

These commands use the locked Python 3.12 environment and local wheelhouse. They
do not call project AWS services:

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/validate_schemas.py
.venv/bin/python scripts/validate_durable.py
.venv/bin/python scripts/verify_pipeline_build.py
.venv/bin/python scripts/verify_agentcore_build.py
.venv/bin/python -m infra build --spec infra/deployment.example.json --output .build/reference-tools --wheelhouse .build/wheels
.venv/bin/python scripts/verify_durable_render.py --tool-build-dir .build/reference-tools
.venv/bin/python -m infra.durable --spec infra/deployment.example.json --config infra/durable.example.json --output .local/reference-plan
```

The `reference_only` example is synthetic. Cloud commands reject it before
credentials are accessed. A render without bindings produces the two regional
bootstrap foundations and durable foundation. Rendering does not deploy anything.

For an actual customer, use a private deployment spec with `reference_only: false`,
verified account/regions, separate UI/CI/deployment roles, approved fleet, exact
telemetry dimensions and recipients. Use qualified executors. Choose a model that
supports **Converse tools and bedrock-runtime CountTokens for the exact request**;
not every Bedrock model supports that combination. Unsupported counting fails
before inference. Model/profile IAM, region availability, entitlements and quotas
need a canary; catalog listing is insufficient. Mantle token counting is not an
implemented adapter. See [AWS token-count support](https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html).

Use SSO/assumed roles/workload credentials through the AWS credential chain.
Establish the deployment identities described under resource ownership and IAM below. AgentCore deployments require appropriately
scoped Runtime/endpoint management and `iam:PassRole` to the execution role with
`iam:PassedToService=bedrock-agentcore.amazonaws.com`. Do not install broad full
access policies as a production workaround. Candidate verification needs scoped
IAM policy reads, CloudFormation reads and exact function/Runtime inspection.

Verify Lambda concurrency headroom before reserving initial
notification slots: AWS requires capacity for the unreserved pool as well. Approve
model/query spend, retention, primary and distinct fallback recipients, fixed HTTPS
status URL and operator responsibilities before staging. EC2/application/collector
setup is customer-owned and must exist for coverage verification.

## Build and bind immutable candidates

Use the actual private inventory for tools:

```bash
.venv/bin/python -m infra build --spec .local/customer/deployment.json --output .build/customer-tools --wheelhouse .build/wheels
.venv/bin/python scripts/build_pipeline.py --output .build/customer-pipeline --wheelhouse .build/wheels
# AgentCore only: build the entrypoint and SDK for Linux ARM64.
.venv/bin/python scripts/build_lambdas.py --function incident_investigate --architecture arm64 --output .build/customer-host --wheelhouse .build/wheels
```

The packages include the prompt, both OpenAPI schemas and shared runtime source.
Rendering checks the source/dependency/artifact hashes; tool packages also bind the
inventory-specific catalog and log scope. ZIP builds reproduce byte-for-byte.
Pure Python import checks on macOS are not proof of an actual AgentCore boot.

Create a private durable config from `infra/durable.example.json`: set target,
explicit limits, URL, fallback recipient, retention and initial capacity. Keep
model work paused. Commit reviewed source before cloud mutations. Mutation commands
reject a dirty or different source revision. Each re-render produces a new review
hash; re-inspect the new bundle instead of carrying a stale hash forward.

```bash
.venv/bin/python -m infra.durable --spec .local/customer/deployment.json --config .local/customer/durable.json --output .local/customer/plan --build-dir .build/customer-pipeline --tool-build-dir .build/customer-tools
```

For AgentCore add `--host-build-dir .build/customer-host`. Once bindings exist,
also pass `--bindings .local/customer/bindings.json`. Binding fields are described
below; none is an invented ARN or `$LATEST` alias.

Cloud operations use the following reviewed pattern, substituting the exact
rendered hash and stage. These commands create/change resources and are for the
customer's approved staging run, not part of local validation:

```bash
.venv/bin/python -m infra.durable_ops change-set --bundle .local/customer/plan --review-hash REVIEW_HASH --stage STAGE --output .local/customer/change-set.json
.venv/bin/python -m infra.durable_ops inspect --bundle .local/customer/plan --review-hash REVIEW_HASH --stage STAGE --change-set CHANGE_SET_ID --output .local/customer/inspected-change.json
.venv/bin/python -m infra.durable_ops execute --bundle .local/customer/plan --review-hash REVIEW_HASH --stage STAGE --change-set CHANGE_SET_ID --change-set-hash INSPECTED_HASH --output .local/customer/execution.json
```

Wait for CloudFormation completion before collecting or sealing. The tool requests
execution; it does not treat that request as successful deployment.

1. Review/create `foundation-tools` in the Bedrock region and `foundation-monitor`
   in the monitoring region. They own artifact buckets, cursor secret, topics and
   declared telemetry resources. Existing resources require ownership/import
   review; do not apply a second owning stack. These stages are stable/updateable.
2. Review/create `durable-foundation`, collect its outputs using `collect --stage
   durable-foundation`, and store them under `bindings.foundation`. Capture starts
   at the SNS-to-SQS subscription before investigations are enabled. Verify primary
   and fallback subscriptions/addresses independently.
3. Run `upload --artifact-kind tools --build-dir .build/customer-tools` using the
   same bundle/review/output flags. Store the returned two objects under
   `bindings.tool_artifacts`. Run `cursor-version` and store its ARN/VersionId under
   `bindings.secret`; this reads metadata, not the secret. Pin/retain this version
   for the release lifetime when rotating the customer secret.
4. Re-render, review/create `owned-tools`, collect its two version ARNs under
   `bindings.tools`, then `seal-runtime --stage owned-tools`. Never update this
   release stack; publish a different release ID. Re-render with collected bindings.
5. Run `upload --artifact-kind pipeline --build-dir .build/customer-pipeline` and
   store returned objects under `bindings.artifacts`. For AgentCore also run
   `upload --artifact-kind host --build-dir .build/customer-host`; store that single
   object under `bindings.host_artifact` in the Bedrock-region bucket.
6. AgentCore only: re-render/create `agentcore-runtime`, collect RuntimeId/version
   under `bindings.agentcore_candidate`, seal that stage, then re-render/create
   `agentcore-endpoint`. Collect its four outputs under `bindings.agentcore` and
   seal the endpoint stage. The endpoint binds the collected numeric version;
   `DEFAULT` is forbidden. Re-render with all actual bindings.
7. Review/create `durable-runtime`, collect its six version ARNs under
   `bindings.versions`, and seal that stage. Re-render again so routing/canary use
   the exact final bundle. All candidate stacks are create-only and retained.

The AgentCore host uses the documented HTTP `/ping` and `/invocations` contract,
SSE heartbeats and two local work slots. It binds 0.0.0.0:8080 only in AgentCore
hosting mode. Do not expose this internal server as an unauthenticated public
standalone API. Direct-code deployment uses a versioned S3 ZIP and Python 3.12;
AWS patches the language runtime, while the customer updates bundled dependencies.
[AWS direct-code guidance](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html).

## Verify, canary and promote

`verify-candidate` verifies the sealed tools/runtime, deployed code/configuration,
actual execution-role trust/inline policies and absence of extra attached policies.
For AgentCore it verifies the pinned S3 checksum, numeric Runtime version, actual
model/tool/limit environment and exact live endpoint target. It does not prove
model compatibility, successful tools, recipient delivery or fault recovery.

`canary --allow-model-invocation` is an explicit **paid staging-only** operation.
It invokes the qualified investigation Lambda using its actual role; AgentCore
selection then invokes the actual host and host role. The request has bounded
allowances and must produce a final answer plus successful logs/metrics contracts.
Coverage checks must pass first. No initial/follow-up notification is sent by this
chat canary. The Lambda canary path is disabled in production.
The canary also requires a live individual investigator session ticket from an
identity-enabled candidate. Complete the identity foundation/grant/OIDC bootstrap
in [identity setup](IDENTITY.md), including its limited issuer role, before
the first canary. A shared password or operator-supplied claim is insufficient.

```bash
.venv/bin/python -m infra.durable_ops verify-candidate --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/candidate.json
.venv/bin/python -m infra.durable_ops canary --allow-model-invocation --access-ticket-file .local/customer/private/canary.ticket --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/canary.json
.venv/bin/python -m infra.durable_ops retirement-plan --bundle .local/customer/plan --review-hash REVIEW_HASH --receipt .local/customer/canary.json --output .local/customer/retirement.json
```

Review the exact obsolete subscriptions/alarms. Run `retire` with the receipt and
`--retirement-plan` if necessary, then obtain a new empty retirement plan. Routing
execution additionally requires both `--receipt` and `--retirement-plan`. It
re-verifies candidate/coverage and a receipt no older than one hour for the exact
bundle/target/model/tools/limits.

Keep `investigation_paused: true` while accepting test events and proving initial
alerts during model denial. Switching it off changes the bundle: re-render,
re-canary and re-review routing for that exact promotion. Verify registration using
`verify-routing`, then complete the production checklist. A registration PASS
is not delivery, latency or production acceptance.

Copy the verified routing output `RuntimeConnection` into the UI environment,
configure customer OIDC and identity settings, and configure incident storage from the durable
foundation. The identity-enabled UI invokes only the dedicated qualified chat Lambda;
In AgentCore mode the chat Lambda, rather than the UI, invokes the exact chat
Runtime and release endpoint.
The UI's incident read role excludes raw EVENT records. Shared-password access
is development only. Identity and
distributed work allowances are implemented; real IdP/origin/IAM and
allowance/load qualification remain pending.

For deployments with observations, follow the corrected
[bootstrap order](TELEMETRY.md#deploy-and-verify-the-additional-stages):
verified enabled health bootstrap must precede strict coverage/promotion.

## Budgets, recovery, replay and rollback

Reference allowances are 32,000 reserved input+maximum-output tokens across all
incident attempts, eight model steps, eight tool calls, 24 log query/discovery
units, 1,024 output tokens per step and 15 minutes per side of the incident anchor.
These are configurable within checked ceilings, not measured production sizing.
Input counting uses the exact Converse messages/system/tools. Reservations are
never refunded on timeout or ambiguous failure; observed usage is a lower bound
when responses are lost. Unsupported model counting/caching fails closed.

Each model/tool handoff checks ownership/fence/deadline and allowance. The host
checks the ledger before starting and permits one execution per attempt fence.
A remote connection loss does not trigger fallback or immediate retry; the lease
expires and external recovery creates a new fenced attempt. Already submitted AWS
operations can continue after disconnect; client close does not prove cancellation.

Query counts, request/response bytes and time windows are bounded. CloudWatch
Insights has no pre-query maximum billed-byte setting, so this is **not a hard
scan-byte or dollar cap**. Validate fleet-specific scan volume/cost in staging.
Bounded redaction and reviewed governance/deletion controls are implemented;
customer profile approval and live retention/restore verification remain pending. TTL/lifecycle
cleanup is asynchronous, while UI reads already reject expired records.

For investigation replay, use `scripts/replay_incident.py` to inspect and then
apply its reviewed plan with the exact event ID/operator identity. It preserves
identity and records an audit intent. Completed, degraded, active, expired or
exhausted work cannot be rerun. Notification-only replay now has a separate
`scripts/replay_notification.py` inspect/apply procedure with exact review JSON,
operator audit and bounded notification allowance. See the
[corrective recovery guide](OPERATIONS.md#backlog-failed-handoff-and-safe-replay).
Unaccepted poison/delivery DLQ replay still needs a separately reviewed procedure.
Reconcile schedules now invoke four independent scan classes with persisted CAS
progress; empty manual payloads scan pending only. AgentCore SDK invocation uses a
killable child to bound the local wait; upstream cancellation remains unproven.

Pause new model work through a reviewed routing change; initial alerts and sweep
remain active. Existing calls may finish and queued incidents can become DEGRADED
at their ten-minute deadline. Full maintenance mode disables all consumer mappings
and sweeps. Do not delete the ledger/queues/KMS/evidence to roll back code.

Target switching/rollback requires pausing, accounting for active leases and old
accepted incidents, then promoting previously qualified compatible releases.
An incident's first execution pins its policy/release; do not reset counters or
reassign it to new model settings. Complete/recover it with its original release,
or retain a terminal operator-review outcome. Do not send one attempt to both
targets. Fresh rollback receipts and endpoint/code/tool verification are required.
Actual target-switch and hard-termination rehearsals remain live acceptance work.

## Resource ownership and IAM

Before provisioning, a customer security administrator creates three distinct
identities: the declared CI/operator role, the UI workload principal, and the
CloudFormation execution role. The execution role trusts CloudFormation. The
operator needs scoped stack/artifact management, exact-role passing, IAM simulation
and policy reads, candidate verification, signing-version labels, and reviewed
access-grant operations. Paid canaries require exact qualified function invocation.

The generated templates create separate workload roles for tools, queues, model
workers, the session issuer, UI reads and observers. Browser users do not receive
these roles. Inspect generated policies and the permission matrix from
[automation dry-run and check](DEPLOYMENT_AUTOMATION.md); it is a conservative screen,
not a complete bootstrap policy generator or proof that every AWS call is allowed.
Organization policies, permission boundaries and service configuration still apply.

Existing log groups, topics or storage must have one reviewed owner. The CLI does
not automatically import foreign resources or transfer ownership. Keep immutable
release stacks and retained evidence separate from updateable foundations/routing.
Changing deployment source or settings requires a newly reviewed plan.
