**Kira customer-owned open-source roadmap tracker**

Revised: 1 October 2026. Plan: [OPEN_SOURCE_PRODUCT_PLAN.md](/Users/hamzashoaib/Documents/Side-hustles/AIOps-Agent/OPEN_SOURCE_PRODUCT_PLAN.md). Production baseline: [IMPLEMENTATION_TRACKER.md](/Users/hamzashoaib/Documents/Side-hustles/AIOps-Agent/IMPLEMENTATION_TRACKER.md).

**Confirmed direction:** customer-owned and customer-operated cloud infrastructure; web chat, automatic alert investigations and notifications first; a local macOS/Windows client later. Maintainers provide the open-source project and documentation. Managed services and SaaS commercialization are excluded.

Web/cloud publication track: **0/16 tasks DONE**. Later desktop track: **0/4 tasks DONE**. Production readiness remains **0/52** in its own tracker. All implementation is NOT_STARTED. The scope decision is confirmed; license, desktop technology, signing identity and exact support matrix still require decisions. This revision changes plans only.

The previous 32 OS* tasks are superseded, not completed. CE* is the current namespace. No implementation evidence is lost because no OS task had started. Removed work is recorded below rather than counted as progress.

Status values: NOT_STARTED, IN_PROGRESS, IN_REVIEW, VERIFYING, DONE, BLOCKED. Assign an owner before implementation and attach acceptance evidence before DONE. Update counts manually; link overlapping production work instead of reporting it twice. Earliest next product task: CE1.01. The overall engineering priority remains the production baseline's P0.01.

| Phase | Track | Done / total | Gate status |
|---|---|---:|---|
| CE1 — Reusable customer-cloud deployment | Web/cloud release | 0/4 | NOT_RUN |
| CE2 — Documented web chat and customer onboarding | Web/cloud release | 0/4 | NOT_RUN |
| CE3 — Customer-owned automatic alerts and notifications | Web/cloud release | 0/4 | NOT_RUN |
| CE4 — Qualify and publish the open-source project | Web/cloud release | 0/4 | NOT_RUN |
| CE5 — Local macOS and Windows desktop application | Later desktop phase | 0/4 | NOT_RUN |

**CE1 — Reusable customer-cloud deployment.** Acceptance details are in the plan.

| Task | Deliverable | Prerequisites | Status | Actual owner | PR / evidence | Blocker / next action |
|---|---|---|---|---|---|---|
| CE1.01 | Declare the supported deployment contract | — | NOT_STARTED | — | — | — |
| CE1.02 | Parameterize and package the cloud stack | CE1.01 | NOT_STARTED | — | — | — |
| CE1.03 | Document and test cloud access methods | CE1.02 | NOT_STARTED | — | — | — |
| CE1.04 | Add preflight and safe lifecycle commands | CE1.02, CE1.03 | NOT_STARTED | — | — | — |

**CE2 — Documented web chat and customer onboarding.** Acceptance details are in the plan.

| Task | Deliverable | Prerequisites | Status | Actual owner | PR / evidence | Blocker / next action |
|---|---|---|---|---|---|---|
| CE2.01 | Support local and customer-hosted web UI | CE1.04 | NOT_STARTED | — | — | — |
| CE2.02 | Introduce connection profiles and setup checks | CE2.01 | NOT_STARTED | — | — | — |
| CE2.03 | Document a complete manual investigation | CE2.02 | NOT_STARTED | — | — | — |
| CE2.04 | Verify team access and UI failure behavior | CE2.01, CE2.02, CE2.03 | NOT_STARTED | — | — | — |

**CE3 — Customer-owned automatic alerts and notifications.** Acceptance details are in the plan.

| Task | Deliverable | Prerequisites | Status | Actual owner | PR / evidence | Blocker / next action |
|---|---|---|---|---|---|---|
| CE3.01 | Ship the alert setup and coverage guide | CE1.04 | NOT_STARTED | — | — | — |
| CE3.02 | Ship notification setup and delivery verification | CE3.01 | NOT_STARTED | — | — | — |
| CE3.03 | Document day-to-day operation and recovery | CE3.01, CE3.02 | NOT_STARTED | — | — | — |
| CE3.04 | Prove unattended cloud operation | CE2.04, CE3.03 | NOT_STARTED | — | — | — |

**CE4 — Qualify and publish the open-source project.** Acceptance details are in the plan.

| Task | Deliverable | Prerequisites | Status | Actual owner | PR / evidence | Blocker / next action |
|---|---|---|---|---|---|---|
| CE4.01 | Complete license, security, and repository preparation | CE1.01 | NOT_STARTED | — | — | — |
| CE4.02 | Publish reproducible release artifacts and documentation | CE1.04, CE2.04, CE3.04, CE4.01 | NOT_STARTED | — | — | — |
| CE4.03 | Run independent customer-account validation | CE4.02 | NOT_STARTED | — | — | — |
| CE4.04 | Make the public release decision | CE4.03 | NOT_STARTED | — | — | — |

**CE5 — Local macOS and Windows desktop application.** Acceptance details are in the plan.

| Task | Deliverable | Prerequisites | Status | Actual owner | PR / evidence | Blocker / next action |
|---|---|---|---|---|---|---|
| CE5.01 | Choose and prototype local client packaging | CE4.04 | NOT_STARTED | — | — | — |
| CE5.02 | Implement secure local cloud connections | CE5.01 | NOT_STARTED | — | — | — |
| CE5.03 | Build, sign, and verify desktop releases | CE5.02 | NOT_STARTED | — | — | — |
| CE5.04 | Validate the local-to-cloud workflow | CE5.03 | NOT_STARTED | — | — | — |

**Decision and scope register.**

| Item | Direction | State |
|---|---|---|
| Project ownership model | Open-source project, customer operates own infrastructure | CONFIRMED_BY_USER |
| First functionality | Web chat, automatic alert investigations, notifications | CONFIRMED_BY_USER |
| Desktop sequence | Later local macOS/Windows app connected to customer cloud | CONFIRMED_BY_USER |
| First cloud | AWS, matching the existing code; document support limits | PLANNING_DEFAULT |
| Existing architecture | Retain Bedrock/Streamlit and customer AWS services; harden/generalize | PLANNING_DEFAULT |
| License | Explicit choice before publication; Apache-2.0 remains a proposal | TO_DECIDE |
| Client identity | Customer federation/SSO/role/profile first; tested fallback if required | TO_IMPLEMENT |
| Desktop framework and supported platforms | Choose after local-to-cloud prototype; Tauri is a candidate | TO_DECIDE |
| Publication | Release only after successful qualification and an explicit release decision | PENDING |

**Superseded work from the previous roadmap.**

| Previous scope | Disposition | Reason |
|---|---|---|
| OS6: managed SaaS, billing, tenant operations | REMOVED | User explicitly excludes managed services |
| OS7: fully offline/local backend and model | REMOVED | Local desktop connects to customer cloud; offline engine is not requested |
| OS1/OS2: mandatory portable orchestration and PostgreSQL backend | WITHDRAWN_AS_REQUIREMENT | Customer-owned AWS deployment satisfies the chosen scope |
| OS3: mandatory React/portable Compose product rewrite | WITHDRAWN_AS_REQUIREMENT | Existing UI can be packaged/documented; implementation choice later |
| OS0/OS4/OS5: scope, publication and desktop tasks | REPLACED_BY_CE_TRACK | Preserve relevant objectives under the clarified operating model |

**Production-plan reuse.**

| Production task group | Reused work | CE tasks |
|---|---|---|
| P1 | Configuration, contracts, correctness, repeatable builds | CE1.02–CE1.04, CE2.02–CE2.04 |
| P2 | Isolated infrastructure, scoped roles, immutable releases, reconciliation | CE1.02–CE1.04, CE4.02 |
| P3 | Durable incidents, retry, idempotency, outbox, notifications | CE3.01–CE3.04 |
| P4 | Detection, telemetry health, canary and runbooks | CE3.01–CE3.04 |
| P5 | Identity, access scope, redaction, safety and evaluations | CE1.03, CE2.04, CE5.02 |
| P6/P7 | Qualification, lifecycle, migration and operating instructions | CE1.04, CE4.03, CE4.04 |

**Release evidence register.**

| Milestone | Evidence required | Owner / evidence | Status |
|---|---|---|---|
| Customer-cloud qualification | Production findings closed/accepted under original gates; clean independent account install | — | NOT_RUN |
| Web chat | Local and customer-hosted paths; tested authentication, scope and reports | — | NOT_RUN |
| Unattended alerts | Cloud processing and real notifications with every local client shut down | — | NOT_RUN |
| Open-source publication | License/rights/history review, tagged artifacts, docs, independent tests | — | NOT_RUN |
| Desktop release | Local-to-cloud identity, safe installers/updates, compatibility, sleep/wake tests | — | NOT_RUN |

**Session log.**

| Date | Work | Result | Next action |
|---|---|---|---|
| 2026-10-01 | Initial broad product roadmap | Superseded before implementation | — |
| 2026-10-01 | Applied user clarification: customer-owned open source, web/cloud first, local desktop later | 20 CE tasks defined; zero implementation tasks marked complete | Continue production baseline; establish CE1.01 support contract |
