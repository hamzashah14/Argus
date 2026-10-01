# Resume here

Updated: 2026-10-01. Active scope: **Phase 0 only**.

## User decisions

- Implement the existing audit plan one phase at a time, beginning with Phase 0.
- Use a **synthetic reference deployment** for now. Leave live AWS verification
  pending. No real account, region, model, service owner or recipient is selected.
- Product remains open source and customer operated. Web chat/alert investigations/
  notifications first; desktop later. UI and backend changes belong to later tasks.

## Current checkpoint

Phase 0 is IN_PROGRESS. Application, Lambda, schema and deployment behavior is
unchanged. A local pre-change snapshot contains all 25 existing files, including
untracked deployment files. The original three deletions are preserved.

- Baseline manifest: [evidence/phase-0/baseline-manifest.json](evidence/phase-0/baseline-manifest.json).
- Original Git HEAD: `6b91a71e268ce7b0915055fb897073d3379e1ffe`.
- Phase 0 helpers: `scripts/phase0/verify.py` and `scripts/phase0/reproduce.py`.
- Test runtime: Python 3.12.14; isolated SDK dependencies in `.venv`.
- Completed: reference inventory, targets, decisions, local preflight and regression
  records; 21/21 original self-checks, 14 syntax checks, and all 10 defect reproductions.
- Pending: record a baseline branch/revision, validate a clean checkout, then update
  the tracker. Original G0 remains NOT_PASSED while P0.05 live verification is deferred.

## Resume procedure

1. Read this file and [WORK_LOG.md](WORK_LOG.md); run `git status --short`.
2. Read Phase 0 task criteria in `PRODUCTION_IMPLEMENTATION_PLAN.md` and the
   status/evidence rows in `IMPLEMENTATION_TRACKER.md`.
3. Use [README.md](README.md) for validation commands and evidence conventions.
4. Complete the next action above. Do not start Phase 1 without the user's next
   instruction, and do not convert deferred live checks into passed checks.

All 20 audit findings remain OPEN. Local checks do not qualify a production release.
