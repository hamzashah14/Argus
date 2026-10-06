# Resume here

Updated: 2026-10-06. **Phase 3 VERIFYING — local durable pipeline and owned Python orchestration implemented and checked, with customer choice of standalone or AWS AgentCore. 294 offline tests pass; local evidence, operator/setup/cost guides and continuity records saved. Live G2/G3, scan-cost acceptance and Phase 1 hosted CI remain pending. Phase 4 NOT_STARTED.**

## User decisions and current context

- Implement the audit plan one phase at a time, beginning with Phase 0.
- Use synthetic service fixtures. The user subsequently clarified that **no EC2,
  Bedrock or other project infrastructure exists**, but their AWS CLI is configured.
- Read-only inspection verified the default CLI account and its configured region,
  `eu-central-1`. Private identity details stay in ignored local evidence.
- Product remains open source and customer operated. Web chat/alerts/notifications
  first; local desktop later. No managed services or maintainer-operated cloud.

## Current checkpoint

**6/6 Phase 0 tasks DONE; G0 PASS as a new-deployment prerequisite assessment.**
This supersedes the initial 5/6 synthetic-only checkpoint. The plan explicitly
clarifies why deployed services are not prerequisites for assessing a new account.
Actual deployment, model invocation, runtime authorization and delivery tests are
still pending in their later phases. All 20 audit findings remain OPEN.

- Branch: `codex/phase-3-durable-incidents`; Phase 3 implementation checkpoint `d215bfd`; Phase 3 parent `01e4ce8`; Phase 2 implementation checkpoint `13db959`; parent `16a523d`; Phase 1 implementation `ea8a079`.
- Original parent: `6b91a71e268ce7b0915055fb897073d3379e1ffe`.
- Verified source baseline: `1ad38ec1aaff96c4872a653885e33e540742519a`.
- Phase 0 reference checkpoint: `d1cb3a9`; Phase 1 now changes application/deployment source.
- Original 25-file snapshot and SHA-256 manifest preserved; retrieve unchanged Phase 0 source at `badc15e`.
- Phase 0 fresh checkout: 21/21 original self-checks, 14 syntax checks and ten reproduced
  defect cases. Runtime Python 3.12.14 with exact audit SDK versions in `.venv`.
- Cloud preflight: STS plus nine regional checks succeeded. No non-terminated EC2
  instances or matching project resources found. Lambda concurrency limit is **10**;
  this is a recorded capacity gap for P2.05/P3.07/P6.03.
- Bedrock model catalog is readable. This does not prove chosen-model invocation
  permission, entitlement, quotas, or agent compatibility.
- No cloud resources created, model invocations, notifications, release or push.

Evidence: [baseline manifest](evidence/phase-0/baseline-manifest.json),
[clean checkout](evidence/phase-0/checkout-validation.json),
[account summary](evidence/phase-0/account-preflight-summary.json).

## Next action

Latest steering: the user authorized best-fit engineering with customer choice of
standalone and AWS AgentCore, then requested an explanation of manual setup,
deployment location and affordability. That explanation is saved in
[deployment and cost](phase-3/DEPLOYMENT_AND_COST.md). Standalone is the default;
maintainers need no customer-facing cloud account or managed service.

Shared SDK-based orchestration and both adapters are implemented, including exact
CountTokens input counting, conservative fenced aggregate reservations, observed
usage, pinned tool calls, deadlines, remote one-execution-per-fence and immutable
release/canary verification. Chat and incident work share the loop. AgentCore hosts
it behind IAM using a pinned endpoint; ambiguous remote failures wait for lease
recovery. No new-account Agents Classic dependency in either deployment path.

Local checkpoint: **294 tests pass**, 20 owned same/split-region templates plus
12 prior templates lint, complete standalone (6 stages) and AgentCore (8 stages)
release renders verify against real local build hashes. Three legacy, six pipeline
and one ARM64 host ZIP pairs are deterministic and import with their bundled SDK.
Lint/format/shell/schema/pip/secret checks pass; 93 unchanged dependencies have no
known vulnerability at the session scan. See [validation](phase-3/VALIDATION.md)
and [sanitized evidence](evidence/phase-3/local-validation.json). No project AWS
calls, resources, inference, notifications, push or hosted CI were performed.

Next authorized Phase 3 work is live qualification once the customer supplies
real regions/model, identities, inventory/telemetry, recipients, stable HTTPS UI URL
and approved pilot budget, and resolves the Lambda concurrency gap. Follow
[GUIDE.md](phase-3/GUIDE.md). Actual AgentCore boot, model capability, IAM isolation,
concurrent claims/reservations, termination, delivery and 1,000 accepted-event
accounting are not proven by mocks. Query/window bounds are not a hard billed-byte
or dollar cap; per-user chat controls remain Phase 5. Keep G1/G2/G3 pending and
all audit findings OPEN. Do not provision the paused synthetic examples or silently
advance Phase 4. For local-only continuation, use the stored source/test/build
checks and preserve this checkpoint; do not repeat AWS preflight unnecessarily.

User authorized all of Phase 1. **7/8 tasks DONE; P1.01 VERIFYING** solely for the
hosted CI acceptance run. Local result: **147 tests passed** (21 migrated checks,
11 UI flows), lint/format/shell/schema/pip checks pass, 86 dependencies scanned with
zero known vulnerabilities, no unreviewed secret candidates. Three Lambda builds
reproduce byte-for-byte and import with their bundled SDK. A clean clone of
`ea8a079` passed all 147 tests/checks and produced identical packages. Browser
review passed; the synthetic preview server is stopped.

Next: run the configured `quality-and-build` GitHub Actions workflow on the reviewed
branch and retain its result, then close P1.01/G1 if successful. No remote push or
CI dispatch has occurred. The user explicitly requested Phase 2. P2.01–P2.06 repository implementation now passes local checks:
**205 tests**, 12 CloudFormation templates, six-stage/47-resource synthetic render,
93 dependencies with zero known vulnerabilities, deterministic packages and no
unreviewed secret candidates. See [Phase 2 validation](phase-2/VALIDATION.md),
[operator guide](phase-2/GUIDE.md) and [checkpoint](phase-2/NOTES.md).

P2 tasks remain VERIFYING because G2 needs actual isolated staging, intended/denied
IAM calls, candidate invocation, retirement and rollback evidence. No AWS calls,
provisioning, notifications or model invocation occurred in Phase 2. The next
live step needs actual regions/model, identities, fleet, recipient and budget.
The user has now requested Phase 3. See [Phase 3 checkpoint](phase-3/NOTES.md) for in-progress work. Keep G1/G2 pending and do not deploy synthetic resources or mark G3 passed from local tests.
See [validation](phase-1/VALIDATION.md) and [operator guide](phase-1/GUIDE.md).

Keep Streamlit and the existing AWS/Bedrock architecture for now.

Before later provisioning, select final regions/model, environment/account boundaries,
approved budget, deployment identity and future pilot. Runtime/telemetry/notification
checks require their resources to exist. See [PREFLIGHT.md](phase-0/PREFLIGHT.md)
for each gap's owner and dependent task. Do not request EC2/agent IDs for nonexistent
resources as a prerequisite to local Phase 1 development.

## Resume procedure

1. Read this file and [WORK_LOG.md](WORK_LOG.md); run `git status --short`.
2. Read the relevant task in `PRODUCTION_IMPLEMENTATION_PLAN.md` and its current
   row in `IMPLEMENTATION_TRACKER.md`.
3. Use [README.md](README.md) for reproduction commands and evidence conventions.
4. Continue the next user-authorized phase, update records at meaningful checkpoints,
   and keep all deployment-specific checks distinct from local/reference results.
