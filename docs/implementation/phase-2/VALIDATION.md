> Historical checkpoint: commands/counts below record validation at that phase's
> source revision. The 7 October 2026 cleanup removed root shell deployment scripts
> and Classic support; use current STATE and README for present-day commands.

# Phase 2 validation — 2026-10-05

**Repository implementation passes local checks; G2 is pending live staging.**
P2.01–P2.06 remain VERIFYING against their original acceptance criteria. G1 hosted
CI remains pending. No AWS calls, provisioning, paid canaries or notifications were
performed during Phase 2. No Phase 3 runtime was implemented.

| Check | Result | Scope |
|---|---|---|
| Pytest | 205 passed | 147 previous tests plus 58 infrastructure/release tests; AWS clients and sockets blocked by default |
| CloudFormation lint | 12 templates PASS | Six stages in same-region and split-region configurations; warnings fail the check |
| Complete reference render | PASS | All six stages, 47 resources; actual local packages with explicitly synthetic cloud bindings |
| Python / shell / OpenAPI | PASS | Ruff lint/format, five ShellCheck files, both OpenAPI schemas, Git whitespace |
| Dependency consistency | PASS | Hash-installed dev lock and pip check |
| Advisory scan | PASS | 93 packages, zero known vulnerabilities at scan time |
| Secret scan | PASS | No unreviewed candidates; exact checksum/synthetic-value exclusions only |
| Lambda packages | PASS | Three independent ZIP pairs reproduce byte-for-byte; three bundled SDK imports under Python -S |
| Inventory-specific packages | PASS | All three packages built with generated metric catalog and exact log scope; checked against inventory and current source |
| Release guards | PASS locally | Wrong account, synthetic reference, stale receipt, template tampering, unsealed stacks, changed code/config/model/schema/executor/alias rejected |
| Registration and retirement | PASS locally | Partial target failures, denied/missing metrics, quota/filter failures, changed retirement plans, retired recipients, disabled alarms and routing drift covered |
| Hosted CI / Linux execution | NOT RUN | Workflow extended; no push or dispatch |
| AWS IAM / Bedrock / delivery / rollback | NOT RUN | Customer deployment inputs and staging resources required |

Python: 3.12.14. Bundled boto3/botocore: 1.43.106. Local dependency/security scans
used network package services; test cases and template generation used no AWS.
Raw local output is ignored under `.build/phase2-*`; reference plans are ignored
under `.local/phase2/complete-reference-plan/`. Sanitized results and artifact
checksums are in [local-validation.json](../evidence/phase-2/local-validation.json).

## Reproduction

Use the hash-installed environment and downloaded Lambda wheelhouse described in
the Phase 1 guide, then run:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/shellcheck setup-iam.sh setup-lambdas.sh deploy.sh setup-alerts.sh scripts/common.sh
.venv/bin/python scripts/validate_schemas.py
.venv/bin/python scripts/validate_infrastructure.py
.venv/bin/python -m pytest --junitxml=.build/phase2-tests.xml
.venv/bin/python -m pip check
.venv/bin/python scripts/check_secrets.py
.venv/bin/pip-audit -r requirements/dev.lock --disable-pip --no-deps --format json --output .build/phase2-dependency-audit.json
.venv/bin/python scripts/verify_build.py
.venv/bin/python -m infra build --spec infra/deployment.example.json --output .build/phase2-reference --wheelhouse .build/wheels
.venv/bin/python -m infra render --spec infra/deployment.example.json --output .local/phase2/reference-plan
git diff --check
```

The basic render produces foundations until real or synthetic artifact bindings
are supplied. Tests cover all six stages; `scripts/validate_infrastructure.py`
generates complete synthetic templates for linting. Reference-only inputs cannot
authenticate through the cloud CLI. JSON hashes detect changes relative to the
reviewed plan; they are not signatures against a malicious deployment operator.

## Acceptance work still required

| Task | Implemented locally | Remaining acceptance evidence |
|---|---|---|
| P2.01 | Regional templates, ownership/migration inventory, retained data | Clean staging creation and evidence production is untouched |
| P2.02 | Separate role policies, exact log scope, metric allowlist, pinned secret rotation | Customer IAM bootstrap/review; intended and denied live calls; deployment-role restrictions |
| P2.03 | Deterministic packages, S3 version pins, numeric Lambda versions, sealed release stacks | Create two candidates; prove active version/config unchanged and previous artifacts retrievable |
| P2.04 | Exact tool/schema/prompt/model binding; candidate alias; successful-observation canary gate | Real qualified-executor compatibility and candidate invocation; failed grants preserve active behavior |
| P2.05 | Fail-closed account/quota/telemetry/filter/target checks and receipts | AWS fault injection, telemetry fixtures and actual coverage manifest |
| P2.06 | Exact owned-resource diff, disable before removal, recipient retirement and shared CWAgent inventory | Live host/feature/recipient changes, former recipient exclusion and rollback rehearsal |

Before staging, select the actual model/profile and model ARNs, account/regions,
three bootstrap identities, fleet, notification recipient and budget. The previous
account concurrency limit of 10 still needs a capacity decision. A null reservation
does not cap spending. Follow [GUIDE.md](GUIDE.md); keep raw cloud evidence private.

Remaining architecture limits are explicit: the worker still processes SNS directly;
Phase 3 owns persistence, dispatch, independent initial alerts and delivery recovery.
Ingestion/dispatch/notification roles define permission boundaries only. Stack seals
cannot prevent a privileged administrator from making direct service changes.
Metric IAM scoping relies partly on application inventory checks. Real Bedrock trace
format, email confirmation and service quotas remain unverified. All audit findings
stay open until their mapped remediation gates pass.
