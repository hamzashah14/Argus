# Phase 1 validation — 2026-10-05

**Implementation complete; G1 pending hosted CI.** P1.02–P1.08 meet their local
acceptance checks. P1.01 remains VERIFYING until the configured GitHub Actions job
runs successfully against this source. No Phase 2 work has started.

| Check | Result | Scope / evidence |
|---|---|---|
| Pytest | 147 passed | Includes 21 migrated checks and 11 Streamlit AppTest flows; AWS clients and sockets denied by default |
| Ruff lint + formatting | PASS | 48 Python files formatted |
| ShellCheck | PASS | All five deployment/common shell files |
| OpenAPI | PASS | Both specifications and actual success/no-data/partial/error fixtures |
| Configuration | PASS | Minimal defaults, unknown/invalid values, wrong account before mutation, relative paths, catalog validation |
| Metric fixtures | PASS | All six supported built-in alarm descriptors, dimensionless Nginx, custom path/process/volume, exact custom alarm matching |
| Payload/time/pagination | PASS | Equivalent offsets, invalid-time degradation, 300 long log groups, tamper/expiry/scope rejection, full JSON and UTF-8 SNS boundaries |
| Dependency install/check | PASS | Hash-verified dev lock; pip check; Linux dependency metadata closure (not execution) |
| Dependency advisory scan | PASS | Zero known vulnerabilities in the updated lock at scan time |
| Secret candidate scan | PASS | Reviewed synthetic values/checksums only; new synthetic candidate negative control rejected |
| Lambda build | PASS | Three independently rebuilt ZIPs identical; bundled boto3 1.43.106 imports under Python -S |
| Browser review | PASS | Synthetic local login and workspace inspected at 874×954; header spacing corrected; connection remains unverified |
| Hosted CI / Linux runtime | NOT RUN | Workflow configured; no remote push or CI dispatch in this session |
| AWS / production qualification | NOT RUN | No deployment, model call or notification; later phase gates remain open |

Commands are in [GUIDE.md](GUIDE.md). Machine-readable source/lock hashes and build
manifest are in `../evidence/phase-1/`. Raw local JUnit, install and build output
remain in ignored `.build/`. The synthetic UI screenshot is in ignored
`.local/phase1/workspace.jpg`; it contains no customer credentials or inventory.

## Security scan triage

`.secrets.baseline` stores only detector fingerprints, locations and explicit
`is_secret: false` review decisions. CI accepts only exact file/type/fingerprint
matches with that decision; it never automatically updates the baseline. Tracked
and untracked non-ignored files are scanned. Private ignored configuration is not
exported into scan evidence. Hash locks and the baseline itself are excluded.

Reviewed candidates:

- Three synthetic resource names in Phase 0 fixtures/reference inventory.
- Three test password/cursor-key literals, deliberately nonfunctional examples.
- SHA-256 source/artifact/dependency checksums and preserved Git revisions in public
  validation evidence. These are integrity identifiers, not access credentials.

The original six synthetic candidates and 50 historical checksum candidates were
reviewed before creating the baseline; new Phase 1 checksum candidates were checked
against generated evidence before adding their exact fingerprints. A temporary
synthetic secret candidate outside the baseline correctly failed the scanner and
was then removed. No real secret was found or added to the baseline.

## Acceptance limitations and next action

The branch is `codex/phase-1-correctness`, based on `badc15e`. Publish/review the
branch through the repository's normal process and retain a successful
`quality-and-build` run before setting P1.01 DONE and G1 PASS. Local test success
does not establish Linux CI, Bedrock compatibility or production readiness.

The original audit finding register remains open; these local fixes are evidence
for its remediation tasks, not blanket closure of cross-phase findings. Remaining
risks include mutable deployments, direct SNS processing and possible loss on
worker timeout, shared-password access, missing distributed budgets and telemetry
coverage. Their assigned later phases have not been silently advanced.
