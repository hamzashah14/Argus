# Implementation work log

Append entries; retain previous outcomes when later work supersedes them.

## 2026-10-01 — Phase 0 started

- User corrected the requested starting point from Phase 1 to **Phase 0**, then
  explicitly selected a synthetic reference deployment with live verification pending.
- Read the audit, implementation/product plans, tracker and current source. No
  application changes had been made before the scope correction.
- Existing work: modified application/deployment files, three pre-existing deleted
  legacy files, untracked current deployment files and planning documents. Preserved
  all of it; no reset, cleanup, deployment or cloud operation performed.
- Captured 25 existing files in `.local/baselines/pre-phase-0-2026-10-01.tar.gz` and
  recorded individual SHA-256 hashes, permissions, parent Git revision and status.
- Confirmed `config.env` and `.env` are absent. AWS CLI is installed; no target
  identity is selected. Local absence of environment credentials does not prove
  that the machine has no profiles or other credential providers.
- Added continuity instructions, a baseline check harness, synthetic fixture inputs,
  and an offline reproduction harness. Original embedded self-checks remain in place.
- No new task/agent, recurring automation, cloud resource, public release or remote
  push was created. Current next action: run checks and finish Phase 0 evidence.

## 2026-10-01 — Reference records and checks

- Recorded three explicitly synthetic services, exact metric dimensions, current
  resource names/ownership uncertainties, unsupported scope, and missing evidence.
- Recorded provisional latency/load/recovery/retention and USD 50 pilot-budget
  placeholders. These are test proposals, not approved live spending or an SLA.
- Recorded selected architecture/security directions and unresolved customer choices;
  P0.05 remains VERIFYING and the original G0 cannot pass without its live evidence.
- Installed the exact audit SDK versions into a new Python 3.12.14 `.venv`.
  The sandbox download failed on DNS; an approved network-enabled retry succeeded.
- `.venv/bin/python scripts/phase0/verify.py --output docs/implementation/evidence/phase-0/baseline-checks.json`:
  PASS, 21 original self-checks and 14 original-file syntax checks, no cloud calls.
- `.venv/bin/python scripts/phase0/reproduce.py --output docs/implementation/evidence/phase-0/regressions.json`:
  R01–R10 all REPRODUCED, across eight audit findings. No findings closed.
- `.venv/bin/python -m pip check`: PASS. `git diff --check`: PASS. No application,
  Lambda, schema or deployment source changed from the pre-Phase-0 snapshot.
- Added README navigation, continuity docs and ignores for local/private records and
  Finder metadata. Next action: preserve the complete baseline in a local branch/
  revision and verify that a fresh checkout reproduces the original checks.

## 2026-10-01 — Baseline saved and reference gate reviewed

- Created local branch `codex/phase-0-baseline` and commit
  `1ad38ec1aaff96c4872a653885e33e540742519a` with the existing project work and Phase 0
  records. The broad diff against the old parent includes the user's earlier changes;
  snapshot hash comparison confirms no application/deployment behavior was edited
  during Phase 0. Git operations required access to protected Git metadata and were
  approved. No push or remote operation occurred.
- Ran a fresh local `git clone --no-hardlinks --no-local`, verified its exact HEAD
  and clean status, and ran both harnesses using the isolated Python 3.12.14 environment.
  Result: 21/21 original self-checks, 14 syntax checks and 10/10 defect reproductions.
  All 18 application/deployment source files matched the pre-change manifest; the
  clone remained clean. Evidence: `evidence/phase-0/checkout-validation.json`.
- Reviewed statuses: P0.01/.02/.03/.04/.06 DONE for the approved reference scope.
  P0.05 remains VERIFYING with live verification deferred by the user's choice.
  Original G0 NOT_PASSED; no findings closed; Phase 1 NOT_STARTED.
- Customer owners, account/model/fleet, recipients and live budget remain explicit
  placeholders. The plan permits subsequent repository work with synthetic fixtures
  if requested, but no cloud integration can claim those prerequisites passed.
- Updated tracker and resume instructions. Next action: user selects the next phase
  or supplies a real target for P0.05. No application/UI/backend changes were made
  in this phase; those remain in the planned correctness/reliability tasks.

## 2026-10-01 — User clarified a new AWS deployment

- User said no EC2, Bedrock or other project resources exist, and AWS CLI is configured.
  This clarifies that the baseline is a new deployment, not migration of a live fleet.
- Inspected the single local `default` profile and configured `eu-central-1` region.
  STS authentication succeeded with an IAM user. Account ID/principal ARN were saved
  only in ignored private evidence. No credentials were printed or committed.
- Nine read-only regional checks succeeded: EC2, Bedrock agents/model metadata,
  Lambda capacity/functions, SNS topics, CloudWatch alarms, log groups and EventBridge
  rules. No non-terminated EC2 instances or matching project resources were found.
  Lambda reports zero functions and a concurrency quota of 10. Bedrock catalog lists
  text-model metadata; this does not establish invocation access or model-specific quota.
- Sandbox calls could not reach AWS; approved network-enabled read-only retries worked.
  No cloud resource changes, model invocation, sample data or notifications occurred.
- Updated the plan's P0.05/G0 interpretation explicitly for a new deployment:
  prerequisite assessment records actual capabilities and gaps; it does not require
  deployed EC2/agents/subscriptions. Earlier 5/6 checkpoint is superseded by 6/6,
  with later deployment checks assigned to their actual dependent tasks.
- Recorded the observed Lambda concurrency gap and the need to validate the example's
  reserved-concurrency setting before deployment. No quota request was submitted.
- Updated tracker, resume notes, decisions, inventory and sanitized evidence. All
  audit findings remain open; application source unchanged. Next eligible work is
  P1.01 when Phase 1 is requested. Final deployment region/model/budget remain unset.

## 2026-10-01 — Phase 1 authorized

- User requested Phase 1. Created `codex/phase-1-correctness` from `badc15e` with a clean working tree.
- Scope: P1.01–P1.08, local code/tests/UI/build work; no AWS deployment.
- Active task P1.01; original 21 checks will migrate into pytest, with new acceptance tests for corrected behavior.
- Account concurrency 10 and later-phase security/durability gaps remain open.

## 2026-10-05 — Phase 1 resumed, implementation checkpoint

- Implemented shared configuration, UTC parsing, exact metric descriptors, signed
  discovery cursors, bounded tool/SNS payloads and chat error handling. Migrated all
  21 embedded checks; added contract/configuration/boundary/UI regression tests.
- Added separate hashed dependency locks, bundled SDK builds, CI workflow and
  deterministic ZIP verification. Local result before this checkpoint: 134 tests
  passing, both OpenAPI documents valid, lint/shell checks passing, all three
  packaged handlers import without site packages.
- Dependency scan reports no known vulnerabilities across 85 package records.
  Secret candidate triage, browser review, final edge-case checks and documentation
  remain. No hosted CI, deployment, model call or notification was performed.
- Phase 1 implementation is not production qualification; later phase gates remain
  open. Original Phase 0 harness results refer to its preserved source revision.

## 2026-10-05 — Phase 1 final local acceptance

- Fixed review edge cases: malformed catalog field types/size, relative config
  paths, validation before log client creation, UTF-8 decoder finalization at the
  output limit, conservative outer JSON sizing and exact custom alarm/catalog ID
  matching. Added six built-in alarm descriptor checks and related regressions.
- Final pytest: **147 passed**, including 21 migrated checks and 11 UI flows.
  Ruff lint/format (48 files), ShellCheck, both OpenAPI schemas, pip check and
  `git diff --check` pass. Tests deny AWS clients/socket connections by default.
- Found the macOS lock omitted Streamlit's Linux watchdog dependency; made it
  explicit, regenerated app/dev locks and reinstalled with `--require-hashes`.
  Linux dependency metadata closure passes; Linux execution remains unverified.
- `pip-audit` updated lock: 86 packages, zero known vulnerabilities. Secret scan:
  reviewed synthetic test values and checksum fingerprints only. A new synthetic
  credential candidate correctly failed the scanner; the probe was removed.
- `scripts/verify_build.py`: three deterministic ZIP pairs and three isolated
  imports pass with bundled boto3 1.43.106. Source, dependency and artifact hashes
  recorded in public Phase 1 evidence; raw local output stays ignored in `.build`.
- Browser review used only synthetic localhost settings and disabled profile
  files. Sign-in and workspace layout inspected; fixed clipped header spacing.
  Preview screenshot saved in `.local/phase1/workspace.jpg`.
- Updated setup/migration/testing docs, catalog example, prompt pagination and
  evidence uncertainty guidance. Removed stale claims of guaranteed notification
  delivery, immutable releases, free-tier costs and maintainer-hosted UI.
- P1.02–P1.08 DONE for local acceptance. P1.01 VERIFYING and G1 PENDING until the
  configured hosted CI workflow passes. No push, cloud deployment, model call,
  notification or Phase 2 work. All cross-phase audit findings remain open.

## 2026-10-05 — Saved checkpoint and clean-checkout verification

- Saved local implementation commit `ea8a079` on `codex/phase-1-correctness`.
  No push. Git metadata mutations required sandbox escalation and were approved.
- Cloned that revision with `--no-hardlinks --no-local` into ignored local storage.
  Reused the hash-installed Python 3.12.14 environment and verified Lambda wheels;
  all 147 tests, Ruff lint/format, OpenAPI, secret scan and independent package
  builds pass. ZIP hashes match the original checkout. Clone clean before/after.
- Evidence: `evidence/phase-1/clean-checkout.json`. Local preview server stopped;
  screenshot retained. The only Phase 1 acceptance step left is hosted CI, not
  cloud provisioning. Resume by validating that workflow on the saved source.

## 2026-10-05 — Phase 2 authorized

- User requested Phase 2. Created `codex/phase-2-release-isolation` from `16a523d`.
- Read saved state, Phase 2 acceptance criteria, prior decisions and deployment
  scripts. G1 remains pending hosted CI; proceeding is explicitly user-directed.
- Implement CloudFormation resource plans, environment/role boundaries, immutable
  releases, candidate/promote verification and owned-resource reconciliation.
  Use synthetic inputs until target model, deployment identities and live budget
  are selected. No staging deployment or production qualification is implied.

## 2026-10-05 — Phase 2 infrastructure/release checkpoint

- Added strict inventory and six CloudFormation stage generators; 12 same/split
  region synthetic templates pass cfn-lint. Locked and installed cfn-lint in dev
  dependencies. Original 147 tests pass after runtime scope/secret integration.
- Added versioned build/upload/render and explicit change-set review/execution
  commands. Candidate stacks are create-only; routing is separately gated.
- Added exact metric/region/account/quota checks and owned-resource retirement
  plans. New infrastructure tests cover failures and environment isolation.
- User said “Go ahead” during implementation. Live inputs remain unspecified;
  no cloud calls were made. Continue review and local evidence, keeping staging
  acceptance and G1 hosted CI explicitly pending. See phase-2/NOTES.md.

## 2026-10-05 — Phase 2 local acceptance checkpoint

- Completed P2.01–P2.06 repository work: strict regional inventory/templates,
  separate role scopes, pinned secret versions, qualified Lambda snapshots,
  release-specific agents, reviewed change sets, sealed release stacks, candidate
  canary receipts, telemetry coverage, routing validation and owned retirement.
- Added create-only candidate protections, exact source/artifact/config/schema
  verification, stale-plan checks and explicit synthetic-reference cloud refusal.
  Fixed already-disabled retired alarms blocking future promotion. Retained roles
  and invoke grants with old versions so rollback dependencies remain available.
- Validation: 204 tests (147 previous + 57 new), 12 cfn-lint templates, complete
  six-stage/47-resource reference render, Ruff lint/format, five ShellCheck files,
  both OpenAPI schemas, pip check, Git whitespace and secret scan pass locally.
  System PATH did not expose ShellCheck; used the pinned .venv/bin/shellcheck.
- Updated hash-locked dev dependencies for cfn-lint; pip-audit scanned 93 packages
  with zero known vulnerabilities. Three Lambda ZIP pairs match byte-for-byte;
  all isolated SDK imports pass. Inventory-specific packages also built/verified.
- Published sanitized evidence, operator bootstrap/deployment/sealing/promotion/
  rollback instructions and ownership/import-versus-replace decisions. Raw logs
  and generated synthetic plans remain ignored under .build/ and .local/phase2/.
- No AWS calls, deployment, model invocation, notification, push or CI dispatch.
  P2 tasks VERIFYING; live G2 and hosted G1 remain pending. Roles for future
  ingestion/dispatch/notification are boundaries only; Phase 3 runtime not started.
- Reviewed 23 additional detector fingerprints as generated SHA-256 integrity
  identifiers, verified against source/build evidence; baseline remains exact-match
  only. No real credential was found or added to the baseline.
