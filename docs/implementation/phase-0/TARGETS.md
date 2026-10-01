# P0.03 — Reference acceptance targets

All numbers below are **tentative engineering targets**, not an SLA, observed
capacity, price estimate or authorization to incur costs. They make later tests
concrete. A customer operator must replace/approve them before live qualification.
Engineering record owner: Codex in this work session. Production reliability,
notification and budget owner: customer operator, named person still required.

| Area | Proposed reference target | How to establish evidence |
|---|---|---|
| Critical HTTP failure detection | Within 2 minutes for the reference health endpoint | Timed probe failure/recovery tests, separate from pipeline latency (P4/P6) |
| Initial notification | p95 ≤60 seconds from durable ingress, including queue delay | Persist ingress/publish times; verify controlled recipient separately |
| Investigation outcome | Complete **or explicitly degraded**, with follow-up intent, within 10 minutes of durable ingress | Include model outage, throttle, queue wait, tool failure and worker death |
| Accepted-event accounting | 100% of unique accepted fixture events reach terminal or explicit recoverable state | Reconcile source event IDs to state records, including duplicates |
| Normal model attempt | ≤7 minutes; proposed Lambda ceiling ≤8 minutes | Deadline prototype and cancellation/reconciliation tests in P3.05 |
| Overdue reconciliation | ≤1 minute scan interval proposed | Kill/expire workers and verify recovery within overall budget |
| Steady automatic load | 1 unique incident/minute for 30 minutes | Record backlog, p95 latency, outcomes and model/query spend |
| Burst load | 10 unique incidents in 60 seconds; add 20% duplicate deliveries | Initial alerts must keep their target; excess model work gets explicit degraded state by deadline |
| Model concurrency | 2 investigation workers initially; notification capacity independent | Bound paid work and prove notifications survive worker saturation |
| Chat load | 2 simultaneous users, 5 turns/hour/user in reference tests | Measure timeouts, input/output limits, fairness and isolation |
| Recovery | Reconcile overdue work ≤2 minutes after a healthy reconciler returns | Inject worker/dispatcher failure; no silent orphaned incident |
| Infrastructure disaster recovery | Tentative restore RTO 4 hours; backup RPO 24 hours | Restore rehearsal in customer staging; distinct from ordinary queue/worker recovery |
| Cost budget | USD 50/month **placeholder ceiling for a small pilot** | Customer replaces with actual budget and region/model calculation; no pricing claim |
| Spend controls | Proposed alerts at 50/80/100%; at approved cap pause new paid model work, preserve initial alerts | Customer policy and enforcement tests; not implemented |
| Retention | Proposed logs/reports/incident records 30 days; private security audit 90 days | Classify data first, then test expiry/access/deletion; compliance may require different values |
| Notification | Customer-confirmed email initially; independent fallback route required | SNS publish acceptance is separate from inbox delivery or human acknowledgement |
| Staging observation | 3–7 consecutive calendar days after failure/load/rollback tests | P6.05 release evidence, not simulated elapsed time |

Ten simultaneous investigations cannot be assumed to finish within ten minutes
with two slow model workers. This profile deliberately requires admission control,
bounded queue age and truthful degraded outcomes; initial alerts remain independent.
Full-report success rate and latency will be measured before setting a stronger
customer commitment. Recovery/backup values must also be reconciled with a real
customer's loss tolerance before production.

Use at least 1,000 synthetic records across the fault scenarios for accepted-event
accounting in Phase 3/6. Do not make 1,000 billable model calls merely to satisfy a
fixture count. A small separately budgeted live test establishes AWS semantics;
synthetic tests establish deterministic state transitions and failure handling.

These targets are documented now; the current application does not enforce them.
