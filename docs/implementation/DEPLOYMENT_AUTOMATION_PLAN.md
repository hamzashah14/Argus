# Deployment automation implementation track

User-authorized addition after Phase 5 local completion, 7 October 2026. This is
customer deployment tooling, not Phase 6 integration qualification, production
cutover authorization or a recurring Codex automation. Reuses P2.01–P2.06 release
controls, Phase 3/4 bootstrap and Phase 5 identity/chat gates.

| ID | Step | Local status | Required live acceptance |
|---|---|---|---|
| DA.01 | Generate private configuration, validate fields, offline dry-run/hash and collector examples | VERIFYING — implemented locally | Actual customer inventory and role/model/provider choices |
| DA.02 | Read-only account/role/region/inventory/quota/model and permission screen | VERIFYING — implemented locally | Real scoped operator/execution IAM, session/SCP/resource-policy and model checks |
| DA.03 | Build, upload/pin, staged changes, collect/seal, atomic progress and resume | VERIFYING — implemented locally | Both live targets, ambiguous replies/interruption, stack drift and recovery |
| DA.04 | Initial grants, native-session canary handoff, guarded routing and UI connection/launcher | VERIFYING — implemented locally | Real IdP/MFA, scoped role profiles, paid canary, registration and inbox checks |
| DA.05 | Docs, regression/failure tests, evidence and continuity | VERIFYING — implemented locally | Hosted CI and actual customer deployment; no live gate closed |

Implementation: `infra.automation`, `infra.deployment_preflight`, idempotency tokens
in the existing durable commands, `scripts/run_customer_ui.py`. No additional
package, role-policy relaxation, collector installation or maintained hosting.

Operator commands/settings/resume/limits: [deployment guide](../DEPLOYMENT_AUTOMATION.md).
Local results: [sanitized evidence](evidence/deployment-automation/local-validation.json).
All private settings, work journals, cloud replies, access requests, receipts and
canary tickets stay ignored. The initial deployment is paused. Human SSO/inbox
proof and customer security bootstrap remain explicit prerequisites. AWS simulation
is a conservative screen, not full effective authorization. New config/source
requires a new reviewed deployment/release, not journal editing.

Next action: real customer-owned staging qualification only when authorized and
private inputs/roles/inventory/telemetry/provider/budget are ready. Preserve all
existing phase/finding/gate statuses and the user's live-verification deferral.
