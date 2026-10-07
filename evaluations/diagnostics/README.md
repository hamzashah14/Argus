# Synthetic diagnostic fixtures

The versioned `diagnostics-v1` suite exercises report qualification, redaction and
hostile inputs with synthetic logs and metric descriptors. It contains no customer
data. Offline grading checks reference answers; it does not qualify a Bedrock model.

```bash
python scripts/evaluate_diagnostics.py --output .build/diagnostics-evaluation.json
```

See [evaluations](../../docs/EVALUATIONS.md) for controls, limits and the explicitly
opt-in paid synthetic-model procedure. Keep customer results private.
