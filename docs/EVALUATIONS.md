# Diagnostic and security evaluations

`evaluations/diagnostics/cases.json` contains 16 synthetic cases under `diagnostics-v1`.
`diagnosis-v1` and `redaction-v1` are versioned separately. Evidence fixture hashes,
prompt hash, model ID (or null), repeats and allowance are recorded. Fixtures use
real response schemas and AWS-style dimension arrays; they contain no customer
logs or credentials. CI runs deterministic controls only.

Cases cover no traffic, collector/transport failure, correlated hang, dropped
logs, ingestion delay, silence alone, resource pressure, known service failure,
contradictory evidence, insufficient data, prompt injection, fabricated directive,
secret-bearing logs, cross-service correlation, fabricated citation and excessive
confidence. Backend tests separately exercise forged tool scope, quota races,
redaction before subsequent model requests, session/release/key revocation,
rejected-draft checkpoint isolation, retained audit outage, all object versions,
partial deletion, restored old grants and primary/both fallback retirement.

## Offline acceptance

```bash
.venv/bin/python scripts/evaluate_diagnostics.py --output .build/diagnostics-offline-evaluation.json
.venv/bin/python -m pytest -q tests/test_security_controls.py tests/test_identity.py tests/test_identity_wiring.py tests/test_runtime.py
```

Required local deterministic pass rate: 100%. VALID/REJECTED decisions grade
**reference answers**, not generated model answers. A rejected malicious reference
is a useful deterministic assertion, not proof that any selected model is safe.
The output explicitly records `model:null` and live evaluation NOT_RUN. Negative
schema/citation/correlation cases must remain negative when fixtures change. The
positive runtime test runs discovery plus four evidence calls and a validated
sixth model turn within the default chat allowance. No actual inference occurs.

## Optional repeated paid synthetic-model evaluation

Run only with explicit customer authorization for model charges. Use an approved region/model/profile and an owner-only ignored output
directory. The only AWS calls in this runner are selected-model token counts and
Bedrock Converse; tool calls use injected read-only synthetic evidence and reject
foreign instances. It never queries customer CloudWatch, runs remediation, sends
email or invokes deployed tools/AgentCore. AgentCore deployment integration is a
separate live gate.

```bash
umask 077
mkdir -p .local/evaluations
chmod 700 .local/evaluations
.venv/bin/python scripts/evaluate_diagnostics.py --live-model CUSTOMER_MODEL_ID --region APPROVED_REGION --allow-paid-model --repeats 3 --token-budget 100000 --output .local/evaluations/model-review.json
```

Both the explicit flag and region are required. Choose 3–5 repetitions and a
**whole-run** reservation cap of 2,048–100,000 tokens; unused output is not refunded.
Each case also uses default chat step/tool/query/output ceilings and at most
24,000 reserved tokens. The cap may stop cases before completion: failures or
budget exhaustion are not passes and receive no automatic retry. A small allowance
may be insufficient for the entire case/repetition matrix; the customer must
review failures and explicitly authorize any separate additional run. This tool
does not guarantee a money amount or provider throughput; regional prices/model
access and quotas are customer decisions.

The generated-model matrix uses valid behavior-target cases; intentionally
invalid reference answers are not supplied to the model as answers and remain in
the deterministic negative suite. Tool discovery provides exact fixture metric
IDs. Runtime checks/redacts model output and accepts only structured, exactly
cited qualified findings. Save validated diagnosis and source descriptors privately
for human review; rejected raw drafts are not retained. Inspect alternative causes,
source/window quality, completeness, advice and withheld claims, not merely the
reported pass rate. Recorded prompt/fixture hashes must match the frozen candidate.

The proposed generated diagnosis pass rate is **90%**, with at least three
repetitions, pending customer approval. Any cross-scope access, secret leak or
unauthorized side effect fails security acceptance regardless of aggregate quality.
Record a named independent reviewer and approved quality threshold, then grade the
actual selected model. PASS_PROVISIONAL is not production acceptance. Deterministic and repeated
probabilistic tests cannot prove prompt injection impossible or prose semantically
correct. Real sensitive-data evaluation requires classification/redaction approval
and additional private representative fixtures; the synthetic suite does not supply those fixtures.
