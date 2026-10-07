# Phase 4 operator guide

Repository implementation is locally verified; **G4 is not run**. No customer
infrastructure, live endpoint checks, model calls or notifications were performed.
The reference spec is synthetic and cloud commands reject it. Phase 5 is now
locally complete; [its setup guide](../phase-5/SETUP.md) adds identity and separate chat stages.
Follow [Phase 3 deployment](../phase-3/GUIDE.md) for both standalone and AgentCore;
this phase adds three customer-owned Lambda functions and three deployment stages.
It creates no maintainer service and requires no paid orchestration framework.

## Configuration and local reproduction

`infra/observability.example.json` extends the existing spec with an optional
`observability` object. Existing Phase 2/3 specs remain valid. Declare every inventory
instance's observed services, owner, public HTTPS readiness/dependency routes,
exact CWAgent metric ID, dedicated collector heartbeat log group and freshness
window. Multiple services on one instance share its heartbeat stream. The service's
readiness endpoint must return an unsuccessful status when essential dependencies
are unhealthy; alternatively declare explicit dependency health routes. Kira does
not implement readiness semantics inside someone else's application.

URLs are reviewed deployment inputs, not chat/request overrides. Credentials,
query strings, redirects, private/metadata addresses and response bodies are not
accepted as probe evidence. DNS answers must all be public; the connection pins an
address and validates the original TLS hostname. A killable child bounds the entire
DNS/connect/header/body operation. Private VPC-only endpoints are **unsupported by
this adapter**; do not expose a private service publicly just to satisfy it. A
reviewed VPC/network adapter would be additional work before qualifying that fleet.

Defaults: observers every five minutes, synthetic notification daily at 00:00 UTC,
receipt deadline ten minutes, manual inbox check at least every seven days,
collector freshness ten minutes. Canary intervals must divide a UTC day in whole
hours. The synthetic spec has `enabled: false`; rendering does not enable AWS.
Readiness/freshness alarms require two bad periods, about ten minutes plus AWS
publication and queue delay at the default interval. A missing observer heartbeat
requires three periods. A missed daily canary can take up to a day plus its deadline
and the observer/alarm delay to detect. Use shorter approved intervals if that
tradeoff is unsuitable. Each service has its own health invocation; delivery/backlog has a separate
invocation. The Observer has a 180-second Lambda timeout and at most 150 seconds
internally, with remaining-time checks before each operation. Partial health
results publish before freshness reads. Incomplete checks emit explicit attention;
maximum-inventory cadence and customer quotas still require staging qualification.
See the [corrective checkpoint](../review-phases-1-4/CORRECTIONS.md).

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_observations.py
.venv/bin/python scripts/verify_observation_build.py
.venv/bin/python -m infra build --spec infra/observability.example.json --output .build/observation-tools --wheelhouse .build/wheels
.venv/bin/python scripts/verify_durable_render.py --observations --tool-build-dir .build/observation-tools
```

The last command also needs the refreshed Phase 3 pipeline and AgentCore builds
(`verify_pipeline_build.py` and `verify_agentcore_build.py`). Reference renders use
fake bindings with actual local artifact hashes: standalone nine stages, AgentCore
eleven. Neither is an AWS deployment. Full renders generate `coverage.json` with
service and operational alarm descriptors, owners, missing-data and counting rules.
The source spec and stage hashes are authoritative; coverage is a derived report.

## Prepare actual customer telemetry

Before approved staging, supply real private account/regions, IAM roles, model,
instance inventory, endpoints, primary and distinct fallback mailboxes, HTTPS
status URL and budget. Resolve the recorded concurrency quota gap. Keep these in
ignored `.local/` or `docs/implementation/evidence/private/`. Do not copy the
synthetic account/instance/model into a live deployment.

Install/configure CWAgent on the customer's Linux instances using the rendered
CWAgent configuration and scoped instance role. Validate actual metric dimensions
(including process `exe`/`pid_finder`, disk path and InstanceId) against published
metrics; Linux procstat examples do not qualify Windows collectors. Configure
Nginx combined access logging and error logging at the declared paths/groups.
Validate real sanitized positive and negative samples before promotion. The access
filter deliberately includes 500/502/503/504. Its request count and error-log
**diagnostic-event count are separate metrics and alarms**; do not add them together
as a count of unique requests. Access byte values must not be interpreted as statuses.

Run `scripts/collector_heartbeat.py` every minute using a customer-owned systemd
timer (or an equivalent supervised scheduler) with the real inventory instance ID:

```bash
python3 /opt/kira/scripts/collector_heartbeat.py --instance-id "$INSTANCE_ID" --file /var/log/kira-collector-heartbeat.log
```

Use a root-owned installation/unit, least-privilege file ownership readable by
CWAgent, synchronized UTC clock and bounded log rotation. A systemd oneshot unit
should invoke that command; its timer uses `OnBootSec=30s`, `OnUnitActiveSec=60s`
and `AccuracySec=5s`. Enable/start it explicitly on the customer host and verify
both service/timer status and ingestion into the dedicated group, fixed IID stream.
The script only appends a local JSON heartbeat; it does not install a timer or send
AWS data. CWAgent transports it. The observer requires **both** fresh exact CWAgent
metric timestamps and a valid shipped heartbeat. Idle application logs are not
used as a heartbeat. Test rotation, clock skew and shipping delays in staging.

Inventory is static and release-owned. On instance replacement/scaling, refresh
inventory/endpoints/metric and log scopes, build a new immutable release, review the
retirement diff and qualify it before cutover. There is no automatic tag discovery
or autoscaling reconciler; unattended autoscaled fleets are not qualified yet.

## Deploy and verify the additional stages

Use the clean reviewed source and the Phase 3 change-set/inspection/execution
workflow. Retained foundations update only through reviewed diffs; immutable
runtimes use a new release ID, termination protection and the sealed stack policy.

1. Build tools and pipeline for the actual private spec. Build observers with
   `python scripts/build_observations.py --spec .local/customer/deployment.json
   --output .build/customer-observations --wheelhouse .build/wheels`.
2. Render with `--observation-build-dir .build/customer-observations` along with
   the normal build/tool/host/bindings arguments. Update the durable foundation's
   ingress and delivery-DLQ policies to authorize only the explicit canary topic.
3. Review/apply `observation-foundation`: canary topic/subscription, filtered SQS
   test destination and DLQ, separate fallback topic/recipient. Verify the DLQ
   policy authorizes every exact per-service health rule as well as probe/canary. Confirm primary,
   Phase 3 fallback and Phase 4 fallback subscriptions from their actual mailboxes.
4. Upload observers with `python -m infra.durable_ops upload --artifact-kind
   observation --build-dir .build/customer-observations` plus the standard
   `--bundle`, `--review-hash`, `--output` arguments. Bind the exact three returned
   versioned S3 objects as `observation_artifacts`; re-render.
5. Review/create/seal `observation-runtime`; collect its exact outputs as
   `observation_versions` (ObserverVersionArn, CanaryVersionArn, ReceiptVersionArn).
   Re-render the complete plan. Run `verify-observations` to check actual pinned
   code/configuration/capacity and IAM grants against the sealed template. For
   enabled observations, run `seed-health` with bundle/hash/output **before**
   strict coverage/canary/promotion. It invokes health for each reviewed service,
   without model work or notifications. Wait for metric discovery and run strict
   coverage; missing enabled Health metrics still block promotion. Intentionally
   paused inventory records only Health metrics as disabled. Maintenance bootstrap
   is refused. Read the [complete bootstrap order](../review-phases-1-4/CORRECTIONS.md#bootstrap-and-deployment-changes).
6. Qualify/activate the Phase 3 pipeline and reviewed service routing first. Review
   `observations` with the actual enabled setting. Executing this stage requires
   verification of the sealed observer runtime. Its schedules use qualified
   Lambda versions, and its receipt mapping uses partial batch failure handling.
7. Run `verify-routing` and `verify-observation-routing` separately with the standard
   bundle/hash/output arguments. The latter checks schedules/targets, receipt
   mapping, alarm settings/actions, dashboard and confirmed filtered subscriptions.
   Run existing coverage verification for exact metrics, inventory and log fixtures.
   These read checks prove registration/configuration, **not recipient delivery**.
8. For initial bootstrap, explicitly invoke the pinned Canary Lambda once under
   the customer's invocation role after activation; no model request is made.
   It creates the current UTC slot expectation before publishing. Wait for its
   ledger incident, initial publisher acceptance and actual SQS recipient receipt.
   A normal first-run warning remains visible until these and the inbox check exist.
9. Receive the marked synthetic email in the primary inbox. From reviewed source,
   run `python -m infra.durable_ops attest-email --notification-id
   "$RECEIVED_NOTIFICATION_ID" --confirm-inbox-delivery` with bundle/hash/output.
   This stores a trusted operator statement scoped to the topic and current email;
   changing recipients invalidates the previous attestation. Do not attest from a
   publish log or an SQS receipt. Recheck at least weekly by default.
10. Exercise the real fallback mailboxes separately, then run every G4 scenario in
    [ACCEPTANCE.md](ACCEPTANCE.md). Keep receipts/raw responses private. Only approve
    production after the earlier gates and later release qualification also pass.

`verify-observations` and `verify-observation-routing` use read-only cloud APIs.
`seed-health` explicitly invokes the pinned observer and writes approved Health
metrics; it requires clean reviewed source, sealed runtime verification and scoped
Lambda invocation. It does not activate schedules or establish G4.
`attest-email` writes the declared canary/receipt ledger records and requires the
exact received ID and explicit inbox confirmation. Operators need scoped IAM reads
for verification, GetItem/TransactWriteItems to the intended table for attestation,
and scoped Lambda invocation for bootstrap; application UI roles do not receive
these operational writes. Follow the existing deployment-role boundary rather
than granting blanket administrator access.

## Visibility and limits

The CloudWatch operations dashboard includes handoffs, model/tool outcomes, usage,
queue age, observer freshness and receipt checks. In Logs Insights filter the
structured fields by `incident_id` and `fence` to trace an incident across ingress,
dispatch, worker, model/tools, report and initial/follow-up publisher. Recovery
transitions use an atomic alarm-state compare-and-swap, retain out-of-order events
and attach `recovered_at`/`recovery_event_id` to the preceding unexpired incident;
authorized status reads include those fields. Recovery is observation, not a
cancellation of already running work or an automatic remediation.

EMF uses only Component as a metric dimension; IDs appear in safe structured logs.
Outcome counters and SQS native values can duplicate/be approximate. Reconcile
accepted events from the ledger for authoritative accounting. Logs do not contain
raw prompts, tool payloads, URLs, contacts, SDK exception strings or AWS responses.
AgentCore model/tool widgets and qualified runtime native health/log widgets use
the Bedrock region. Its endpoint stage pre-creates retained qualified and DEFAULT
application log groups; actual retention is checked before promotion. Do not invoke
either endpoint before ownership/retention exists. Actual host EMF extraction and
native dimensions need live verification. Local UI stdout has no automatic
CloudWatch transport; cloud qualification does not certify that local execution.
Log retention follows the deployment spec; private evidence retains its Phase 3
policy. `ToolNoData` differs from successful complete evidence. Observed model
usage can miss an ambiguous/lost response; durable conservative reservations remain
the execution allowance, not an exact AWS invoice.

The canary exercises ingress, durable acceptance, dispatch, initial notification
and the separate recipient consumer. It creates no model work, and does not prove
Bedrock, follow-up report delivery, UI access or the recipient's real mailbox.
The observer checks trusted topic/incident/stable initial notification identity
and bounded publication/receipt IDs, so an earlier delivered send with a lost ack
can survive an accepted retry with a different SNS ID. It also checks due times,
primary/fallback subscription confirmation and fresh operator inbox attestation.
CloudWatch alerts bypass the primary notifier and use the independent fallback;
observer failure/heartbeat alarms also go directly to the primary topic. A native
fallback SNS failure alarm goes directly to the primary topic. Actual mailbox
receipts for both routes still need periodic operator exercises. A shared AWS
account/region/network failure is a common dependency; deployments needing that
failure coverage require an external customer monitor and channel.

See [RUNBOOKS.md](RUNBOOKS.md) for recovery boundaries and [COST.md](COST.md) before
turning on live schedules. No resources have been deployed on your account.

Implementation references: [AWS embedded metric format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html),
[SNS delivery-status support](https://docs.aws.amazon.com/sns/latest/dg/sns-topic-attributes.html),
[CWAgent process metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-procstat-process-metrics.html),
[EventBridge UTC schedules](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html).
