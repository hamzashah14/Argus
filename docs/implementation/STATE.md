# Resume here

Updated: 2026-10-01. **Phase 0 complete for a new deployment; Phase 1 not started.**

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

- Branch: `codex/phase-0-baseline`.
- Original parent: `6b91a71e268ce7b0915055fb897073d3379e1ffe`.
- Verified source baseline: `1ad38ec1aaff96c4872a653885e33e540742519a`.
- Reference checkpoint: `d1cb3a9`; subsequent changes are documentation/evidence only.
- Original 25-file snapshot and SHA-256 manifest preserved; all 18 application/
  deployment source files remain unchanged from that snapshot.
- Fresh checkout: 21/21 original self-checks, 14 syntax checks and ten reproduced
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

Next eligible task: **P1.01 reproducible builds and CI**, when the user starts
Phase 1. Continue P1.02–P1.08 in dependency order; UI enhancement is P1.08.
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
