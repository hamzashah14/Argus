# Resume here

Updated: 2026-10-01. Active scope: **Phase 0 only**.

## User decisions

- Implement the existing audit plan one phase at a time, beginning with Phase 0.
- Use a **synthetic reference deployment** for now. Leave live AWS verification
  pending. No real account, region, model, service owner or recipient is selected.
- Product remains open source and customer operated. Web chat/alert investigations/
  notifications first; desktop later. UI and backend changes belong to later tasks.

## Current checkpoint

**Phase 0 reference work is complete: 5/6 tasks DONE.** P0.05 live verification is
deferred by user choice and remains VERIFYING. Original gate G0 is NOT_PASSED;
0/8 full gates have passed. Phase 1 has not started. Application, Lambda, schema
and deployment behavior is unchanged. A local pre-change snapshot contains all
25 existing files, including untracked deployment files. The original three
deletions are preserved in the baseline commit.

- Baseline manifest: [evidence/phase-0/baseline-manifest.json](evidence/phase-0/baseline-manifest.json).
- Original Git HEAD: `6b91a71e268ce7b0915055fb897073d3379e1ffe`.
- Verified baseline revision: `1ad38ec1aaff96c4872a653885e33e540742519a` on
  `codex/phase-0-baseline`; later checkpoint changes are documentation/evidence only.
- Phase 0 helpers: `scripts/phase0/verify.py` and `scripts/phase0/reproduce.py`.
- Test runtime: Python 3.12.14; isolated SDK dependencies in `.venv`.
- Completed: baseline preservation and clean-checkout verification, reference
  inventory, targets, decisions, local preflight and regression records; 21/21
  original self-checks, 14 syntax checks and all 10 defect reproductions. Fresh
  checkout remained clean and preserved all 18 application/deployment source files.
- Evidence: [clean-checkout result](evidence/phase-0/checkout-validation.json).
- Pending live inputs: target account/profile, regions/model, real service inventory,
  named operators, recipients/fallback, security decisions and approved budget.
- Next repository task **only when requested**: P1.01 reproducible builds/CI, then
  P1.02–P1.08 in dependency order. UI improvement is P1.08; preserve Streamlit for now.
- No remote push, release, AWS API call, infrastructure change or notification occurred.

## Resume procedure

1. Read this file and [WORK_LOG.md](WORK_LOG.md); run `git status --short`.
2. Read Phase 0 task criteria in `PRODUCTION_IMPLEMENTATION_PLAN.md` and the
   status/evidence rows in `IMPLEMENTATION_TRACKER.md`.
3. Use [README.md](README.md) for validation commands and evidence conventions.
4. Continue the next user-authorized phase. If Phase 1 is requested, the plan permits
   repository work using synthetic fixtures while P0.05 remains deferred. Carry
   the live gap forward; never convert deferred checks into passed checks.

All 20 audit findings remain OPEN. Local checks do not qualify a production release.
