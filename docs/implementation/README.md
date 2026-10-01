# Implementation records

Start with [STATE.md](STATE.md), then [WORK_LOG.md](WORK_LOG.md). The root
`IMPLEMENTATION_TRACKER.md` is the task/gate status authority. These files explain
the evidence and preserve context between sessions.

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

## Reproduce the baseline locally

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
artifact or implementation of P1.01. Production CI, application/dev lockfiles,
dependency hashes and packaged Lambda dependencies remain Phase 1 work.

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
