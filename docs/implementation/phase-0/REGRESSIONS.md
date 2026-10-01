# P0.06 — Deterministic reproductions and evidence

The original 21 embedded self-checks are retained unchanged. They establish the
baseline, not the absence of the audit defects. Ten additional observations in
`scripts/phase0/reproduce.py` preserve all eight requested reproduction categories.
Inputs live in [fixtures.json](fixtures.json); generated data stays synthetic.

| Case | Finding / remediation | Baseline observation | Expected corrected behavior |
|---|---|---|---|
| R01 | F03 / P3.02 | Duplicate SNS MessageId repeats investigation and publication | One logical claim/work item, reconcilable notification intent |
| R02 | F01 / P3.05 | Fake stalled stream reaches publication after remaining time goes negative | Independent initial alert, enforced deadline and external recovery |
| R03 | F13 / P1.07 | 100,000 CJK characters exceed SNS UTF-8 limit with metadata | Byte-safe full message, valid subject, safe truncation/fallback |
| R04 | F14 / P1.04 | +05:00 offset is discarded by logs and metrics | Equivalent UTC instants query identical windows |
| R05 | F14 / P1.04 | Malformed alarm time silently becomes current processing time | Raw value retained and explicit uncertainty/degraded outcome |
| R06 | F12 / P1.05 | Dimensionless alarm queried with InstanceId | Exact allowlisted dimension set, including empty dimensions |
| R07 | F15 / P1.06 | 300-group discovery stops at 250 without continuation | Every group reachable through bounded pages and scoped cursor |
| R08 | F15 / P1.06 | Long discovery names exceed body/full-envelope budget | Full UTF-8 envelope fits, including discovery/error metadata |
| R09 | F16 / P1.03 | Required-only config does not export default AGENT_NAME | Validated defaults available to every child before mutation |
| R10 | F20 / P1.02 | Inner datapoint array lacks `items` | Valid full contract and actual success/no-data/partial/error fixtures |

R02 is a deterministic simulated clock jump, not a real AWS timeout. R10 is a
targeted OpenAPI invariant, not a full specification validator. R06 mocks the API
request, not metric existence. R03 captures a mocked publication rather than
sending an oversized notification. These limits remain visible in the evidence.

Results are observations (`REPRODUCED` / `NO_LONGER_REPRODUCED`), separate from the
passing baseline-preservation checks. A runtime exception in the harness fails
the run; an expected known defect is recorded without creating a permanently red
main CI suite. In the responsible phase, add positive acceptance tests and retain
these historical results; never change expected-correct behavior to match a bug.

## Evidence files and retention

- `evidence/phase-0/baseline-manifest.json`: original file hashes and Git state.
- `evidence/phase-0/baseline-checks.json`: runtime/dependencies, source hashes and original checks.
- `evidence/phase-0/regressions.json`: actual observations and expected fixes.
- `evidence/phase-0/checkout-validation.json`: selected revision and clean-checkout verification.

Record the exact command, revision/source hashes, result and limitations. Keep
customer secrets/logs out of public evidence. Future CI artifacts should retain
the release manifest and these check IDs; no CI workflow is added in Phase 0.

## Primary references checked on 2026-10-01

The report fixture uses the SNS documented limit of 262,144 UTF-8 bytes; email
subjects exclude control characters and must be shorter than 100 characters.
[AWS SNS Publish](https://docs.aws.amazon.com/sns/latest/api/API_Publish.html).
The schema fixture checks the required `items` property for array schemas.
[OpenAPI 3.0.3 Schema Object](https://spec.openapis.org/oas/v3.0.3.html#schema-object).
Lambda asynchronous delivery can repeat events, including successful processing;
deduplication must therefore be application-level.
[AWS asynchronous error handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html).
