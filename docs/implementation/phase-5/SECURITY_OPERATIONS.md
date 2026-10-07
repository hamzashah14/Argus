# Customer security operations

Local P5.03/P5.06 implementation and rehearsal with synthetic fakes; actual AWS,
IdP and inbox verification **NOT_RUN**. These procedures are not deployment
commands executed in this session. Assign an identity administrator, security/data
owner, incident responder and budget owner before activation. Codex owns local
engineering records only. No customer risk has been accepted on their behalf.

## Data policy and audit

| Data | Treatment | Retention / access |
| --- | --- | --- |
| Credentials, signing keys, OIDC client/cookie secrets, session tickets | Restricted; independent secrets, exact version binding; never public evidence, URLs or logs | Customer secret store/private local configuration; rotate through a new release |
| Raw customer logs/inventory and provider claims | Restricted; raw source stays in customer systems; tested redaction before model/storage/delivery | Customer owns CloudWatch/provider retention; do not copy raw records into this repository |
| Redacted evidence/checkpoints/final reports | Sensitive operational data; private versioned KMS bucket, TLS, explicit KMS upload policy | Reviewed deployment evidence lifecycle and authoritative incident TTL; reads require active in-scope identity |
| Grants/sessions/quota leases | Sensitive metadata; encrypted separate table, deletion protection and PITR | Grant revocation tombstones retained; session expiry is checked before access regardless of TTL; quota TTL is cleanup |
| Access records | Pseudonymous actor, action/outcome, instance, environment/account/release; no prompts/claims/tickets | Application audit TTL default 30 days; customer-configurable maximum 90 days |
| CloudTrail data access | Restricted customer audit bucket, SSE-S3, public block, TLS, versioning and digest validation | Current/noncurrent lifecycle follows audit-days policy; actual receipt and integrity verification pending |
| Erasure tombstone / private purge registry | Incident/event IDs, fence and review reference; no report content | Live tombstones 35 days; private registry retained through all customer backup/export retention |

Application authorization records persist login, permitted/denied chat/report and
allowance decisions. Audit storage failure denies the corresponding access; it
does not silently allow and emit a success-only console record. Lambda IAM
transaction permissions use the underlying item actions; see the official
[DynamoDB transaction IAM documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html).
The customer workload roles cannot change grants or scan memberships.

Identity-enabled durable foundations include a single-region CloudTrail trail for
`incidents/` S3 object access and reads of the exact incident/session tables. No
account-wide data selector or audit-write loop is configured. CloudFormation
[trail configuration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudtrail-trail.html)
and [data-event documentation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
describe these controls and their additional charges. Verify actual received
records and digests after known reads/writes; a configured/logging trail alone is
not receipt evidence. CloudTrail/system log fields may identify AWS principals;
the customer must approve that classification and access, not assume anonymization.
TTL/lifecycle cleanup is asynchronous; live incident/session time checks enforce
expiry and report denial independently. PITR, exports and provider retention are
separate; live deletion is not backup deletion or cryptographic shredding.

## Access review and offboarding

Proposed cadence: monthly identity/recipient review, quarterly rotation rehearsal,
per-release IAM/model/redaction review, and immediate review on departure, incident
or provider/policy change. The customer owner must approve the cadence and record
completion, exceptions and next due date privately.

Use a separately scoped customer administrator, exact reviewed bundle/account and
owner-only ignored private directory. CLI output is mode 0600 and refuses a
symlink file; operators must secure the directory and ancestors too.

```bash
umask 077
mkdir -p .local/customer/private
chmod 700 .local/customer/private
.venv/bin/python -m infra.security_ops access-review --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/private/access-review.json
```

This consistent paginated review contains only pseudonymous grant metadata,
release match, role/scope/epoch/enabled flags. It does not infer employment or
automatically delete grants. Compare it with the customer's authoritative roster
and owner attestations. For stale access use the reviewed `grant-plan`/`grant-apply`
workflow in [setup](SETUP.md), `enabled:false`, advancing epoch. Keep tombstones;
delete/recreate can reset epochs. Revoke provider/SSO/workload sessions too. An
accepted SDK call may finish; application revocation is not forced cancellation.
Test expired/old-epoch tickets and direct IAM calls. Do not serve restored grants
until the restore reconciliation below is complete.

## Rotation and rollback rehearsal

1. Record approved source/bundle, current grants/epochs, immutable signing/cursor
   versions and rollback labels privately. Pause new interactive work, allow
   accepted requests to finish and retain incident notification recovery paths.
2. Create a new signing secret version through customer Secrets Manager admin
   credentials. Collect metadata only; bind the new exact version in a **new
   reviewed release**, pin its release label and re-render/rebuild/seal/verify the
   candidate. Never retarget an existing release label or rely on `AWSCURRENT`.
3. Review/rebind intended users to the new release with incremented epochs and
   fresh OIDC authentication. Verify old tickets fail, current grants work and
   disabled actors remain disabled. Signing-key caching can last one minute, but
   authoritative epoch/release checks still apply on each action. Retire obsolete
   caller/endpoint permissions only through reviewed retirement gates.
4. OIDC client secret and browser cookie secret are independent of signing keys.
   Rotate them privately with the provider and local UI deployment; restart the
   UI, clear old browser sessions and require fresh MFA. Test login/logout,
   callback/origin and provider revocation. Never make them a runtime signing key.
5. Cursor-secret rotation changes immutable tool binding/release; old pagination
   cursors fail. Rebuild/redeploy verified tools, update the release and rebind
   grants, then restart discovery rather than accepting an old cursor under a new
   key. Rotate workload credentials using customer SSO/assumed roles; revoke old
   sessions and test IAM directly. Use no hardcoded long-lived keys.
6. Rollback selects the retained old immutable code/key label but requires a
   **new reviewed access decision and epoch**; do not restore old enabled grants
   or revive disabled users. Review old recipients and endpoints before resuming.
   Record denials and an independent operator's attestation. Keep old key labels
   only for the approved rollback period, then separately review retirement.

Local tests cover changed signing key, stale epoch, grant tombstones and old
release bindings after synthetic restore. Provider revocation/browser cookies,
actual AWS secret rotation/cache behavior and the entire live rollback remain
pending. A runbook rehearsal with fakes cannot close those gates.

## Recipient retirement

Update the private desired configuration with authorized replacement primary and
fallback recipients, then render a complete reviewed bundle. Before change-set
execution, inspect stale **CloudFormation-owned** subscriptions across routing,
incident fallback and observation fallback:

```bash
.venv/bin/python -m infra.security_ops recipients-plan --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/private/recipient-plan.json
# Independently review every exact topic/subscription/old endpoint in the plan.
.venv/bin/python -m infra.security_ops recipients-apply --bundle .local/customer/plan --review-hash REVIEW_HASH --plan .local/customer/private/recipient-plan.json --output .local/customer/private/recipient-result.json
```

Apply rechecks the exact diff, unsubscribes only reviewed stale owned email
subscriptions and requires NotFound confirmation. It refuses unconfirmed/foreign
subscriptions and ambiguous outcomes. Resolve those manually under the customer's
SNS administrator, never interpret an API timeout as retirement. No email is sent
by this command. Apply the reviewed CloudFormation updates afterward so it cannot
recreate obsolete recipients, confirm replacements and run real primary/fallback
inbox acceptance. Rollback must not reintroduce departed recipients. Customer-owned
subscriptions outside these stacks require an explicit separate inventory/review.

## Evidence deletion and partial recovery

Deletion is an explicit security-owner decision for a **terminal, quiescent**
incident. Finish or explicitly suppress pending delivery using the existing
notification workflow; do not erase running/retryable work or forcibly cancel it.
Wait at least 15 minutes after the recorded deadline/lease. This covers bounded
worker lifetimes, not arbitrary unreviewed external writers.

```bash
.venv/bin/python -m infra.security_ops erase-plan --bundle .local/customer/plan --review-hash REVIEW_HASH --incident INCIDENT_ID --output .local/customer/private/erasure-plan.json
# Review exact incident, row digests, account/bucket and all immutable object versions.
.venv/bin/python -m infra.security_ops erase-apply --bundle .local/customer/plan --review-hash REVIEW_HASH --plan .local/customer/private/erasure-plan.json --output .local/customer/private/erasure-result.json
```

The bounded manifest includes every version and delete marker, not just the latest
object. Apply rechecks it, fences the incident into DELETING and removes readable
pointers/queue indexes, deletes only reviewed versions, verifies no new versions,
removes incident details and saves minimal DELETED/event tombstones. Report reads,
new investigation and notification replay deny DELETING/DELETED. A partial failure
keeps that denial marker. Save its private review record, fix the underlying
failure and generate/review a **new** plan for remaining versions/rows; no blind
retry or broad prefix deletion. Manifests over 10,000 rows/versions require a
separately engineered bounded procedure. Foreign/unversioned objects are refused.

The separately authorized erasure role needs exact-table GetItem/Query/UpdateItem/
DeleteItem/PutItem, exact bucket ListBucketVersions limited to `incidents/`, and
DeleteObjectVersion on reviewed incident prefixes, plus the STS account check.
Access-review needs exact-table Scan; recipient administration needs exact-topic
subscription inspect/unsubscribe and stack read permissions. These administrative
privileges are intentionally absent from ordinary UI/runtime roles. Approve IAM,
review source and keep private receipts before any actual destructive operation.

## Isolated backup restoration

Maintain an owner-only purge/offboarding registry independently of the restored
tables. Never reconnect a restored PITR/export into serving roles or stream/queue
workers immediately. Retained shared KMS keys do not individually erase backups.

1. Restore into isolated customer resources with no UI/model/notification/stream
   invocation permissions. Inventory restore time, export/PITR and object history.
2. Reconcile every registry deletion and disabled identity against the restored
   rows; erase prohibited evidence/versions again using reviewed manifests and
   retain anti-replay tombstones. Check recovery links/checkpoints/notifications.
3. Use a new signing version **and new release binding**; reconcile desired
   enabled users with incremented epochs and explicit reviewed grants. A restored
   old grant/session then fails the release binding even if its epoch rolled back.
4. Validate report denial and no event/replay resurrection, dependency IAM and
   recipient decisions. Obtain security-owner approval and a second-operator
   attestation before attaching any serving role or enabling workers.
5. Retire isolated superseded backups according to customer retention/legal policy.
   Keep the purge registry through the longest backup/export window. Provider/model
   retention, old CloudWatch logs, audit records and email inbox copies require
   separate customer processes; incident erasure does not remove them.

## Incident responsibility and residuals

The customer incident responder owns evidence review/remediation and escalation;
security/data owner owns access, deletion, classification and exceptions; budget
owner owns quotas/model usage/audit costs. Their names are pending, so broad access
and sensitive-data use remain gated. [Residual register](SECURITY_REGISTER.json)
records proposed constraints with engineering owners, due dates and required
customer decisions. None is silently marked accepted or closed. Renew an exception
only with owner approval, scope, mitigation and expiry; expired exceptions block
release qualification. Preserve all original findings and live gates in the tracker.
