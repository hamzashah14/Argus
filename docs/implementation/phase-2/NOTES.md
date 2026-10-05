# Phase 2 implementation checkpoint

Authorized by the user on 2026-10-05; branch `codex/phase-2-release-isolation`,
parent `16a523d`. User subsequently said “Go ahead”; no live model, budget,
recipient or deployment role has been supplied. Local repository implementation is now verified.
No provisioning, notification, model call or Phase 3 work is authorized by these
synthetic fixtures alone. G1 hosted CI remains pending.

## Implemented

- Strict deployment JSON schema and shared fleet/metric/log/CWAgent inventory.
- Six CloudFormation stage generators: tools/monitor foundations, release-specific
  tools+agent, candidate alias, worker version, and stable routing.
- Environment-specific names/tags, private versioned artifact buckets, retained
  logs/versions/secrets, exact inventory log IAM resources and runtime scope checks.
- Pinned Secrets Manager cursor version (no secret value in the release bundle).
- Release tooling: local build/render, owner/region-checked artifact upload,
  create-only candidates, reviewed change sets, preparation/output collection,
  candidate/version/contract checks, explicit paid canary and gated promotion.
- Coverage failure handling, exact paginated metric checks, filter fixture checks,
  quota rejection and per-entry EventBridge failure handling.
- Exact-stack ownership reconciliation, disable obsolete alarm actions before
  CloudFormation removal, remove confirmed retired recipients, preserve unrelated
  resources/history. Local plan/tamper/identity tests are present.
- Legacy mutable shell entrypoints now need development-only explicit opt-in.

## Validation / remaining work

204 tests pass, including 57 new Phase 2 tests. All 12 generated same/split-region
templates pass cfn-lint. Six-stage reference render contains 47 resources. Ruff,
format, ShellCheck, schema, pip, secret and whitespace checks pass. All three Lambda
ZIP pairs reproduce and import their bundled SDK; inventory-specific packages
match generated configuration. Advisory scan: 93 packages, zero known vulnerabilities.

Read [VALIDATION.md](VALIDATION.md) and its sanitized evidence before resuming.
P2.01–P2.06 are VERIFYING; G2 is PENDING live staging. G1 hosted CI also remains
pending. Follow [GUIDE.md](GUIDE.md) and [OWNERSHIP.md](OWNERSHIP.md) for customer
bootstrap, reviewed deployment, migration, sealing, promotion and rollback.

Next: obtain actual customer model/regions/identities/fleet/recipient/budget for an
explicit staging run, or wait for a new phase instruction. Preserve release stacks,
permissions and secret labels through rollback. Do not silently deploy fixtures,
advance to Phase 3 or treat permission-boundary roles as implemented durable ingress.

AWS references checked: CloudFormation Lambda Version/Bedrock Agent/AgentAlias,
Lambda concurrency, EventBridge PutTargets. Numbered Lambda versions are immutable;
IAM role policies and release-specific-name fallback functions still require drift
controls and restricted deployment access. No live compatibility claim is made.
