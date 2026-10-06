# Phase 4 local validation — 6 October 2026

**Repository checks PASS. G4 NOT_RUN; P4.01–P4.06 VERIFYING.** No production
qualification, hosted CI, customer deployment, paid inference or email receipt
is claimed. Earlier G1/G2/G3 remain pending; all 20 audit findings remain OPEN.

Sanitized checksums and results are in
[local-validation.json](../evidence/phase-4/local-validation.json). Raw local build
logs are ignored under `.build/`; real customer evidence belongs in the ignored
private directory. No new dependencies were introduced; lockfiles remain unchanged.
The previous same-day Phase 3 pip-audit result (93 packages, zero known advisories
at that scan) remains the recorded advisory scan, not a fresh Phase 4 scan.

## Verification

| Check | Command using `.venv/bin/` | Actual result |
|---|---|---|
| Full offline regression suite | `python -m pytest -q` | 349 passed |
| Python quality | `ruff check .`; `ruff format --check .` | PASS |
| Contracts | `python scripts/validate_schemas.py` | Both OpenAPI schemas valid |
| Prior infrastructure | `python scripts/validate_infrastructure.py` | 12 same/split-region templates PASS |
| Owned infrastructure | `python scripts/validate_durable.py` | 20 standalone/AgentCore same/split-region templates PASS |
| Observation additions | `python scripts/validate_observations.py` | 32 extended templates PASS |
| Legacy packages | `python scripts/verify_build.py` | Three deterministic ZIP pairs, isolated imports PASS |
| Incident packages | `python scripts/verify_pipeline_build.py` | Six deterministic ZIP pairs, isolated imports PASS |
| AgentCore host | `python scripts/verify_agentcore_build.py` | One ARM64 ZIP pair, pure Python imports PASS; actual Linux boot pending |
| Observer packages | `python scripts/verify_observation_build.py` | Three inventory-bound deterministic ZIP pairs, isolated imports PASS |
| Tool packages | `python -m infra build --spec infra/observability.example.json --output .build/observation-tools --wheelhouse .build/wheels` | All source/catalog/log-scope hashes verified |
| Old release renders | `python scripts/verify_durable_render.py --tool-build-dir .build/reference-tools` | Standalone 6 / AgentCore 8 stages, reviewed bundle/artifact checks PASS |
| Complete extended renders | `python scripts/verify_durable_render.py --observations --tool-build-dir .build/observation-tools` | Standalone 9 / AgentCore 11 stages, actual local artifact bindings and coverage report PASS |
| Secret candidates | `python scripts/check_secrets.py` | No unreviewed candidates after exact synthetic/checksum review |
| Installed requirements | `python -m pip check` | No broken requirements |
| Shell | `shellcheck setup-iam.sh setup-lambdas.sh deploy.sh setup-alerts.sh scripts/common.sh` | PASS |
| Whitespace | `git diff --check` | PASS |

CI now includes observation template validation, deterministic inventory-bound
packages and both complete extended renders. No hosted CI run or push occurred.

## Faults and boundaries covered locally

- Strict route/config validation; private/metadata/mixed-DNS destinations rejected
  before connect; pinned TLS host; redirects/large bodies/unhealthy statuses fail;
  child timeout kills/reaps the complete route operation without logging payloads.
- Dedicated shipped heartbeat plus exact metric timestamps required; business
  traffic cannot replace heartbeat, no-data/future/naive timestamps cannot be fresh.
- Distinct Nginx 500/502/503/504 access statuses, bytes/status separation and UTC
  parsing; all rendered alarms mapped to evidence/owners in the complete manifest.
- Canary scope and stable UTC slot, expectation before send, initial-only durable
  acceptance with no model WORK, duplicate publish identity and actual conditional
  test-queue receipt. SDK SNS publish acceptance is explicitly insufficient.
- Removed/filtered/unconfirmed subscribers, missing/overdue canary receipt and
  missing/stale/future/old-recipient inbox attestations fail. Maintenance suppresses
  service checks without asserting successful delivery; disabled observers use no AWS.
- Component-only EMF with no customer payloads; incident/fence correlation resets
  between executions; model CountTokens/inference and tool failures are distinct.
- Atomic alarm-state ordering, fractional timestamps, linked recovery and stale
  recovery rejection; authorized incident status exposes recovery fields.
- Qualified observer versions, limited observer writes/no model execution,
  paused schedules, direct fallback/heartbeat alarms, runtime drift verification,
  independent schedule/mapping/alarm/dashboard/subscription drift rejection.
- Existing durable incident, shared orchestration, both runtime adapters, tool,
  UI and deployment regression tests remain passing.

Early test runs caught a missing inbox timestamp guard, reused closed catalog test
fixture and incomplete mocked handoff results; these were fixed and regression
coverage retained. New correlation tests initially had missing test imports; fixed.
Template/render review also corrected the UTC canary schedule, complete alarm
coverage defaults and recipient-scoped attestations before the final checks.

These are mocked SDK and synthetic fixtures, not evidence of actual AWS dimensions,
IAM grants, Linux/ARM64 runtime execution, real Nginx layout or recipient mailboxes.
Run [ACCEPTANCE.md](ACCEPTANCE.md) on the approved frozen staging candidate. Private
network probes, automatic fleet discovery, arbitrary collector formats and external
account/region outage monitoring are not implemented adapters. Runbooks need a
second customer's operator rehearsal. Do not close findings from this file.
