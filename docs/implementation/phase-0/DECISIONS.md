# P0.04 — Deployment and security decisions

Recorded 2026-10-01. `CONFIRMED` means a user decision. `SELECTED_FOR_DESIGN`
means an engineering direction from the existing plan, with no deployed behavior.
`PENDING_CUSTOMER` identifies an unresolved live integration input.

| ID | Decision / option | Status | Decision owner / evidence | Blocks or follow-up |
|---|---|---|---|---|
| D00 | Open-source project; infrastructure, credentials, operations and spend belong to each customer; no managed service | CONFIRMED | User's operating-model instruction | Publication/desktop remain CE roadmap |
| D01 | Phase 0 synthetic reference only; real account/regions/model/fleet deliberately unset | CONFIRMED | User's answer in this session | P0.05 live check deferred; P2 cloud work/P6/P7 require actual target |
| D02 | Separate staging/production accounts preferred; scoped resources required even with one account | SELECTED_FOR_DESIGN | Existing plan; engineering custodian Codex | Customer selects accounts; P2.01/P2.02 |
| D03 | AWS SAM/CloudFormation for infrastructure; retain AWS/Bedrock/Streamlit initially | SELECTED_FOR_DESIGN | Existing plan; engineering custodian Codex | Implement in P2; no framework migration in Phase 0 |
| D04 | Customer-hosted web UI; individual SSO/access boundary before broad production access | SELECTED_FOR_DESIGN / PENDING_CUSTOMER | Customer operator selects host, IdP, domain, TLS and approver | P5.01; existing shared password remains a known gap |
| D05 | Initial email independent of model; independent fallback channel and recipient owner | SELECTED_FOR_DESIGN / PENDING_CUSTOMER | Customer operations owner must be named | P3.04/P4.05; no email sent in Phase 0 |
| D06 | Use provisional targets in TARGETS.md for synthetic engineering work | SELECTED_FOR_DESIGN | Codex records proposal; customer approves live load/budget | P0.03 reference recorded; P3.07/P6.03 require actual values |
| D07 | Treat operational evidence as confidential; redact before model/email; default 30-day evidence and 90-day security audit proposals | SELECTED_FOR_DESIGN / PENDING_CUSTOMER | Customer data/security owner chooses classification, residency, retention/deletion | P3.06/P5.03; no present redaction guarantee |
| D08 | Work one phase at a time; maintain reviewable evidence before release | CONFIRMED | User's scope correction | Phase 1 not started by Phase 0 completion |
| D09 | Use workload IAM roles in customer AWS; short-lived profile/SSO credentials locally; narrow static keys only where unavoidable | SELECTED_FOR_DESIGN | Customer security owner assigns identities | P2.02/P5.06; exact IdP/role trust unresolved |
| D10 | Private encrypted evidence, least-privilege KMS access; customer chooses key ownership/rotation and recovery | SELECTED_FOR_DESIGN / PENDING_CUSTOMER | Customer security owner not yet assigned | P2.02/P3.06/P5.06; no new key created |
| D11 | Read-only investigation and human-reviewed recommendations; no automatic remediation in this release | SELECTED_FOR_DESIGN | Existing plan | Any future write tools require a separate design and authorization model |
| D12 | Local desktop client later connects to customer resources; cloud workers provide alerts while desktop is closed | CONFIRMED direction | User's desktop/open-source instruction | CE5; signing, distribution and local credentials later |
| D13 | UI improvements start with honest connection state, safe failures, bounded sessions and clearer interaction | SELECTED_FOR_DESIGN | User requested UI/backend enhancement; P1.08 | Design/implement/validate in Phase 1; no cosmetic work in Phase 0 |
| D14 | Public evidence is synthetic; real inventories/logs/contact details stay in private operator records | SELECTED_FOR_DESIGN | Engineering record owner Codex | Maintain sanitized evidence references for all phases |

The roles above are responsibility slots, not claims that a named production owner
has accepted them. The user/project owner is the reference-scope decision maker;
the eventual deployment operator must name infrastructure, application, notification,
security/data, budget and release owners before their dependent live work.

## Gate interpretation

The user's synthetic selection authorizes repository/reference work and defers
P0.05 live verification. It does **not** turn that task into DONE or make the
original G0 production-requirements gate pass. Record reference readiness and the
live deferral separately. If the user next requests Phase 1, use the plan's allowance
for repository work with synthetic fixtures and carry these unresolved integrations
forward. Do not attempt an unconfigured cloud deployment to make a checkbox green.

The current README is baseline documentation and contains audit-identified
overstatements (safe reruns, tool release isolation, deadline/email guarantees,
silence implying a hang) and unverified pricing. This decision record does not
endorse those statements. Correct each alongside its implementation task; do not
use the old instructions as proof of production safety.
