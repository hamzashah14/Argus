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

Remaining: deployment/role/secret wiring and verified IdP MFA/origin boundary;
distributed user budgets; evidence redaction/retention/deletion; deterministic
output validation; security/diagnostic fixtures and model evaluation; operator
security runbooks. Do not present partial identity implementation as completed
Phase 5 or production qualification. No AWS resources or model calls authorized.

Implementation checkpoint: `0a6ce44` on `codex/phase-5-identity-evidence`, parent
`fff9cb3`. Old and extended releases passed again from the clean code checkpoint
with all four bundle records showing `source_dirty: false`. This confirms packaging
and source binding only; identity deployment support remains unfinished.
