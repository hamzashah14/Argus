# Implementation continuity

Before changing this project, read `docs/implementation/STATE.md`, then the
relevant task in `PRODUCTION_IMPLEMENTATION_PLAN.md` and `IMPLEMENTATION_TRACKER.md`.
Read `docs/implementation/WORK_LOG.md` for decisions and previous validation.

- The user selected Phase 0 first, then each phase in order. Do not silently
  advance into another phase or treat planning as implemented behavior.
- Operating model: open-source software deployed and operated in the customer's
  own infrastructure. Web UI/alerts/notifications first; local desktop later.
  No maintainer-operated SaaS or managed services.
- Phase 0 uses synthetic service fixtures. The user subsequently confirmed a new
  AWS deployment with no project infrastructure. Read-only account/region checks
  completed; deployment-specific verification remains in later phases. Read
  `docs/implementation/phase-0/PREFLIGHT.md`; fixtures are not live infrastructure.
- Preserve existing work. The pre-implementation snapshot manifest lives in
  `docs/implementation/evidence/phase-0/baseline-manifest.json`.
- After meaningful work, update STATE, WORK_LOG, task statuses, evidence, and
  next actions. Record commands, results, limits, and blockers without secrets.
- Keep private configuration, credentials, real logs, customer inventory and
  raw cloud responses out of committed evidence. Use the ignored
  `docs/implementation/evidence/private/` directory for local private evidence.
- A local passing test is not live AWS validation or a production qualification.
  Reproduced known defects must remain open until their remediation gates pass.

Direct user instructions take precedence over this continuity guide.
