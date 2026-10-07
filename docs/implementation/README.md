# Implementation records

Start with [STATE.md](STATE.md), then [WORK_LOG.md](WORK_LOG.md). The root
`IMPLEMENTATION_TRACKER.md` is the task/gate status authority. These files explain
the evidence and preserve context between sessions.

## Current project overview

[Project evolution and onboarding](../PROJECT_EVOLUTION_AND_ONBOARDING.md) is the concise
before/after guide to phases, current workflows, UI, prerequisites and customer AWS/server setup.
[Phase 5 completion](phase-5/LOCAL_COMPLETION.md) records current local evidence and pending gates.

## Phases 1–4 review

[Engineering review](review-phases-1-4/REVIEW.md) preserves eight historical gaps
and reproductions. [Corrective implementation](review-phases-1-4/CORRECTIONS.md)
records user-authorized batches A–C, regression evidence, bootstrap/replay
procedures, scope correction and pending live gates. R01–R08 remain VERIFYING.
[Floci assessment](review-phases-1-4/FLOCI.md) records exact compatibility gaps
and a cost-conscious local integration proposal. No emulator is installed and
Phase 5 is now locally complete; all six tasks remain VERIFYING with live verification pending.

## Phase 0 records

| Record | Purpose |
|---|---|
| [BASELINE.md](phase-0/BASELINE.md) | Selected source, existing work, reproducibility and recovery |
| [INVENTORY.md](phase-0/INVENTORY.md) | Current architecture, resource ownership and coverage gaps |
| [reference-inventory.json](phase-0/reference-inventory.json) | Explicitly synthetic service/metric inventory |
| [TARGETS.md](phase-0/TARGETS.md) | Provisional reliability, capacity, recovery and budget targets |
| [DECISIONS.md](phase-0/DECISIONS.md) | Selected engineering direction and pending customer choices |
| [PREFLIGHT.md](phase-0/PREFLIGHT.md) | Local observations and deferred live prerequisites |
| [REGRESSIONS.md](phase-0/REGRESSIONS.md) | Reproductions, expected fixes and evidence rules |
| [fixtures.json](phase-0/fixtures.json) | Synthetic inputs used by the diagnostic runner |

## Reproduce the historical Phase 0 baseline

Run these historical commands from a separate checkout at `badc15e`, not from
the updated Phase 1 working tree. Embedded checks were migrated to pytest in Phase 1.
For current commands, use the [Phase 1 guide](phase-1/GUIDE.md).

Use Python **3.12** (verified with 3.12.14). The system Python on the original
workstation was 3.14; do not accidentally use it for the recorded comparison.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r scripts/phase0/requirements.txt
.venv/bin/python scripts/phase0/verify.py --output .local/phase0/baseline-checks.json
.venv/bin/python scripts/phase0/reproduce.py --output .local/phase0/regressions.json
```

The first runner executes the **unchanged 21 embedded self-checks**, parses the
original six Python/three JSON files, and runs `bash -n` on the original five shell
files. The second observes the known defects separately. Both use synthetic data,
mock AWS clients, deny socket connections in the Python test process, and make no
cloud calls. The config fixture sources only a disposable copy of `common.sh`;
it never runs a setup/deploy script. Neither runner exercises the real Streamlit UI.

`scripts/phase0/requirements.txt` freezes the audit SDK environment solely for
reproduction. It is not a production lock, application dependency scan, deployable
artifact or implementation of P1.01. Phase 1 now provides CI, separate application/dev lockfiles, dependency hashes and
packaged Lambda dependencies. Historical evidence remains unchanged.

## Evidence convention

Public synthetic records: `docs/implementation/evidence/phase-<n>/<check-id>.json`
or `.md`. Use stable task/finding IDs, source revision or source hashes, runtime/
dependency versions, command, actual result, expected result, and limitations.
Future CI should upload the same layout plus its build/release manifest.

Private local records: ignored `docs/implementation/evidence/private/`. Never
commit credentials, raw customer logs, real contact details, customer account
inventories or tokens. Summarize capabilities with sanitized identifiers when
referencing private evidence from this folder.

After a code fix, preserve these historical observations. Add positive regression
tests to the discovered suite in the responsible phase. A diagnostic changing to
`NO_LONGER_REPRODUCED` requires investigation; it is not proof of a correct fix.

## Phase 2 records

- [Operator guide](phase-2/GUIDE.md): local preparation and explicit AWS commands.
- [Ownership and migration](phase-2/OWNERSHIP.md): retain/import/replace decisions.
- [Implementation checkpoint](phase-2/NOTES.md): resume context and open gates.
- [Local validation](phase-2/VALIDATION.md): results, reproduction and live acceptance work.

## Phase 4 records

[Checkpoint](phase-4/NOTES.md), [operator guide](phase-4/GUIDE.md), [runbooks](phase-4/RUNBOOKS.md), [local validation](phase-4/VALIDATION.md), [live acceptance](phase-4/ACCEPTANCE.md), and [cost/setup](phase-4/COST.md) describe the current locally verified detection/observability implementation and pending G4.
