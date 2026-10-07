# Repository cleanup: current deployment only

7 October 2026. User-authorized maintenance after Phase 5 local completion.
This does not implement Phase 6, deploy AWS or qualify a production release.

## Removed

- Root `deploy.sh`, `setup-iam.sh`, `setup-lambdas.sh`, `setup-alerts.sh` and their
  `scripts/common.sh`/`scripts/deploy_agent.py` implementation.
- Legacy `config.env.example` and static `cwagent-config.example.json`. Current
  inputs are schema-validated private JSON; collector configuration derives from
  the same inventory used for tools/alarms.
- The direct `trigger_investigation` Lambda and its exclusive tests. The durable
  queue/ledger/independent-notification pipeline is the current implementation.
- Agents Classic invocation in UI chat and incident execution, agent/alias fields,
  Classic CloudFormation candidates, permissions, canaries and the old `infra`
  deployment subcommands. `python -m infra` now exposes inventory tool builds;
  deployment operations remain under `infra.durable_ops`.
- Obsolete Phase 2 bundle arguments in the durable CLI and the `release-name`
  executor fallback. Explicit standalone/AgentCore selection and qualified
  numeric versions remain.
- The unguarded cloud sample-log generator and baseline-only Phase 0 runner files.
  They are recoverable in their matching Git revisions; original audit/evidence
  records and the baseline manifest remain intact.
- Legacy README instructions, CI shell checks, obsolete test-specific lint
  exclusions and the unused dependency-free ShellCheck development requirement.
  All other dependency pins and hashes remain unchanged.

## Retained and updated

The UI, shared prompt/contracts, log/metric tools, six incident handlers, three
observation handlers, standalone Python execution and optional separate AgentCore
hosts remain. Both tool regression suites were moved out of `tests/legacy` into
the main test directory; useful original log/metric coverage is preserved.

Tests formerly exclusive to removed Classic APIs were removed or ported to the
current execution/CLI contracts. Regression checks still exercise time/metric
correctness, private output limits, denied access, immutable code/configuration,
source/template tampering, account/inventory boundaries, grants, budgets,
redaction, durable recovery and both runtime targets. Additional tests reject
retired CLI commands/targets before cloud access and reject the removed fallback.

Shared build/receipt/change-review helpers remain in `infra.release`. Shared AWS
client construction moved to `infra.aws` with its existing timeout/retry settings.
The generic service routing template supplies event/alarm/email configuration;
durable routing supplies actual queue mappings, scoped UI permissions and verified
connection outputs. It no longer generates Classic resources before discarding them.

The README now lists only current commands and repository responsibilities.
The administrator checklist remains the complete setup sequence. Phase 1/2 guide
and later validation pages identify historical procedures; they do not instruct
current deployments to run deleted scripts. History is needed for implementation
continuity and remains under `docs/` and Git.

Private `.env`, `.streamlit` secrets, `.local/`, cloud evidence and the user's
untracked logo assets were preserved. No AWS resources were removed or changed.
This cleanup does not migrate a previously deployed Classic installation.

## Validation and limits

Code checkpoint `847b9ae`: 583 regression tests, 90 templates, 12 package/import
pairs, eight clean-source release layouts and 16 reference evaluation cases PASS.
The local development UI was refreshed and login/setup checks passed without AWS
or model calls. Current offline validation evidence is recorded in
[cleanup validation](evidence/phase-5/repository-cleanup-validation.json) and
[WORK_LOG](WORK_LOG.md). The prior 631-test / 94-template / 13-package-pair record
belongs to the pre-cleanup checkpoint. Counts change because obsolete functionality
and its exclusive tests/artifact/templates were removed, not because live gates
passed. Current builds contain two tools, six pipeline functions, one ARM64 host
and three observers: 12 independently reproducible package pairs.

Identity/authentication rules, scopes, budget values, redaction, retention and
notification policies have not been relaxed. P5.01–P5.06 remain VERIFYING, G5
NOT_RUN, all earlier live gates and original findings remain open. Actual AWS,
model, provider, origin, delivery, load and recovery qualification is still pending.

For historical reproductions, use an isolated checkout of the exact documented
revision: baseline scripts at `badc15e`, Phase 2 code at `13db959`, complete Phase 5
at `4d03640`, and the last pre-cleanup documentation at `92e4131`. Do not copy
retired scripts into the current deployment path.
