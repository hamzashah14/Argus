# Phase 5 checkpoint

Started 7 October 2026 by user direction. P5.01 IN_PROGRESS; P5.02–P5.06
NOT_STARTED; G5 NOT_RUN. Earlier live gates remain pending.

First slice: customer-owned OIDC in Streamlit; individually attributed, signed
session references backed by strongly consistent DynamoDB reads and atomic idle
expiry; explicit role/authoritative DynamoDB identity grants checked before backend chat/tool/report
access; logout deletion and policy-epoch revocation. Production/staging cannot
fall back to the shared development password.

Local validation: 459 tests (49 new), 64 existing infrastructure templates,
13 deterministic package pairs/imports and synthetic complete 6/8 and 9/11-stage
release renders pass. Seven OIDC dependencies were added with hashes; existing
pins and Lambda lock are unchanged. Advisory scan: 100 packages, zero known
vulnerabilities. Secret scan: 377 existing reviewed entries, zero new.
See [identity implementation/limits](IDENTITY.md) and
[sanitized evidence](../evidence/phase-5/identity-validation.json).

At the first-slice checkpoint, remaining work was deployment/role/secret wiring
and verified IdP MFA/origin boundary;
distributed user budgets; evidence redaction/retention/deletion; deterministic
output validation; security/diagnostic fixtures and model evaluation; operator
security runbooks. Do not present partial identity implementation as completed
Phase 5 or production qualification. No AWS resources or model calls authorized.

Implementation checkpoint: `0a6ce44` on `codex/phase-5-identity-evidence`, parent
`fff9cb3`. Old and extended releases passed again from the clean code checkpoint
with all four bundle records showing `source_dirty: false`. This confirms packaging
and source binding only; identity deployment support remains unfinished.

## Deployment wiring checkpoint — 7 October 2026

The next slice implements optional identity-enabled releases for both execution
targets. Dedicated retained DynamoDB storage uses KMS encryption, TTL, PITR and
deletion protection, without the incident stream. A separate generated signing
secret is retrieved only by exact ARN/version, with scoped IAM and a bounded
one-minute cache. Identity configuration/key version participate in the release
fingerprint. AgentCore now always receives ENVIRONMENT, eliminating a potential
development-default bypass when deployed remotely.

The limited session-issuer role resolves first-deployment OIDC/canary ordering
without granting model/tool/report access. Operator grant plan/apply commands
enforce scope, increment epochs, preserve disabled tombstones and conditionally
reject concurrent edits. Key pinning retains a release-specific version label
and refuses retargeting. Foundation/actual-role verifiers and post-promotion UI
role checks are implemented and tested with synthetic AWS responses. A staging
investigator can explicitly save a ticket to an owner-only local file from a
loopback UI; production/public bindings and viewer exports are denied.

Local validation: **522 tests (63 new in this slice)**, **82 templates** (64 existing
plus 18 identity-enabled), 13 deterministic package pairs/imports. Actual local
artifact hashes verify old 6/8 and observation 9/11-stage releases plus new
identity 8/10 and identity-observation 11/13-stage releases. Lint/format/shell,
OpenAPI, pip and whitespace pass. No dependency changes; prior 100-package scan
remains the advisory record. Secret scan has zero new candidates after reviewing
exactly three new dummy fixture/documentation entries (380 total); no exclusions
were widened. Details: [evidence](../evidence/phase-5/wiring-validation.json).

[Setup](SETUP.md) documents customer IdP/TLS/workload credentials, phased
foundation binding, key labels, separate grant administration, native staging
ticket/canary, grant cutover and rollback, and the unexecuted live matrix.
No project AWS calls/provisioning, paid inference, notifications, emulator or push.

P5.01 remains IN_PROGRESS: customer IdP/MFA/origin/IAM acceptance is NOT_RUN;
auditable browser/proxy/provider integration is still unqualified. Next engineering
work is P5.02 distributed issuance/chat allowances and automatic/chat capacity
isolation. P5.03–P5.06 remain NOT_STARTED; no Phase 6 advancement or findings closure.
