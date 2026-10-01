# P0.01 — Source baseline

Date: 2026-10-01. Selected source is the **complete existing working tree**, including
current untracked deployment/configuration templates, before Phase 0 documentation
and harness changes. This is an engineering baseline, not a production release.

Parent revision: `6b91a71e268ce7b0915055fb897073d3379e1ffe` on `master`.
The parent's checkout alone is incomplete for the current application because
several required files were untracked. The source manifest records 25 present files
and SHA-256 hashes; pre-existing deletion of `aiops_all_lambda_code.py`,
`lambda/fetch_health/lambda_function.py` and `schemas/fetch_health.json` is intentional
baseline state for preservation, not a new deletion made in Phase 0.

## Preservation

[baseline-manifest.json](../evidence/phase-0/baseline-manifest.json) records exact
source content, file permissions and Git status. A private local archive is saved
at `.local/baselines/pre-phase-0-2026-10-01.tar.gz`. Its SHA-256 is in the manifest.
It contains source/planning files only; `.git`, credentials, private configuration,
dependencies and caches are excluded. Keep it local; it is not the release package.

To inspect recovery material, first verify the archive hash, then extract into a
**new empty directory** and compare files to the manifest. Never extract over the
working tree. The local commit `1ad38ec1aaff96c4872a653885e33e540742519a` on
`codex/phase-0-baseline` is the portable baseline, including all current application
and deployment files. It intentionally incorporates the user's pre-existing work;
the Phase 0 session itself did not change application behavior.

## Validation and build identity

The application runtime specified by the deployment helper is Python 3.12. The
baseline harness uses Python 3.12.14 and the exact SDK versions in
`scripts/phase0/requirements.txt`. Commands and evidence links are in the parent
[implementation README](../README.md).

Application source hashes in the baseline manifest identify the preserved files.
A clean local clone of `1ad38ec` passed all 21 original self-checks, all 14 original
syntax checks and all ten defect reproductions, and remained clean before/after.
All 18 original application/deployment source files matched the snapshot hashes.
See [checkout-validation.json](../evidence/phase-0/checkout-validation.json).
Dependencies came from the isolated Python 3.12.14 environment created in this
session; this is source reproducibility evidence, not a production artifact build.

Existing tests establish preservation only. The known timestamp, SNS size,
pagination, metric dimension, configuration, contract, deadline and duplicate
processing defects remain in this baseline. No production dependency lock or
cloud artifact has been produced in Phase 0.
