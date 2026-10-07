Versioned synthetic suite for Phase 5. These cases validate controls and report
grading, not a real model's diagnostic accuracy. Fixtures contain synthetic
instance IDs, example.invalid sources, invented symptoms and canary secret
markers. No customer evidence is allowed here.

Run `python scripts/evaluate_phase5.py --output .build/phase5-evaluation.json`.
Default execution is entirely offline and creates no AWS client. Expected reports
are reference answers, not outputs produced by a model. Repeated paid model
evaluation is opt-in, must use a customer-approved model/region and private output,
and remains NOT_RUN until explicitly performed. See the [Phase 5 evaluation guide](../../docs/implementation/phase-5/EVALUATIONS.md).
