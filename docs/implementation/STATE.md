# Resume here

Updated: 2026-10-05. **Phase 2 VERIFYING — repository implementation passes local checks; live G2 and Phase 1 hosted CI remain pending.**

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

- Branch: `codex/phase-2-release-isolation`; Phase 2 parent `16a523d`; Phase 1 implementation `ea8a079`.
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
**204 tests**, 12 CloudFormation templates, six-stage/47-resource synthetic render,
93 dependencies with zero known vulnerabilities, deterministic packages and no
unreviewed secret candidates. See [Phase 2 validation](phase-2/VALIDATION.md),
[operator guide](phase-2/GUIDE.md) and [checkpoint](phase-2/NOTES.md).

P2 tasks remain VERIFYING because G2 needs actual isolated staging, intended/denied
IAM calls, candidate invocation, retirement and rollback evidence. No AWS calls,
provisioning, notifications or model invocation occurred in Phase 2. The next
live step needs actual regions/model, identities, fleet, recipient and budget.
Do not mark G1/G2 passed or start Phase 3 without the user's next instruction.
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
