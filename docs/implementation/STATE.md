# Resume here

Updated: 2026-10-06. **User-authorized Phases 1–4 corrective batches A–C are
implemented locally; R01–R08 VERIFYING pending live qualification.**
**410 tests**, 64 templates and 13 deterministic package pairs/import checks
pass; both old and extended owned releases render with actual local hashes. Read the
[corrective checkpoint](review-phases-1-4/CORRECTIONS.md). Phase 5 is not started.
No AWS project calls/resources, live probes, inference or notifications occurred.
Floci integration remains proposed, not installed.

## User decisions

- Implement the audit plan one phase at a time, starting with Phase 0.
- Open-source, customer-operated software in the customer's own infrastructure.
  Web chat/alerts/notifications first; local desktop later. No managed service.
- Phase 0 used synthetic service fixtures. The user then confirmed no EC2/Bedrock
  or other project infrastructure exists; only their AWS CLI is configured.
- Prior read-only checks verified the configured default account and region
  `eu-central-1`; private identity is retained only in ignored evidence. There were
  no project resources. Lambda concurrency quota **10** is a live prerequisite gap.
- Shared code-owned Python orchestration with selectable standalone and AWS
  AgentCore, using Bedrock models. Standalone is the default; no Agents Classic
  dependency in the new-account path. No paid orchestration framework required.
- Budget matters. Keep local tests/builds offline; cloud activation needs actual
  customer inventory, identities, model, endpoints, recipients, owners and budget.
  The synthetic reference spec is not authorization or infrastructure.

## Current checkpoint and evidence

- Corrective implementation checkpoint **`99695cf`** on the existing Phase 4
  branch. **410 tests (61 new)**, 64 templates, 13 deterministic ZIP pairs/imports,
  schemas/lint/format/shell/pip/whitespace PASS. Old 6/8 and extended 9/11-stage
  releases reran successfully from clean checkpoint (`source_dirty: false`);
  synthetic cloud seeding denied before clients for all four bundles. No cloud
  qualification is implied. Secret scan: 377 exact reviewed entries, zero new;
  35 public checksum entries added without widened exclusions.
- Current records: [corrective checkpoint](review-phases-1-4/CORRECTIONS.md),
  [sanitized validation](evidence/review-phases-1-4/corrections-validation.json).

- Branch `codex/phase-4-detection-observability`, parent `c3297e2` (Phase 3 docs),
  Phase 3 code `d215bfd`, Phase 3 parent `01e4ce8`.
- Phase 2 code `13db959`, parent `16a523d`; Phase 1 code `ea8a079`.
- Original parent `6b91a71e268ce7b0915055fb897073d3379e1ffe`; verified source baseline
  `1ad38ec1aaff96c4872a653885e33e540742519a`. Original 25-file snapshot/manifest and
  ten reproduced defects remain preserved; unchanged Phase 0 source at `badc15e`.
- **13/52 tasks DONE**, 20 original findings OPEN plus eight VERIFYING review findings
  R01–R08 (local fixes are not production qualification). G0 PASS as a new-deployment prerequisite
  assessment, not deployed runtime qualification. P1.01 hosted CI and live G2/G3/G4
  remain pending. Tests cannot close them.
- Historical Phase 4: **349 tests**, 12 prior + 20 owned + 32 extended CloudFormation templates
  pass; 13 deterministic package pairs/import checks; standalone nine-stage and
  AgentCore eleven-stage complete observation renders verify actual local hashes.
  Previous six/eight-stage releases also render. Lint/format/shell/schema/pip/secret
  checks pass. Locks are unchanged; prior same-day 93-package advisory scan remains
  the recorded scan. No new dependency, project AWS call, push or hosted CI.
- Safe external HTTPS health checks and exact collector/log freshness, separate
  Nginx request/diagnostic counts, atomic recovery links, correlated structured
  metrics and an operator dashboard are implemented. Sender/receipt/observer
  functions exercise initial notification without model work. Real-inbox delivery
  is a separate explicit operator attestation bound to the topic/current recipient.
  CloudWatch fallback and missing-heartbeat alarms bypass the primary notifier.
- New synthetic observation settings are paused. Default live cadence is five-minute
  observers, daily UTC synthetic notifications, ten-minute receipt/freshness windows
  and weekly manual inbox attestation. No VPC-only probe or auto-discovery adapter.
- Full procedures, local limits and pending live matrix: [Phase 4 checkpoint](phase-4/NOTES.md),
  [operator guide](phase-4/GUIDE.md), [runbooks](phase-4/RUNBOOKS.md),
  [validation](phase-4/VALIDATION.md), [acceptance](phase-4/ACCEPTANCE.md),
  [cost/setup](phase-4/COST.md), [sanitized evidence](evidence/phase-4/local-validation.json).

## Next authorized work

The user said “Continue with the Project” after review. Authorized scope was
corrective batches A–C within existing phases, now complete locally. This did
not authorize Phase 5 or live AWS deployment. All eight have repository fixes
and positive tests; final local validation and clean-source checkpoint pass. Preserve current evidence. Batches
A–C need customer acceptance to close findings; no additional phase is authorized. Read
[CORRECTIONS.md](review-phases-1-4/CORRECTIONS.md), tracker and WORK_LOG.

R01 scope correction: full promotion already verified six pipeline role grants;
the historical diagnostic exercised standalone verify-runtime. Checks now live in
the shared verifier, with exact owned role binding and sealed template validation.
Recovery uses four independent CAS-progress scans; AgentCore has a killable SDK
child; notifications have expired-lease ambiguity and audited notification-only
replay; health uses per-service invocations, separate guarded delivery checks and
explicit bootstrap; duplicate receipt identity and remote-region/log/retention
bindings are corrected. Read corrected Phase 3/4 guides before cloud commands.

Historical review evidence at source `175d7e9` remains unchanged. The original
defect runner is historical, not the current acceptance suite. Floci batch D is
still a proposal; customer staging batch E requires real inputs and budget.
The user will decide when Phase 5 starts; do not start it automatically.

Resume Phase 4 staging qualification when actual customer prerequisites and budget
exist. Follow the Phase 3 deployment guide and Phase 4 additions; resolve quotas,
prove exact telemetry and IAM, activate only reviewed qualified candidates, perform
fault/recovery drills, receive real primary/fallback emails and have a second
operator rehearse the runbooks. G4 needs those receipts and timings; G1/G2/G3 and
later production qualification remain separate. Do not provision synthetic resources,
repeat the account preflight unnecessarily, claim production-grade completion or
start Phase 5 without the user's direction.

Keep initial notification/capture and independent fallback operating when expensive
model work is paused. Query/window bounds are not hard billed-byte/dollar limits;
chat per-user controls remain Phase 5. Recovery observations do not cancel active
work. Manual telemetry installation, readiness semantics, subscription confirmation,
private inputs, IAM/quota setup and customer operation remain necessary. See
[complete deployment/cost explanation](phase-3/DEPLOYMENT_AND_COST.md).

## Historical validation

Phase 0: 21 original self-checks, 14 syntax checks, ten reproduced defects, STS plus
nine regional reads. [Preflight](phase-0/PREFLIGHT.md),
[baseline manifest](evidence/phase-0/baseline-manifest.json).
Phase 1: 147 tests including UI flows; deterministic packages and clean-clone check.
Phase 2: 205 tests and 12 templates; actual isolated staging/IAM/canary still pending.
Phase 3: 294 tests, both owned targets and durable ledger/budgets; live AgentCore
boot/model capability/delivery/cancellation/load still pending. Historical records
remain in each phase's VALIDATION.md and WORK_LOG. Keep Streamlit for now.

## Resume procedure

1. Read this file, WORK_LOG and git status.
2. Read the matching task in PRODUCTION_IMPLEMENTATION_PLAN and IMPLEMENTATION_TRACKER.
3. Use CORRECTIONS.md and the corrected Phase 3/4 guides for current behavior,
   reproduction, bootstrap/recovery and pending qualification.
4. Record meaningful work, commands, evidence, limits and blockers without secrets.
   Private customer evidence stays in ignored docs/implementation/evidence/private/.

Historical Phase 4 implementation checkpoint: `832a4e5`. Complete old and extended release
renders passed again from its clean working tree (`source_dirty: false`); synthetic
cloud verification was rejected before creating an AWS client. That historical documentation
follow-up changed no runtime code or live gate. Current corrective implementation
and its limits are in CORRECTIONS.md and corrections-validation.json.
