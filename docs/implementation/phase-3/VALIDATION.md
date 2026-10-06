# Phase 3 local validation — 6 October 2026

**Local checks PASS. G3 NOT_RUN; all eight Phase 3 tasks remain VERIFYING.**
This checkpoint implements the durable pipeline and shared owned orchestration
with customer-selectable standalone/AgentCore execution. It does not establish
AWS deployment, production qualification or completed scan-cost acceptance.

Sanitized source/artifact/lock checksums and results:
[local-validation.json](../evidence/phase-3/local-validation.json).
Raw local command logs/builds are ignored under `.build/`; private account evidence
stays separate. No real credentials, inventory, events or cloud responses are
included. Official AWS docs and public dependency advisories were consulted.

## Checks and commands

| Check | Command using `.venv/bin/` | Result |
|---|---|---|
| Regression suite | `python -m pytest -q` | 294 passed |
| Python lint/format | `ruff check .`; `ruff format --check .` | PASS |
| Tool contracts | `python scripts/validate_schemas.py` | Both OpenAPI schemas valid |
| Previous infrastructure | `python scripts/validate_infrastructure.py` | 12 same/split-region templates pass cfn-lint |
| Owned infrastructure | `python scripts/validate_durable.py` | 20 standalone/AgentCore same/split-region templates pass cfn-lint |
| Legacy packages | `python scripts/verify_build.py` | Three independent ZIP pairs identical; isolated imports pass |
| Durable packages | `python scripts/verify_pipeline_build.py` | Six independent ZIP pairs identical; isolated imports pass |
| AgentCore host | `python scripts/verify_agentcore_build.py` | ARM64 ZIP pair identical; pure Python imports pass; live boot pending |
| Inventory-bound tools | `python -m infra build --spec infra/deployment.example.json --output .build/reference-tools --wheelhouse .build/wheels` | PASS; source/catalog/log scope pinned |
| Full release render | `python scripts/verify_durable_render.py --tool-build-dir .build/reference-tools` | Standalone 6 stages / AgentCore 8 stages; all build/bundle bindings verified; synthetic only |
| Secret candidates | `python scripts/check_secrets.py` | No unreviewed candidates; exact checksum false positives reviewed separately |
| Installed dependencies | `python -m pip check` | No broken requirements |
| Shell scripts | `shellcheck setup-iam.sh setup-lambdas.sh deploy.sh setup-alerts.sh scripts/common.sh` | PASS using the virtualenv binary |
| Whitespace | `git diff --check` | PASS |

The unchanged `requirements/dev.lock` was scanned this session with pip-audit:
93 packages, zero known vulnerabilities at scan time. No dependency was added.
Advisory status is time-sensitive, not a permanent security guarantee. CI now
includes both complete release rendering and the ARM64 package; no hosted CI run
or remote push occurred. The installed SDK models recognize AgentCore direct-code
configuration, lifecycle fields and Bedrock CountTokens; this does not prove access.

## What the local tests cover

- Source validation, stable identity, duplicate transitions, conditional claims,
  fenced commits, attempt/retry exhaustion, replay denial and queue-age deadlines.
- Atomic acceptance/outbox, missed-stream repair, ambiguous sends/publications,
  independent initial alerts, paged reconciliation and notification retries.
- Private pinned evidence/checkpoints, bounded reads, checksums and TTL enforcement.
- Exact model input counting and reservation before inference, aggregate allowances
  across attempts, unsupported counting and invalid usage denied before tools,
  observed usage/checkpoints, strict inventory/tool/window/deadline/result limits.
- Both chat targets, remote release/account/endpoint/session binding, SSE closure,
  ambiguous invocation without retry/failover, host HTTP serialization/safe errors,
  thread-start capacity recovery and stale-execution denial.
- Both target IAM/template paths without Classic resources, explicit paid canary
  authorization before cloud access, drift/policy rejection, immutable artifact and
  source checks, and complete synthetic renders through actual local build hashes.

Mocks do not reproduce DynamoDB contention, AWS service behavior or delivery.
The 1,000-transition test covers identity/deduplication keys; it is **not** the
1,000-accepted-incident pipeline accounting/load proof required for G3.

## Required live qualification and limitations

G1 hosted CI, G2 real scoped candidate/permissions/canary/rollback and G3 actual
transactions, concurrent claims/reservations, missed Streams, blocked reads,
worker/host termination, late completions, evidence failures and delivery/load
remain pending. AgentCore needs real ARM64 service boot and version/endpoint checks.
The actual model must support Converse tools and exact CountTokens in its selected
region/profile; unsupported counting fails closed before inference. Capacity must
be resolved given the previously observed regional Lambda quota of 10.

Conservative reservations are not refunded after ambiguity; observed usage can
under-count lost responses. Closing a stream does not prove upstream cancellation.
Notification publisher acceptance is not recipient delivery or exactly-once email.
Query counts/windows and output bytes do not enforce a hard billed scan-byte or
dollar cap. Per-user chat budgets and multi-user identity remain Phase 5. The public
production UI and later desktop application are not finished by this checkpoint.

No project AWS calls, cloud resources, inference or notifications occurred during
local implementation. Synthetic investigations remain paused. All 20 audit findings
remain OPEN; Phase 4 is NOT_STARTED. Continue from [NOTES.md](NOTES.md) and
[STATE.md](../STATE.md), using [GUIDE.md](GUIDE.md) for staging preparation.
