# Phase 1 implementation notes

Authorized scope: P1.01–P1.08. Branch `codex/phase-1-correctness`, parent `badc15e`.
No cloud deployment; use synthetic fixtures and deny network access in tests.

## Checkpoint 1 — Test/build foundation

- Migrated original 9 log, 6 metric and 6 trigger checks into `tests/legacy`.
  Source baseline remains retrievable at `1ad38ec`; Phase 0 evidence is historical.
- Python 3.12.14 is the reference interpreter. Separate pip-tools hashed locks for
  app, dev and Lambda dependencies; SDK bundled into deterministic Lambda ZIPs.
- Shared `kira` package will hold configuration, UTC parsing, response limits,
  metric descriptors and chat behavior. Deployment bundles must include it.
- Next: validate the 21 migrated checks, finish locks/build/CI, then implement
  contracts/config/time/metrics/pagination/SNS/UI with acceptance tests.
- Later phases still own durable incident processing, immutable releases, SSO,
  distributed spend limits, redaction and live integration qualification.

## Checkpoint 2 — 2026-10-05 resume

All eight task implementations are present. Current tests: 134 passing, including
21 migrated checks and 11 Streamlit UI flows. Two schemas validate; three Lambda
ZIPs reproduce and import in isolation. Dependency scan reports zero known issues.
Remaining: final edge cases, narrow secret baseline, browser visual review, setup
docs and final validation evidence. No hosted CI or live AWS validation.

## Checkpoint 3 — Final local verification

147 tests pass. Operator migration and reproducibility commands: GUIDE.md.
Acceptance evidence/limitations: VALIDATION.md. P1.02–P1.08 DONE; P1.01 VERIFYING
for hosted CI. Source and package hashes are in `../evidence/phase-1/`.
All local review actions from checkpoint 2 are complete. Do not repeat Phase 0
harnesses on changed source or treat hosted CI as already run. Phase 2 not started.
