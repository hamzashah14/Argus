# Phase 1 — correctness, builds and web UI

Scope: P1.01–P1.08, customer-operated deployment. Local validation uses synthetic
fixtures; no cloud infrastructure, model invocation or notification is needed.
Release isolation, durable incidents, individual identity and production qualification
remain in Phases 2–6. Desktop packaging remains later product work.

## Install and validate

Reference Python: **3.12.14** (`.python-version`). From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/dev.lock
.venv/bin/python -m pip check
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/shellcheck setup-iam.sh setup-lambdas.sh deploy.sh setup-alerts.sh scripts/common.sh
.venv/bin/python scripts/validate_schemas.py
.venv/bin/python -m pytest --junitxml=.build/tests.xml
.venv/bin/python scripts/check_secrets.py
.venv/bin/pip-audit -r requirements/dev.lock --disable-pip --no-deps --format json --output .build/dependency-audit.json
.venv/bin/python -m pip download --require-hashes --only-binary=:all: --dest .build/wheels -r requirements/lambda.lock
.venv/bin/python scripts/verify_build.py
```

Use `requirements/app.lock` for the web application; `requirements/dev.lock` adds
test/scan tools. `requirements/lambda.lock` contains only the deployed runtime SDK
and its dependencies. The root `requirements.txt` includes the app lock; retain
`--require-hashes` when installing it. Regenerate locks intentionally with pip-tools
7.6.1 on Python 3.12 and review the diff; never hand-edit package hashes:

```bash
.venv/bin/pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=requirements/lambda.lock requirements/lambda.in
.venv/bin/pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=requirements/app.lock requirements/app.in
.venv/bin/pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=requirements/dev.lock requirements/dev.in
```

The generated header's `--no-index` reflects this workstation's resolver configuration;
it is a comment, not an installation directive. Regeneration elsewhere requires
access to the operator's trusted package index. `watchdog` is explicit in app.in
so resolution on macOS also includes Streamlit's Linux dependency.

CI (`.github/workflows/ci.yml`) runs these checks on Ubuntu 24.04/Python 3.12.14,
without AWS credentials, and retains test, scan and build evidence for 14 days.
The local runner is macOS; a hosted Linux CI result is still required to close G1.
A vulnerability scan is a point-in-time advisory check, not a security guarantee.

## Configuration migration

- `config.env` is parsed as literal KEY=VALUE data, never sourced as shell. No
  interpolation, command substitution, `export` statements or unknown keys.
- Set EXPECTED_ACCOUNT_ID, MONITOR_REGION and BEDROCK_REGION. Choose ENVIRONMENT
  from development/staging/production. STS must match before a setup script writes.
- Tool deployment now requires INSTANCE_IDS and LOG_CURSOR_SECRET. Generate a
  private per-environment secret with `secrets.token_urlsafe(32)`; keep it stable
  across invocations. Rotation invalidates outstanding discovery cursors.
- Defaults are exported to child processes. `KIRA_PYTHON` can select another Python
  3.12 executable; setup scripts otherwise use `.venv/bin/python`.
- Validate without AWS: `.venv/bin/python -m kira.config config.env --purpose tools`.
  Purposes also include iam, agent and alerts, with their own required fields.
- Production rejects TSTALIASID. Zero reserved concurrency requires explicit
  MAINTENANCE_MODE=true. Neither validation nor that flag verifies cloud capacity.
  The inspected account's quota is 10: the example reservation must be revisited
  before deployment. Capacity/release gates remain P2.05/P3.07/P6.03.
- Commercial AWS partitions only in the current scripts. Environment labels do
  not isolate the current fixed resource names; Phase 2 adds that boundary.

Private `.env`, `config.env`, credentials and real metric catalogs must not enter
Git. Put customer catalogs in the ignored `.local/` directory and set
METRIC_CATALOG_FILE accordingly. Catalogs are bundled into Lambda ZIPs, so treat
customer build artifacts as private too. Never put credentials in descriptors.

## Metric descriptors and contracts

Metric responses now have named datapoints (`timestamp`, `value`) and a descriptor
with namespace, metric name, statistic, exact dimensions and optional unit. Update
custom consumers of the old positional datapoint arrays. Deploy handler and schema
changes together in a development environment; immutable rollout is Phase 2 work.

The default catalog `config/metric-catalog.json` is empty. Built-ins support EC2
InstanceId series, the example CWAgent aggregates, the configured disk path and the
**dimensionless** `AIOpsNginx/nginx-upstream-errors-<instance-id>` Sum series.
Custom process, filesystem and EBS volume series require explicit catalog entries.
See `config/metric-catalog.example.json`: copy it privately and replace every
synthetic identifier/dimension with the dimensions actually published. Do not
assume a per-process series exists at InstanceId-only scope.

Use `metric_id` and `instance_id` to select a custom entry. IDs are deployment
allowlisted; parameter conflicts, unauthorized instances and unsupported namespaces
fail explicitly. A simple alarm's descriptor is preserved in the incident; an
exact matching catalog entry contributes its metric_id to the investigation prompt.
Metric math/composite/percentile alarms are outside this descriptor support.
Manual chat users must provide the configured metric_id for custom series.

`no_data` means the query succeeded without points. HTTP 400 marks invalid input;
HTTP 502 marks upstream/access failure, with a safe error code and reference. It
must not be interpreted as a healthy resource. Unit is omitted for built-ins where
no fixed unit is configured; no unsupported unit is invented.

## Time, pagination and byte limits

- UTC normalization accepts ISO timestamps with Z/offsets and legacy naive UTC
  timestamps. Equivalent offsets query identical windows. Invalid event time
  produces a degraded report without invoking the model; it does not become now.
- Incident records distinguish the source state-change time, raw source text,
  handler receive time and processing time. SNS publication time is separate.
  The alarm transition is not assumed to be the exact onset of the underlying fault.
- Log discovery returns at most 20 groups per service page. Continue next_token
  with the same instance/environment scope until complete=true, including empty
  pages with a token. Tokens expire after one hour and are authenticated.
- The complete tool envelope is limited to 20,000 bytes using conservative escaped
  JSON sizing. Nearest log evidence is retained; truncated results are partial.
  Oversized discovery/error metadata fails explicitly rather than silently losing
  groups. A fixture traverses 300 maximum-length group names without omissions.
- SNS messages, including metadata and the truncation marker, fit 262,144 UTF-8
  bytes. Invalid subjects fail before publication; empty/malformed report bodies
  receive fallback text. Full report storage and durable delivery remain Phase 3.

## UI behavior and limits

Run `.venv/bin/streamlit run app.py --server.address 127.0.0.1`. The setup page works
without AWS resources. Configure the ignored `.env` and your server-side AWS profile,
SSO session or workload role when an agent exists. Do not use real AWS keys in tests.

The refreshed interface provides connection details, investigation prompts, new
conversation/sign-out controls and explicit partial/error states. Client creation
is inside the error boundary, so absent/expired credentials do not crash the page.
Raw provider exceptions are not rendered. A successful request verifies that request
only; configured IDs do not imply connectivity or overall service health.

Limits: 4,000 prompt characters, 32,000 output bytes, 24 history messages,
20 attempts/hour per browser session, 30-minute sign-in lifetime, 2,048 stream
events and a 180-second elapsed check between I/O operations. SDK connect/read
limits are 5/45 seconds, with one total attempt. These are local safeguards;
blocking I/O can overrun elapsed checks, browser resets bypass per-session counters,
and the server does not enforce an account-wide budget. Hard worker deadlines,
individual identity, authorization and distributed work limits have later task IDs.

## Remaining gate and evidence

See `VALIDATION.md` and the main tracker. Hosted CI, actual Bedrock tool invocation,
Linux execution, live telemetry, quotas and notification delivery are not inferred
from mocked local tests. Phase 0 diagnostic scripts must run on preserved Phase 0
source (`badc15e`); current positive regressions live under `tests/`.
