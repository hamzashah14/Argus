# Phase 4 checkpoint — 6 October 2026

The user explicitly authorized Phase 4. Branch:
`codex/phase-4-detection-observability`, parent `c3297e2` (Phase 3 checkpoint).
No project AWS resources/calls, probes, inference, notifications, push or hosted CI
were performed. Prior account preflight and pending live gates are unchanged.

P4.01–P4.06 are locally implemented and **VERIFYING**. Default observations remain
paused in synthetic fixtures. Do not start Phase 5 without the user's instruction.
This phase supplies customer-owned external HTTPS health and collector freshness,
separate Nginx request/diagnostic counts, atomic recovery links, safe correlated
outcome metrics, operator dashboards, a no-model delivery canary, actual test-queue
receipts, explicit real-inbox attestations and independently watched fallback.

Start with [GUIDE.md](GUIDE.md), [RUNBOOKS.md](RUNBOOKS.md), [COST.md](COST.md),
[VALIDATION.md](VALIDATION.md) and [ACCEPTANCE.md](ACCEPTANCE.md). The original
[DESIGN.md](DESIGN.md) records the chosen boundaries; implementation details and
limits are in the guide. Live G4 is NOT_RUN. All 20 findings stay OPEN; overall
completion remains 13/52 because local verification does not satisfy the remaining
hosted/deployment acceptance gates.

Resume: inspect STATE/WORK_LOG/tracker and git status, then continue approved
Phase 4 staging qualification only when real inputs, IAM/quotas, owners, recipients,
endpoints and a budget exist. Never provision the reference fixture. Existing
standalone/AgentCore choice and the open-source customer-operated model remain.
