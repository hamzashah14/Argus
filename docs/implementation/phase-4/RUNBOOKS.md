# Operations and recovery runbooks

Status: written and reviewed against local code/tests; **another operator's staging
rehearsal is pending**. These are customer procedures, not a maintainer service.
Read the Phase 3 [budgets, recovery and replay](../phase-3/GUIDE.md#budgets-recovery-replay-and-rollback) and
[deployment guide](../phase-3/GUIDE.md) with this document. Until staging assigns
named people, `deployment-oncall` and the spec's service owners are responsibility
roles, not evidence of an accepted production handover.

## Ownership and first response

| Signal/resource | Responsible role | First evidence |
|---|---|---|
| Availability, resource, process, Nginx requests/diagnostics, telemetry freshness | Service owner in coverage.json | Exact metric descriptor, readiness and collector/source timestamps |
| Ingress/dispatch/work/reconcile/model/tool, report and notification failures | deployment-oncall | Incident ID/fence, authoritative ledger and private checkpoints |
| Queue delay, retries, all pipeline queues and their DLQs, stream/delivery DLQs | deployment-oncall | Queue source, oldest age, due intents and terminal statuses |
| Canary expectation/receipt and observation-dead/observation-receipts | deployment-oncall | Slot, expected incident ID, publisher MessageId, recipient MessageId |
| Primary, Phase 3 fallback and Phase 4 observation fallback subscriptions | deployment-oncall plus recipient owner | Confirmation/attributes and an actual received email |
| IAM/credentials/cursor-secret rotation | Customer security/deployment owner | Reviewed grants, pinned release, denied/allowed canaries |
| Spend, retention and maintenance windows | Customer budget owner plus deployment-oncall | Usage, current approved threshold, pending work and resume deadline |

Every alarm's owner/descriptor is listed by the rendered coverage manifest. The
operational alarm descriptions point here. Do not silently assign production
responsibility to Codex. Establish a primary/backup person and a reachable customer
escalation route before activation.

For any page, record UTC time, environment, release/source/bundle hash, alarm name,
incident ID and safe outcome code. Read the exact descriptor and dashboard; use
Logs Insights fields `Component`, `outcome`, `incident_id`, `fence`. Check real
service health separately from investigation status. Inspect the original event,
checkpoints and SDK details only through authorized private storage. Never paste
raw logs, credentials, account responses or contacts into committed evidence.

## Availability, recovery and absent telemetry

1. Check readiness directly from the intended external vantage point and inspect
   the customer's listener, Nginx and dependency status. A metric or low request
   count does not establish application availability.
2. Confirm DNS is public, TLS validates and the response meets the configured
   status/size/time limit. `DESTINATION_DENIED` is a deployment/network input
   problem, not proof of application failure. A `TIMEOUT` can include DNS or a
   hanging response; use customer diagnostics to distinguish them.
3. Inspect exact CWAgent dimensions and recent timestamps. Check the heartbeat
   timer/file, agent status/role, shipped stream and timestamp skew independently.
   A stopped timer, missing metric or missing shipped heartbeat is telemetry
   uncertainty; do not assert an idle application is hung from missing access logs.
4. Repair the failed component. Exercise a dependency failure even if EC2 remains
   running. Verify healthy readiness and fresh collector evidence for the configured
   evaluation windows, then observe OK and the preceding incident's linked recovery.
5. Recovery events remain retained; out-of-order events cannot replace newer state.
   An expired prior incident cannot be linked. Recovery does not cancel an already
   running model attempt. If the retained incident is still incomplete, report that
   uncertainty rather than overwriting evidence with a recovery message.

Nginx access counts represent 500/502/503/504 requests. Diagnostic-event counts
can refer to the same failures and are not additional unique failed requests.
Check timestamp/timezone extraction on private sanitized real samples; unsupported
formats must be corrected in a reviewed release, not assumed to match combined logs.
Confirm agent log rotation/file permissions if only one log source disappears.

## Backlog, failed handoff and safe replay

First determine whether an event was never accepted, is a poison source, has an
accepted incident with a pending intent, is leased/running, or is terminal. Keep
queue capture operating when pausing expensive model work. See Phase 3 replay
boundaries: automatic reconciliation resends durable pending intents, reclaims only
expired leases and enforces fences/attempt/aggregate budgets. Read queue age and
ledger state together; SQS counts are approximate and the PendingIntents GSI is
an eventually consistent due-work view.

For accepted work, fix the specific permissions/target/worker/notification defect
before allowing retries. Verify the pinned version, scoped policy, queue mapping,
visibility/redrive and partial-batch settings. Do not bulk send messages, delete an
unexplained backlog, edit a lease/fencing token or reset budgets. An ambiguous SNS
publish can legitimately lead to a duplicate email; use the stable notification ID.
Never interpret an SDK timeout as proof the message was not published.

For ingress DLQs, privately inspect and validate the exact SNS source/account/topic,
IID and transition. An invalid source must not be laundered into an accepted event.
For dispatch/notification/work DLQs, correlate the exact intent to the ledger before
any controlled redrive. For stream/delivery/observation-dead, distinguish transport
failure from a recipient/parser failure. Replaying an observation canary uses the
same UTC slot identity; it must not create model work. Terminal/exhausted incidents
need the Phase 3 authorized recovery procedure, not an unbounded retry loop.

After recovery, account for every accepted event as active, completed, degraded or
explicit terminal failure. Record duplicate/non-actionable events separately.
Recheck actual initial/follow-up recipient delivery; authoritative accounting is
from durable records, not a dashboard metric total.

## Model or tool outage

Initial notifications remain independent of model execution. Confirm their delivery
first. Distinguish `COUNT_FAILED`/`INFERENCE_FAILED`, `INVOCATION_FAILED`, partial or
no-data evidence and a limit/deadline outcome. Check selected-model availability,
IAM/entitlements/quota/region, immutable tool ARN and telemetry scope. Do not add a
broad permission policy, disable CountTokens or bypass incident/window budgets.

Set `investigation_paused: true` through a reviewed routing update during a model
outage or spend emergency. Preserve ingestion, dispatch, initial notification,
reconciliation and independent observers unless a separate maintenance plan says
otherwise. No automatic standalone/AgentCore failover is implemented: an ambiguous
remote run waits for lease recovery and does not start a second executor. Qualify a
replacement model/target/new release with the paid staging canary before changing
production. Resume through reviewed routing and reconcile the resulting backlog.

## Lost notification or canary

Inspect the current UTC slot's CANARY expectation, incident and initial notification.
An expectation is written before publication. `PUBLISHER_ACCEPTED` means SNS
acknowledged publishing, not that email arrived. A recipient receipt requires the
separate SQS consumer's record and the same publisher MessageId. Check the actual
primary and fallback subscription attributes and the receipt mapping/DLQ. Removing,
filtering or leaving a subscriber unconfirmed fails verification. Check the sender,
consumer, observer schedules, pinned target permission and Errors/Throttles as well.

The independent CloudWatch route alerts without invoking the primary notifier.
Observer failure/heartbeat alarms also publish directly to the primary reports
SNS topic; fallback SNS native delivery failures page that primary route. Neither
proves inbox delivery. Receive a marked canary in the real primary mailbox and
attest its exact notification ID using the guide's explicit command. Repeat within
the configured window and after every recipient change. Send/observe a separately
approved fallback exercise and retain its receipt; the primary attestation does
not attest fallback delivery. Shared account/region failures need the customer's
external monitor/contact procedure.

Do not disable a canary/freshness alarm because it exposes unfinished setup. For
bootstrap, invoke the pinned canary once after activation and confirm receipts.
During fault drills, retain warning timestamps, recovery and absence of model work.
SNS can accept duplicate sends after an ambiguous publish; mismatched receipt IDs
remain an attention signal, requiring operator inspection rather than fake success.

## Recipient change and credential rotation

Update private primary/fallback inputs, confirm ownership, render/review changes,
confirm replacement subscriptions in the mailbox, then verify registration and
receive actual messages. Retire obsolete subscriptions only after the replacement
route works. Primary inbox attestations are fingerprinted to the current topic/email;
old attestations do not qualify a replacement. Verify old recipients stop receiving
new notifications and record authorized retirement evidence privately.

Use customer SSO/assumed roles/workload credential rotation. Rotate leaked credentials
at their source, inspect CloudTrail privately and replace pinned releases if grants
or configuration changed. For the log-cursor secret use a new version, rebuild/bind
and qualify the immutable tools before retirement; retain rollback compatibility
for the approved window. Never copy secrets into repo configuration, CLI output or
incident messages. Verify permitted operations and denial of unintended resources
from each role before resuming.

## Maintenance and cost emergency

Declare an owner, start/end UTC and resume deadline. `maintenance_mode: true`
suppresses service/freshness actions and normal incident processing according to
Phase 3 routing; the observer still checks its own pipeline heartbeat and preserves
outbox visibility. Its application/canary/subscription/inbox checks are explicitly
SUPPRESSED, not successful. Queue-age alerts are suppressed for planned backlog;
DLQ, observer/Lambda and delivery-failure signals remain operational. Canary
expectations are not created during maintenance. Review every resulting schedule,
mapping and alarm action setting with the routing verifier.

For an investigation spend spike, pause model work first, limit manual chat and
expensive Logs Insights/dashboard refreshes, and keep capture/initial/fallback
notification intact. To stop observation work as well, review `enabled: false` in
an emergency plan with an external temporary monitor and a re-enable deadline;
this disables new health alarms/observer schedules/receipt mapping but does not
remove stored resources or recurring alarm/storage/key costs. Do not destroy
queues, keys or rollback artifacts simply to clear alarms. Billing notifications
are not a hard cutoff; compare real customer usage to the approved budget.

End maintenance via a reviewed release/routing update. Check collector freshness,
endpoints, registrations, initial alert receipt and fallback receipt; explicitly
bootstrap the current canary if the next UTC schedule is too far away. Reconcile
pending work within existing budgets before resuming model investigation. A
sustained false-positive or capacity issue requires targeted requalification.

## Rehearsal and closure

A second customer operator must follow these procedures on the frozen staging
candidate, including failed listener/collector, lost recipient/notifier, safe
backlog recovery, maintenance exit and credential/recipient rotation. Record who,
which source/bundle, commands, timings, actual receipts and unresolved limits.
G4 remains pending until [ACCEPTANCE.md](ACCEPTANCE.md) is satisfied. Local tests,
registration checks and written runbooks do not close the 20 audit findings or
qualify this project for production.
