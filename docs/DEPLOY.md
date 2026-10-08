# Deploy Kira in your AWS account

> **Status.** The deployment tools have only been tested locally. They have never been run
> against a real AWS account, so expect rough edges. Deploy to a staging environment first,
> start with a small pilot, and do not treat the result as production-ready.

Kira runs in your own AWS account. You run the deployment commands from your own workstation,
you pay the AWS bill, and the maintainers operate nothing. This is the only deployment guide.
Follow it in order, from an empty account to a first working UI. Terms are in the
[glossary](ARCHITECTURE.md#glossary).

## Choose your setup

You make three choices. Each has a default. The three defaults together are the shortest path,
and sections 1 to 6 cover that path from start to finish. Read sections 7 to 9 only if you pick
an option.

| Choice | Default (the shortest path) | Option | Where |
| --- | --- | --- | --- |
| Who signs in to the UI | **Local single-user mode.** You run the UI on your own machine and protect it with one shared password. There is no identity provider, grant, session ticket, identity table, signing secret or chat gateway function | **Team sign-in with OIDC.** Your identity provider and MFA, per-person grants, audit records, per-user quotas and a dedicated chat gateway | Section 7 |
| Which model | **Amazon Bedrock** | **A model API:** an OpenAI-compatible or Anthropic Messages endpoint, with its key in AWS Secrets Manager. Your prompts leave your AWS account | Section 8 |
| Which runtime | **`standalone`:** Lambda functions | **`agentcore`:** Amazon Bedrock AgentCore hosts. Bedrock models only | Section 9 |

The options combine freely, with one exception: a model API works only with `standalone`. The
tool rejects the other combination.

Team sign-in is on if, and only if, `runtime.json` contains an `identity` block. `init --identity`
only gives you a starting file that has one.

## Who does what

| Who | What they do |
| --- | --- |
| You, the administrator | Run the commands in this guide and own the AWS bill |
| Your AWS account | Hosts everything Kira creates: Lambda functions, queues, DynamoDB tables, S3 buckets, secrets, alarms |
| Your monitored servers | You install the CloudWatch agent and a heartbeat on each ([SERVERS.md](SERVERS.md)). Kira never installs software on them |
| Your mailboxes | People confirm subscription emails and check that alerts really arrive |
| Your identity provider (IdP), optional | Only with team sign-in: you register Kira's web UI there and enforce MFA. Kira cannot do that for you |
| Your model API provider, optional | Only with a model API: you hold the account and the API key, create the secret that stores it, and pay the provider |

**The whole path (default)**

1. Check the prerequisites (section 1) and read the cost notes (section 2).
2. Set up telemetry on your servers ([SERVERS.md](SERVERS.md)).
3. Install, generate settings, fill them in, dry-run and check (steps 3.1 to 3.5).
4. Run `apply`. It stops at "Candidate ready" (steps 3.6 and 3.7).
5. Resume `apply` with `--allow-model-invocation` to run the paid canary (step 3.7).
6. Confirm the emails and resume until it reports ready (steps 3.7 and 3.8). Then move on to
   [ACCEPTANCE.md](ACCEPTANCE.md).
7. Open the UI on your own machine (section 4).

Team sign-in adds an IdP registration, a first login and a staging ticket (section 7). A model API
adds a secret that you create before `check` (section 8).

## 1. What you need before you start

- [ ] **A workstation and a reviewed checkout.** macOS or Linux (on Windows use WSL), Python 3.12,
  Git, and ideally the AWS CLI to sign in and check which account you are in. Use a clean
  checkout of a reviewed commit. `apply` refuses to run if `git status` shows any change,
  including untracked files.
- [ ] **An AWS account and three existing IAM roles.** Kira creates none of them and never grants
  itself permissions. Ask your security administrator if they do not exist.

  | `deployment.json` field | Role | Used for |
  | --- | --- | --- |
  | `ci_principal_arn` | Operator | The role you run the CLI as. Needs scoped stack and artifact management, passing the execution role to CloudFormation, IAM simulation and policy reads, Secrets Manager describe and version-label actions on the project's secrets, and canary invocation. Team sign-in adds first-user grants |
  | `deployment_role_arn` | CloudFormation execution | Creates the resources. Must explicitly trust `cloudformation.amazonaws.com` |
  | `ui_principal_arn` | UI workload | The identity the web UI runs as. Kira's generated UI role (and, with team sign-in, its session-issuer role) trusts only this role |

  All three must be explicit, different roles in the target account. Use SSO, assumed roles or
  workload roles through the normal AWS credential chain. Never put AWS keys in the JSON files or
  a browser. Do not attach AdministratorAccess to get past a blocker. The `agentcore` runtime needs
  extra permissions (section 9).
- [ ] **Two regions.** A monitor region (alarms, queues, tables) and a Bedrock region (the model,
  plus the read-only tool functions and their secret). They may be the same. Both must be enabled
  in your account.
- [ ] **A Bedrock model that works with Kira.** (Using a model API instead? Skip this item and read
  section 8.) The model must support Converse with tools and the `CountTokens` call for the exact
  request. Not every model does. Model access must be granted in the Bedrock region, and your
  throughput quotas must fit. A catalog entry is not proof. `check` only reads model metadata. The
  paid staging canary is what proves it works.
  [AWS token-count support](https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html).
- [ ] **Lambda concurrency headroom.** Kira reserves `initial_reserved_concurrency` executions for
  initial notifications. AWS requires 100 to stay unreserved. If your limit is low, `check` fails
  with "Reserved concurrency would consume Lambda's required unreserved capacity". Ask for a quota
  increase. Team sign-in reserves 3 more (section 7).
- [ ] **Monitored servers.** Existing Linux EC2 instances (1 to 10) with the CloudWatch agent,
  the right log paths and metrics, a heartbeat if you use observers, and readiness routes.
  `check` fails if a declared instance does not exist. See [SERVERS.md](SERVERS.md).
- [ ] **Mailboxes and a status URL.** A primary address (`notification_email`), a different
  fallback address (`fallback_email`) and a fixed HTTPS `status_base_url` that alert emails link
  to. A laptop's `127.0.0.1` address cannot be a shared link. Expect AWS confirmation emails
  (step 3.7). In default mode the UI runs on your machine, so an email link opens only if its
  address reaches that machine (section 4).
- [ ] **People and approvals.** Name owners for deployment and access, incident response,
  security and data, and budget. Approve retention, model and query limits, and a pilot budget.
- [ ] **A runtime choice.** `standalone` runs on Lambda and is the simpler pilot. Use it unless you
  have a reason to pick `agentcore` (section 9).
- [ ] **Optional extras, only if you choose them.** An OIDC identity provider with MFA (section 7),
  a model API account and key (section 8), or the AgentCore roles and ARM64 build (section 9).

## 2. What it costs

You pay for everything Kira creates. This guide gives no price estimate, because cost depends on
your account, regions, model, fleet, schedules, retention and usage. Review these drivers:

- Bedrock inference (model, tokens, tool calls), and AgentCore if you choose it. With a model API
  you pay the provider instead, outside your AWS bill (section 8).
- CloudWatch log ingestion, Logs Insights queries, metrics, alarms and the dashboard.
- Lambda, DynamoDB (including point-in-time recovery), S3 versioning, KMS, Secrets Manager, SNS
  and SQS, and CloudTrail data events (releases with team sign-in create a trail).

Retained storage, keys and alarms keep costing money even when investigations and observers are
paused. Token reservations and query counts bound the work. They are not a dollar cap. Kira has
no pre-query maximum on the bytes Logs Insights scans, and billing alerts do not shut anything
down.

Before you apply, set a budget alarm for the account in AWS Budgets (Kira does not create one).
After one week of staging, review actual cost by service in Cost Explorer before you enable anything
more. To pause model work and keep alerts, see
[maintenance, pausing and spend](OPERATE.md#maintenance-pausing-and-spend).

## 3. Deploy with the automation tool

This is the primary path. The sequence is: **init, fill three private files, dry-run, check,
apply, finish the named human steps, resume apply.** Every command is safe to rerun. Interrupted
work keeps its progress. Run everything from the repository root.

The tool deploys the backend only. It does not install software on servers, create an EC2 host
for the UI, confirm inboxes, or (with team sign-in) register your IdP.

### 3.1 Install and prepare

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/dev.lock
.venv/bin/python -m pip download --require-hashes --only-binary=:all: --dest .build/wheels -r requirements/lambda.lock
```

The first command installs the deployment tools. The second downloads hash-verified Lambda
packages once. `apply` builds every package (inventory-bound tools, six pipeline functions, the
ARM64 AgentCore host and the observers, when configured) from those wheels. It never installs or
upgrades application dependencies.

Commit the reviewed source before `dry-run`. The plan records the commit, so a new commit after
`dry-run` means a new plan hash. Private files live under `.local/`, which Git ignores.

### 3.2 Generate the private files

```bash
.venv/bin/python -m infra.automation init --work-dir .local/customer
```

This makes the folder (mode 700) and three owner-only files (mode 600). It makes no AWS call and
never overwrites existing files. The work directory must be under `.local/` in this checkout.
Plain `init` copies `infra/durable.example.json` as `runtime.json`, which is local single-user mode.
For team sign-in add `--identity` (section 7).

| File | What it holds |
| --- | --- |
| `automation.json` | Which AWS profile to use, where the other files and the wheels are, and your first user grants (empty in default mode) |
| `deployment.json` | Account, regions, release ID, model, IAM roles, server inventory, Nginx filters, primary recipient |
| `runtime.json` | Status URL, fallback recipient, retention, capacity, model and tool limits. With team sign-in it also holds the OIDC issuer and audience and the usage allowances |

The examples are synthetic (`reference_only: true`, `.invalid` addresses). `check` and `apply`
reject them before they touch AWS. Keep every real value, secret and receipt out of Git.

### 3.3 Fill in the three files

All relative paths resolve against `automation.json`, not your terminal's folder.

**`automation.json`.** It must contain exactly these six keys, or you get "Automation
configuration has unknown or missing fields".

| Key | Value |
| --- | --- |
| `version` | `1` |
| `spec`, `runtime_config` | Paths to `deployment.json` and `runtime.json` (the generated names) |
| `profile` | AWS profile name (letters, digits, `_ . @ -`, up to 128 characters), or `null` for the standard credential chain. A named profile is used for every check and subprocess, and ambient static keys cannot override it |
| `wheelhouse` | Path to the verified wheels. `init` writes the absolute path of `.build/wheels` in your checkout |
| `initial_access` | Must be `[]` in default mode. The tool rejects a non-empty list with "initial_access needs an identity block in the runtime configuration". With team sign-in it holds up to 100 first user grants (section 7) |

```json
{
  "version": 1,
  "spec": "deployment.json",
  "runtime_config": "runtime.json",
  "profile": "customer-deployment",
  "wheelhouse": "../../.build/wheels",
  "initial_access": []
}
```

Run the profile as a session of the operator role (`ci_principal_arn`). `check` fails with "Run
with the configured CI/operator role credentials" otherwise.

**`deployment.json`.** Set `reference_only` to `false`. Keep `executor_mode` at `qualified`.

| Group | Settings and rules |
| --- | --- |
| Names and places | `project`: 2 to 12 lowercase letters or digits, starting with a letter. `environment`: `development`, `staging` or `production` (only `staging` finishes automatically, see 3.8). `account_id`: 12 digits. `monitor_region`, `bedrock_region`. `release_id`: 1 to 16 lowercase letters, digits or hyphens. A release is immutable, so use a new `release_id` for any new code or configuration. Resource names must stay within 64 characters |
| Roles and recipient | `ci_principal_arn`, `deployment_role_arn`, `ui_principal_arn`: explicit, different roles in `account_id`. `notification_email`: the primary address, which must differ from `fallback_email` |
| Model (Bedrock, the default) | `model_id` and `model_arns` (1 to 10 ARNs of a foundation model or inference profile; a profile must belong to your account, and every model behind a profile must also be listed). If `model_id` is an ARN it must be in `model_arns`. To use a model API instead, see section 8: it replaces these fields |
| Switches | `maintenance_mode`: keep `false` (true disables routing). `reserved_concurrency`: leave `null`. 0 needs `maintenance_mode`, and the value is only used for a headroom check |
| Retention | `log_retention_days`: 7, 14, 30, 60, 90, 180 or 365. `log_segment`: empty, or up to 24 letters, digits, `_` or `-`, added to log group names |
| Servers | `instances`: 1 to 10. Each needs `id` (`i-` plus 8 or 17 hex digits), `log_groups` (1 to 8 names of up to 40 letters, digits, `_` or `-`), `disk_path` (absolute path such as `/`), `resource_alarms`, `nginx_alarm`, `process_exe` (`null` or an executable name) |
| Nginx | `nginx_filters.access` and `.error`, each with `pattern`, `match` (a sample line that must match) and `miss` (one that must not). Required even if no instance uses Nginx. See [SERVERS.md](SERVERS.md) |

The telemetry must match the inventory exactly: instance IDs, log groups, metric dimensions
(`InstanceId`, disk `path`, process `exe`). The generated agent examples help, but installing
and configuring agents stays your job.

**`runtime.json`.** Created from `infra/durable.example.json`.

| Group | Settings and rules |
| --- | --- |
| Alerts | `status_base_url`: a fixed `https://` URL. `fallback_email`: a valid address that differs from `notification_email`. It serves both fallback topics |
| Retention and capacity | `retention_days`: 7 to 365. `initial_reserved_concurrency`: 2 to 1000 (capacity kept for initial notifications) |
| Model pause | `investigation_paused`: must be `true`. The tool rejects `false`: "Initial deployment must keep investigation_paused true; activation is a separate qualified release" |
| Runtime | `runtime_target`: `standalone` (default) or `agentcore` (section 9) |
| `runtime_limits` | All eight fields are required. Each is at least 1 and at most: `tokens_reserved` 100000, `model_steps` 16, `tool_calls` 16, `log_queries` 48, `output_tokens` 4096, `window_minutes` 30 (minutes on each side of the incident time), `context_bytes` 64000, `tool_bytes` 20000. `output_tokens` must be below `tokens_reserved`. The example uses 32000, 8, 8, 24, 1024, 15, 48000 and 20000 |

These are limits and reservations, not measured production sizing. Do not add an `identity` or
`security` block unless you want team sign-in (section 7).

**Optional: observers.** Observers add health probes and notification canaries. To use them, copy
the `observability` object from `infra/observability.example.json` into `deployment.json` and fill
it in. That example file also widens `nginx_filters.access` to match 500, 502, 503 and 504. Copy
that too: with observers, the coverage check requires all four. Keep `enabled` at `false` for the
first deployment (it keeps schedules and alarm actions off). Changing it later changes the
release. Every field is required:

| Field | Rule |
| --- | --- |
| `interval_minutes` | 5 to 15 |
| `canary_interval_minutes` | 60 to 1440, in whole hours that divide a day (1440 means daily at 00:00 UTC) |
| `receipt_deadline_seconds` | 300 to 1800, and at least one interval |
| `email_receipt_max_age_hours` | 24 to 168 |
| `services` | 1 to 10. Every instance needs one. Each has `id`, `instance_id`, `owner`, `collector_metric_id`, `heartbeat_log_group`, `freshness_seconds` (300 to 1800) and `routes` |
| `routes` | 1 to 3 per service, each with `id`, `url`, `timeout_seconds` (1 to 5), `latency_ms` (up to the timeout) and `statuses` (200 to 299). The URL is public HTTPS on port 443 with no credentials or query |

`collector_metric_id` must name a declared CWAgent metric on that instance (for example
`INSTANCE_ID-memory`). `heartbeat_log_group` must be one of that instance's `log_groups`, and every
service on an instance shares one. The whole block can be at most 2500 bytes.

### 3.4 Preview without deploying

```bash
.venv/bin/python -m infra.automation dry-run --config .local/customer/automation.json --work-dir .local/customer
```

This makes **no AWS calls and no AWS writes**. It validates your files and writes `plan.json`. It
also writes `collector-examples/INSTANCE_ID.json`, one CloudWatch agent configuration per server.
It prints a `plan_hash`. You need that hash for `apply`.

Read `plan.json` before going on. It lists the ordered steps, stack names and regions, the exact
bootstrap templates, the permission screen and the steps left to you. In default mode the
ordered steps are `foundation-tools`, `foundation-monitor`, `durable-foundation`, `owned-tools`,
`durable-runtime`, `candidate-verification`, `staging-canary`, `routing`,
`registration-verification` and `manual-acceptance`. Observers add their own steps. There are no
identity steps. A model API adds a `model-secret` step before `owned-tools`.

The plan is not a price quote, proof of permissions or a real CloudFormation change set. Later
templates need real outputs, so their exact form appears during `apply`, where each real change
set is inspected and saved privately. Changing any setting or the source commit changes the plan
hash.

### 3.5 Check your account (read-only)

```bash
.venv/bin/python -m infra.automation check --config .local/customer/automation.json --work-dir .local/customer
```

This calls AWS with read-only requests. It checks that you are in the right account and role,
that the three IAM roles exist (and the execution role trusts CloudFormation), that both regions
are enabled, that every declared EC2 instance exists, and Lambda concurrency headroom. With
Bedrock it also reads the model's metadata. With a model API it instead checks that the key secret
exists and has one current version (section 8). Then it simulates the screened actions, including
`iam:PassRole` for the intended service. Any denial, missing context or failed simulation blocks
`apply`. It writes `preflight.json` and exits 0, or 1 with a blocker count. API failures write
`error.json` with the operation and error code only.

This is a conservative screen. It is **not** a complete policy builder or a guarantee. It
cannot see organization policies and session policies. Do not attach AdministratorAccess to clear a
blocker. Have your security administrator review `preflight.json`. See the AWS note on
[IAM policy simulator limits](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html).

### 3.6 Apply the reviewed plan

`apply` creates billable resources. Read `plan.json` first. Use the hash from your own `dry-run`:

```bash
.venv/bin/python -m infra.automation apply --config .local/customer/automation.json --work-dir .local/customer --plan-hash YOUR_PLAN_HASH
.venv/bin/python -m infra.automation status --work-dir .local/customer
```

`apply` checks that the hash and the source match, that the checkout is clean and that the preflight
passes. Then it works through these steps:

1. Builds the packages from the wheels.
2. Creates the foundations: two regional bootstrap stacks, the incident database, evidence storage
   and queues. It collects the outputs and the exact version of the log-cursor secret that AWS
   generates. With a model API it also pins the current version of your key secret (section 8).
3. Uploads versioned artifacts, then creates and seals the immutable tool and runtime releases.
   With observers it also creates the observer stacks and seeds the health checks.
4. Verifies the candidate.
5. **Stops** for the human step in 3.7. It then continues with the canary, routing and
   registration checks, and writes `ui-connection.json` as its last step.

Team sign-in and AgentCore add steps of their own (sections 7 and 9).

A CloudFormation stack is a group of resources managed together. A change set is its preview. The
approved plan authorizes additive steps without a prompt for each one. Every change set is still
inspected against the template, role and account. Deletions, replacements, foreign owners, failed
stacks and drift stop the tool. It never deletes queues, evidence or subscriptions to recover.
Stage names and their immutable or updateable status are in Appendix A.

**Waiting and exit codes.** `apply` waits up to 900 seconds by default and polls every 5 seconds.
Use `--wait-seconds 0` to advance once, or any value up to 3600. When AWS is still working, it
returns `WAITING` with exit code 2. Run the same command again to resume. A human step returns
immediately.

**The work directory.** `.local/customer` holds `state.json` (the resume journal), `bundle/`
(rendered templates and `bundle.json`), `build/`, `bindings.json`, `preflight.json`, change-set
reviews, the canary receipt, `operations.log` and `ui-connection.json`. With team sign-in it also
holds key and grant receipts. Keep it, and never edit or discard the journal to force a retry. A
file lock stops two processes from using one directory. Never run the same release from two
directories at once.

### 3.7 The human steps

`apply` stops for these. None can be skipped.

**A. "Candidate ready" (exit 2).** The backend candidate is built and verified. In default mode the
message is "Candidate ready: resume with --allow-model-invocation". There is no sign-in and no
ticket. Run `apply` again with the same config and plan hash and one more flag:

```bash
.venv/bin/python -m infra.automation apply --config .local/customer/automation.json --work-dir .local/customer --plan-hash YOUR_PLAN_HASH --allow-model-invocation
```

This **spends money**: one bounded model request that calls the staging Investigate function. It
must use both the log and metric tools and return a valid diagnosis. Before it, a coverage check
must pass. Your servers must already publish the metrics, or it stops with "Required metric
unavailable". With a model API, the provider bills this request, not AWS. Because no ticket is
needed, you may add `--allow-model-invocation` to the very first `apply` and skip this stop.
Leave it off the first time if you want to check your telemetry before the paid call.

**B. Confirm the emails.** AWS sends subscription emails. The fallback address gets one for the
incident fallback topic (early in the run) and one for the observation fallback topic if you
configured observers. The primary address gets its email only when the routing stage runs, near
the end. Confirm each one when it arrives. The registration check requires every subscription
to be confirmed, so the first `apply` that reaches routing normally **fails** at that point
with `FAILED` (exit 1) and "infra.durable_ops failed; inspect private operations.log". After you
confirm, run the same command again. Do this within one hour of the canary (see C).

**C. The canary receipt.** A passing canary writes a receipt that is valid for one hour. Every
later `apply` checks it. If it is older, you see "Canary receipt expired/differs". Then you
need `--retry-canary` together with `--allow-model-invocation`, which is a second paid call. A
canary that fails for any reason, even before a model call (for example missing telemetry), is
recorded as ambiguous. After you fix the cause, resume with `--retry-canary` and
`--allow-model-invocation`. Retries keep the previous receipts in the journal.

Two more stops can appear. "Legacy resource retirement requires separate review" means the
retirement plan names alarms or subscriptions to remove. The tool never deletes them, so review
them with the commands in Appendix A. Production environments stop as described in 3.8.

With team sign-in, step A also needs a login and a private staging ticket (section 7).

### 3.8 Status, finished and what comes after

| Status | Exit | Meaning |
| --- | --- | --- |
| `RUNNING` | n/a | A run was interrupted. Run `apply` again |
| `WAITING` | 2 | AWS is in progress, or a named human step is next. Resume with the same config and hash |
| `FAILED` | 1 | A prerequisite, API call or gate failed. Read `operations.log`, `preflight.json` or `error.json` privately, repair, then resume. `AccessDenied` never means "absent" |
| `INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING` | 0 | Provisioning and registration passed. Automatic investigation is still paused |

`status --work-dir .local/customer` prints the status, the next action and the plan hash. It makes
no AWS call. If you change a setting or the commit after `apply` started, the old journal no longer
applies: "Configuration/source changed; create a new deployment work directory". Use a new work
directory and a new `release_id`.

**What finished means.** Only `environment: staging` can reach the last row. It means the backend
exists and is registered. The initial deployment always keeps `investigation_paused` true. It does
**not** mean production qualification, and it does not prove an email reached a person. Do the
inbox and acceptance checks in [ACCEPTANCE.md](ACCEPTANCE.md).

**Other environments.** For `production` or `development` the tool provisions the candidate and
stops with `WAITING`: "Production candidates provisioned; existing gates require separately
qualified staging and production cutover". The message says "production" even for `development`.
No flag continues past it, because the paid canary and the promotion receipt exist only for
staging. In default mode the tool writes no `ui-connection.json` for these environments (it writes
one only at the end of a staging run). This repository has no command that promotes a production
bundle. Qualify a staging release first, then treat production cutover as a separate, reviewed
customer process.

**Enabling automatic investigation** is also outside the tool. It needs a changed release, a new canary
and a reviewed routing change. Appendix A lists the manual commands. They have not been run against
real AWS.

After the last row, open the UI (section 4).

## 4. Open the UI on your own machine

This section is for default mode (team sign-in: section 7). The tool writes `ui-connection.json`
as its last step, so start here when `status` shows
`INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING`.

**1. Give the UI an AWS profile.** The UI process must not use deployment credentials. Its profile
assumes the `ui_role_arn` from `ui-connection.json`. That role trusts only your `ui_principal_arn`.
The launcher checks the account and the assumed role and refuses anything else. A standard AWS
profile looks like this (adjust to how your organization signs in):

```ini
[profile customer-ui]
role_arn = ROLE_ARN_FROM_ui-connection.json
source_profile = A_PROFILE_THAT_ASSUMES_YOUR_UI_PRINCIPAL_ROLE
```

**2. Choose a password and launch.** Default mode signs in with one shared password. Export it in
the shell that starts the launcher. It must have at least 12 characters. The launcher reads no
`.env`, so a value there is ignored, and it prints a hint to stderr if `APP_PASSWORD` is missing.

```bash
read -rs APP_PASSWORD && export APP_PASSWORD   # type a private password; it is not shown
.venv/bin/python scripts/run_customer_ui.py --connection .local/customer/ui-connection.json --profile customer-ui
```

The launcher binds the UI to `127.0.0.1` and copies no AWS credentials. Open the address it prints
(Streamlit's default is `http://127.0.0.1:8501`) and sign in with the password. A password session
ends after 30 minutes. An alert email links to `status_base_url` plus `?incident=ID`. If that
address does not reach your machine, open the same `?incident=ID` on the local address instead.

**What default mode does, and what it does not.**

- Chat runs inside the UI process, with the UI role's AWS credentials. It calls the pinned tool
  functions and the model directly. (With `agentcore` the UI calls the AgentCore endpoint instead,
  section 9.)
- These protections still apply: the instance allowlist (`ALLOWED_INSTANCE_IDS`), pinned tool
  versions, bounded limits (`RUNTIME_LIMITS`), release binding, the diagnostic policy and
  redaction. They come from the generated connection file.
- The only throttle is 20 requests per hour for each browser session. There is no per-person
  identity, grant, audit record or shared quota.

**Do not host a default-mode UI for other people.** It is protected by one shared password. Anyone
who knows that password can start model and tool calls with the UI role's AWS permissions, and can
read every incident report. Keep it on `127.0.0.1`, or put it behind your own SSO or VPN proxy. If
several people need their own access, use team sign-in (section 7).

## 5. Troubleshooting

Most commands print a short, safe message. Details stay in private files: `operations.log`,
`preflight.json`, `error.json` and `state.json` in the work directory. Never paste them into
public places.

| Message or symptom | What it means and what to do |
| --- | --- |
| "Deployment files must live under ignored .local/", "Init never overwrites existing customer files" | `--work-dir` must be inside `.local/` of this checkout. For a fresh start use a new work directory |
| "Synthetic reference inputs cannot check/deploy AWS" | `reference_only` is still `true`, or the examples are unchanged |
| "Deployment failed (ValueError); no success claimed. Inspect private evidence." | A setting in `deployment.json` or `runtime.json` breaks a rule in 3.3, and the automation tool does not say which. Run `.venv/bin/python -m infra.durable --spec .local/customer/deployment.json --config .local/customer/runtime.json --output .local/customer/check-render`. It makes no AWS call and ends with the exact message. Examples: "Invalid deployment field: NAME", "UI, CI and deployment identities must be distinct", "Model ARN must be included in model_arns", "Invalid durable URL, distinct fallback recipient or retention", "Invalid runtime limit: NAME" |
| "Automation configuration has unknown or missing fields", "Invalid AWS profile name", "Supply spec, runtime configuration and verified wheelhouse paths" | `automation.json` must have exactly the six keys in 3.3, with valid values |
| "Initial deployment must keep investigation_paused true; activation is a separate qualified release" | Set `investigation_paused` to `true` in `runtime.json` |
| "initial_access needs an identity block in the runtime configuration", "--access-ticket-file applies only with an identity block in runtime.json" | You are in default mode. Leave `initial_access` empty and do not pass a ticket. For team sign-in, see section 7 |
| "Run dry-run and supply its exact --plan-hash before apply" | Rerun `dry-run` and copy the new hash. Any change to settings or the commit changes it |
| "Apply requires a clean reviewed source checkout" | Commit or remove every change, including untracked files |
| "Wrong AWS account; no writes permitted", "Run with the configured CI/operator role credentials" | The profile points at another account, or is not a session of `ci_principal_arn` |
| "Configured IAM role is absent or has a different path", "Deployment role does not explicitly trust CloudFormation" | One of the three roles is missing at that ARN, or the execution role lacks the CloudFormation trust |
| "A selected AWS region is disabled", "Create/configure the declared EC2 inventory before deployment" | Enable the region. Create the instance, or remove it from the inventory if it is terminated |
| "Reserved concurrency would consume Lambda's required unreserved capacity" | Lower `initial_reserved_concurrency` or raise the Lambda quota |
| "Model profile and its destination models must match declared model_arns", "Model catalog ARN differs from declared model_arns" | Bedrock only. List every model behind the profile in `model_arns` |
| "Create the model API key secret NAME before deploying" | Model API only. The secret does not exist in `bedrock_region`. Create it as in 8.3 |
| "Model API key secret has no unique current version" | Model API only. The secret must have exactly one version labelled `AWSCURRENT` |
| "Bind the exact owned model API key secret ARN and immutable version" | Model API only. The secret's ARN is not `PROJECT-ENVIRONMENT/model-api-key` plus a 6-character suffix in `bedrock_region` and `account_id`. Check the name and region (8.3) |
| "model_api is supported only by the standalone runtime", "MODEL_API is set, but the AgentCore target is Bedrock-only", "AgentCore uses a Bedrock model only; remove MODEL_API." | A model API cannot be used with `agentcore`. Choose one (section 9) |
| "Permission preflight blocked; inspect private preflight.json" | A simulated action was denied. Have your security administrator fix the role, then rerun `check` |
| "Another deployment process owns this work directory" | Another run is active. Wait for it |
| "Configuration/source changed; create a new deployment work directory", "Customer configuration changed during deployment", "Source revision changed during deployment" | Do not edit files or commit during a run. Revert, or start a new work directory (3.8) |
| "Existing stack is not owned by this deployment", "Immutable release exists with a different template; use a new release" | A same-named stack has other tags, or a release already exists with other content. Set a new `release_id` |
| "STAGE: stack needs operator recovery; rollback/failure is not success", "STAGE: change set failed; inspect private AWS events" | Read the stack's events in CloudFormation, then repair it. Never delete retained resources blindly |
| "Change set deletes/replaces resources; separate operator review required" | The tool will not approve this. Review it by hand (Appendix A) |
| "MODULE failed; inspect private operations.log and repair before resuming" | A sub-command failed. After routing it usually means an unconfirmed email subscription (3.7 B). Otherwise read `operations.log` |
| "Required metric unavailable: ID", "Required evidence log group is absent", "Required access metric filter failed its positive/negative fixtures", "Access filter does not cover declared failed-request statuses" | Telemetry is not yet as declared. See [SERVERS.md](SERVERS.md), then resume with `--retry-canary` (3.7 C) |
| "Canary requires explicit paid invocation authorization in staging" | The canary needs `environment: staging` and `--allow-model-invocation` |
| "A private individual-session ticket is required for the staging chat canary", "A canary ticket requires explicit paid model authorization", "Canary ticket and parent directory must be private, with a bounded nonempty ticket" | Team sign-in only. The canary needs a ticket (mode 600, in a folder with mode 700, not a symlink) and `--allow-model-invocation` (section 7) |
| "Owned runtime canary failed", "Canary did not prove both successful tool contracts and model completion" | The function failed or the run stopped early. Read the staging Investigate function's CloudWatch logs in the monitor region. With a model API, common causes are an API host that Lambda cannot reach, a rejected key, a model without tool calling, or a token report that fails Kira's accounting check (8.1). The failed canary is ambiguous (3.7 C) |
| "Canary receipt expired/differs", "Previous paid canary outcome is ambiguous" | See 3.7 C |
| "Legacy resource retirement requires separate review" | Review the named alarms or subscriptions by hand. The tool never deletes them |
| "Routing includes an unexpected or unconfirmed subscriber" | Confirm the pending email subscriptions, then resume |
| "Access administration failed; verify the private inputs, ownership and reviewed source" | Team sign-in only. A `grant-plan` or `grant-apply` input, the owner or the clean checkout is wrong. The message hides the details on purpose |
| "UI profile must assume the generated UI role (or limited staging issuer); do not use deployment credentials", "Connection file must be private (chmod 600) and not a symlink" | Fix the profile (section 4, or 7.8 with team sign-in), or run `chmod 600` on `ui-connection.json` |
| "APP_PASSWORD is not set: export it (12+ characters) in this shell first; .env is not loaded." | Default mode. Export `APP_PASSWORD` before you run the launcher (section 4). The UI page may mention a `.env` file, but the launcher does not read it |
| "Set a valid MODEL_API setting (...)" | The `MODEL_API` setting in the UI environment is malformed. Use the generated `ui-connection.json` unchanged |
| "Set KIRA_AUTH_MODE=oidc, or remove CHAT_FUNCTION_ARN and KIRA_SESSION_TABLE." | The UI environment mixes team sign-in settings with default mode. Use one generated connection file unchanged |
| "Deployment failed (ErrorType); no success claimed" | An unexpected error. Read `error.json` if present, and `operations.log` |

## 6. Next steps

- Prove it works: [ACCEPTANCE.md](ACCEPTANCE.md) (real inbox delivery, fault drills, identity
  checks if you enabled team sign-in, handover).
- Run it day to day: [OPERATE.md](OPERATE.md) (incidents, recipients, access review, rotation,
  backup, rollback, spend).
- Understand the design: [ARCHITECTURE.md](ARCHITECTURE.md). Report a security problem:
  [SECURITY.md](../SECURITY.md).

---

**Sections 7 to 9 are optional. Skip them on the default path.**

## 7. Optional: team sign-in with OIDC

Without this module, the UI uses one shared password and chat runs inside the UI process (section
4). With it, Kira uses your IdP for sign-in (native OIDC in Streamlit) and its own grants for who
may do what. You get MFA, per-person grants, audit records, per-user work allowances and a dedicated
chat gateway function. A grant is keyed by the IdP's issuer and immutable subject, never by email.
There is no public sign-up and no automatic first administrator. Roles are `viewer` (read reports)
and `investigator` (also start investigations), both limited to the instances you list. AWS
deployment rights are separate IAM roles. Revoking, rotating and restoring are in
[OPERATE.md](OPERATE.md#access-review-grants-revocation-and-secret-rotation).

### 7.1 What changes in the main path

| Where | Change with team sign-in |
| --- | --- |
| Prerequisites | An OIDC identity provider with MFA (7.2). Lambda headroom for 3 more reserved executions (2 for investigation, 1 for chat) |
| 3.2 `init` | Add `--identity`, so `runtime.json` starts from `infra/identity.example.json` |
| 3.3 `automation.json` | `initial_access` may list first user grants (7.6) |
| 3.3 `runtime.json` | Add the `identity` block, and review the `security` block (7.3) |
| 3.4 `dry-run` | The plan adds `identity-foundation`, `identity-secret`, `identity-foundation-bound`, `chat-runtime` and `initial-access` |
| 3.6 `apply` | Step 2 also creates the identity table and signing secret, labels the signing version for this release and adds the session-issuer role. Step 3 also creates the dedicated chat release. After candidate verification the tool writes `ui-connection.json` (with the staging issuer role) and applies your `initial_access` grants |
| 3.7 A | The stop says "Candidate ready: configure OIDC, log in with MFA and export the private staging ticket; resume with --allow-model-invocation --access-ticket-file". You sign in once and save a staging ticket (7.9) |
| 4 The UI | Sign-in is OIDC. The launcher drops `APP_PASSWORD` |

The tool follows `runtime.json`. If you add or remove the `identity` block, the release changes.
Use a new work directory and a new `release_id`.

### 7.2 What you need

- An OIDC identity provider with MFA, and an administrator who can register an app in it.
- A way to find each person's immutable `sub` (7.5).
- Headroom for the extra reserved concurrency (7.1).

### 7.3 Settings in `runtime.json`

Start from `infra/identity.example.json` (`init --identity` copies it). It adds two blocks to the
default settings:

| Group | Settings and rules |
| --- | --- |
| `identity` | `issuer`: an `https` URL with no query, fragment or user info, on port 443. `audience`: 1 to 256 characters. Exactly these two keys |
| `security` | Allowances counted per UTC hour, for one user and for everyone: `login_user` and `chat_user` (1 to 100), `login_global` and `chat_global` (1 to 1000), `tokens_user` (up to 1,000,000), `tokens_global` (up to 10,000,000). Also `audit_days` (1 to 90, how long audit records are kept) and `chat_limits` (same fields as `runtime_limits`, charged per chat request). A user value cannot exceed its global value, and `chat_limits.tokens_reserved` cannot exceed `tokens_user`. Keep the whole block, and review the numbers rather than adopting the examples. `security` is allowed only together with `identity` |

### 7.4 Register the app with your IdP

- Register an OIDC web application. Note its issuer, client ID, client secret and discovery URL
  (`.../.well-known/openid-configuration`).
- Register the exact callback `https://YOUR_UI_HOST/oauth2callback`. For a local staging pilot,
  use the loopback address you open in the browser, only if your provider allows it. Hosted use
  needs your HTTPS hostname (Appendix B).
- Enforce MFA. The signed ID token must carry `iss`, a stable `sub`, `aud`, an integer `exp`, an
  integer `auth_time`, and an `amr` list that contains `mfa`. Kira rejects a login older than eight
  hours. Idle sessions end after 15 minutes. A provider that cannot emit these claims needs
  its own tested adapter. Do not remove the checks.
- Put the issuer and audience into `runtime.json` (`identity`). `audience` must equal the token's
  `aud` value, which is the client ID for most providers.

### 7.5 Write the UI secrets and get each user's subject

Create `.streamlit/secrets.toml` on the UI machine. Replace the placeholders and fill both empty
secrets privately. An empty secret is not usable:

```toml
[auth]
redirect_uri = "https://YOUR_UI_HOST/oauth2callback"
cookie_secret = ""
client_id = "YOUR_OIDC_CLIENT_ID"
client_secret = ""
server_metadata_url = "https://YOUR_IDENTITY_HOST/.well-known/openid-configuration"
client_kwargs = { scope = "openid", prompt = "login", max_age = 28800 }
```

Run `chmod 600 .streamlit/secrets.toml`. Make the cookie secret a long random value, different
from the client secret. These two are also separate from the signing and log-cursor secrets that
AWS generates. Never put any of them in the JSON files or in Git. Parameters differ by provider,
so check them against
[Streamlit's OIDC guide](https://docs.streamlit.io/develop/concepts/connections/authentication).
Do not turn on token exposure, and never add identity headers at a proxy.

Then ask your provider's admin tools for each person's immutable `sub`. Do not type an email
address.

### 7.6 Create the first grants

Put each first user in `initial_access` in `automation.json`, as exactly `subject`, `enabled`,
`role` (`viewer` or `investigator`) and `instance_ids` (a unique, non-empty subset of your
inventory). Subjects must be unique. During `apply`, the tool reviews each grant with the same
plan-and-apply procedure as the manual commands. A grant that already matches is left alone. A
grant is tied to one release. A new release needs a reviewed rebinding, which ends that user's old
sessions.

```json
{
  "version": 1,
  "spec": "deployment.json",
  "runtime_config": "runtime.json",
  "profile": "customer-deployment",
  "wheelhouse": "../../.build/wheels",
  "initial_access": [
    {"subject": "replace-with-provider-immutable-subject", "enabled": true,
     "role": "investigator", "instance_ids": ["i-0123456789abcdef0"]}
  ]
}
```

The staging canary needs an `investigator` grant. If `initial_access` is empty, create one by
hand before you sign in, once `apply` has reached "Candidate ready" (the bundle is then the
complete candidate). Use a separately authorized access administrator, who needs read and write
on the identity table limited to `IDENTITY#` keys. `REVIEW_HASH` is the `review_hash` field in
`.local/customer/bundle/bundle.json`:

```bash
umask 077
mkdir -p .local/customer/private
chmod 700 .local/customer/private
# Privately create access-request.json with subject, enabled, role and instance_ids.
.venv/bin/python -m infra.identity_ops grant-plan --bundle .local/customer/bundle --review-hash REVIEW_HASH --request .local/customer/private/access-request.json --output .local/customer/private/access-plan.json
# Review the actor, before and after values, role, scope and epoch.
.venv/bin/python -m infra.identity_ops grant-apply --bundle .local/customer/bundle --review-hash REVIEW_HASH --request .local/customer/private/access-request.json --grant-plan .local/customer/private/access-plan.json --output .local/customer/private/access-result.json
```

### 7.7 The human step: "Candidate ready" with a ticket

This replaces step A in 3.7. `apply` stops with "Candidate ready" (exit 2). The backend candidate
is built and verified. Now you must:

1. Register your IdP and write `.streamlit/secrets.toml` (7.4 and 7.5).
2. Make sure your user has an `investigator` grant (7.6).
3. Configure the UI AWS profile and launch the UI (7.8 and 7.9).
4. Sign in, save the staging ticket, then run `apply` again with
   `--allow-model-invocation --access-ticket-file .local/customer/private/canary.ticket`.
   This **spends money**: one bounded model request through the staging chat function that
   must use both the log and metric tools. Before it, a coverage check must pass.
   Your servers must already publish the metrics, or it stops with "Required metric unavailable".
   The ticket file must exist, be mode 600 in a folder with no group or other access, not be a
   symlink and be 1 to 1024 bytes. You cannot pass the ticket flag on the first `apply`, because
   the file does not exist yet.

A retry needs the same three pieces: `--retry-canary`, `--allow-model-invocation` and a fresh
ticket (3.7 C).

### 7.8 Give the UI an AWS profile

The UI process must not use deployment credentials. Before promotion, its profile assumes the
`staging_issuer_role_arn` from `ui-connection.json`. After the final status in 3.8, it assumes
`ui_role_arn`. Both roles trust only your `ui_principal_arn`. The launcher checks the account and
the assumed role and refuses anything else. A standard AWS profile looks like this (adjust to how
your organization signs in):

```ini
[profile customer-staging-ui]
role_arn = ROLE_ARN_FROM_ui-connection.json
source_profile = A_PROFILE_THAT_ASSUMES_YOUR_UI_PRINCIPAL_ROLE
```

Signing in with OIDC never grants AWS permissions.

### 7.9 First launch and the staging ticket

```bash
.venv/bin/python scripts/run_customer_ui.py --connection .local/customer/ui-connection.json --profile customer-staging-ui --staging-ticket-file .local/customer/private/canary.ticket
```

The private folder is the one made in 7.6 (mode 700). Create it first if you skipped that.

The launcher binds the UI to `127.0.0.1`, reads no `.env`, and copies no AWS credentials. It
drops `APP_PASSWORD`, so a shared password never works in this mode. Open the address it prints
(Streamlit's default is `http://127.0.0.1:8501`) and sign in with MFA. In the
**Operator staging canary** section, click **Save staging canary session**. This works only for an
`investigator`, in `staging`, on a loopback address, in a folder that only you can access. It
writes the ticket with mode 600. Then stop the UI and run the paid `apply` from 7.7.

The ticket is a short-lived bearer credential. Never commit, upload or paste it into logs or
URLs. Export it right before you resume. Delete it afterwards with `rm .local/customer/private/canary.ticket`.
If you see "Access is expired, revoked, or unavailable", check that your grant exists for this
release and that the issuer and audience match.

### 7.10 After the last status, and other environments

After the last row in 3.8, launch the UI again with a profile that assumes the generated
operational role (`ui_role_arn` in `ui-connection.json`, set up as in 7.8), and without the
ticket option:

```bash
.venv/bin/python scripts/run_customer_ui.py --connection .local/customer/ui-connection.json --profile customer-ui
```

For `production` or `development` with team sign-in, the tool also writes `ui-connection.json`
(with only the staging issuer role) and applies your grants before it stops with the `WAITING`
message described in 3.8.

## 8. Optional: use a model API instead of Bedrock

The default model provider is Amazon Bedrock. Choose this option only if you must use another
provider. Kira then calls a model over HTTPS, in one of two protocols:

- `openai`: an OpenAI-compatible Chat Completions endpoint.
- `anthropic`: the Anthropic Messages API.

It works only with the `standalone` runtime. AgentCore stays Bedrock only, and the tool rejects
`model_api` together with `agentcore`. The API key lives in AWS Secrets Manager. You create that
secret yourself, and Kira never writes it.

### 8.1 Read this first: what you accept

- **Your data leaves your AWS account.** The prompts include redacted log and metric excerpts.
  They are sent over HTTPS to the provider you name. Redaction is best-effort, not a guarantee.
  Read the provider's terms for retention, training use and data location before you start.
- **Cost, quotas, rate limits, retention and outages belong to the provider.** They are not on
  your AWS bill, and an AWS budget alarm does not see them. Kira's token limits are not a dollar
  cap.
- **Token accounting is weaker than with Bedrock.**
  - `anthropic`: Kira asks the provider's `count_tokens` endpoint before each call. Anthropic
    documents that count as an estimate. After the call, Kira checks the input tokens the provider
    billed against that count.
  - `openai`: there is no count endpoint. Kira reserves a local estimate: the request size in
    UTF-8 bytes divided by `bytes_per_token` (default 3), plus 64. This is **not an upper bound**.
    A lower `bytes_per_token` reserves more. If the provider later reports more prompt tokens than
    the estimate, Kira stops the run (it fails closed). Those tokens are already billed.
  - A response that reports no token usage stops the run. So does a response that reports
    prompt-cache tokens.
  - Some older OpenAI-compatible servers ignore `max_completion_tokens`. Kira stops a run when the
    reported output is above its limit.
- **It is not proven.** The model API code has only been tested offline against fakes. It has never
  been run against a live provider. How well non-Claude models diagnose incidents has not been
  measured. Before you rely on it, run the paid staging canary (3.7) and the paid diagnostics
  evaluation with the `MODEL_API` setting in your shell
  ([evaluations/diagnostics/README.md](../evaluations/diagnostics/README.md)). After `apply`
  finishes, `ui-connection.json` holds the exact `MODEL_API` value.
- **Network.** Kira's Lambda functions have public internet egress (this project puts none in a
  VPC), so the API host must be reachable from them. In default mode chat runs in the UI process,
  so the machine that runs the UI must reach the API host too, and the UI role can read the key
  version.

### 8.2 Settings in `deployment.json`

Delete `model_arns` (it is forbidden with a model API). Set these fields instead:

```json
"model_provider": "model_api",
"model_id": "PROVIDER_MODEL_NAME",
"model_api": {
  "protocol": "openai",
  "base_url": "https://api.example.com/v1",
  "bytes_per_token": 3
}
```

| Field | Rule |
| --- | --- |
| `model_provider` | `model_api`. The default is `bedrock` |
| `model_id` | The provider's model name: 1 to 128 characters (letters, digits, `.`, `_`, `:`, `/`, `-`), starting with a letter or digit |
| `model_api.protocol` | `openai` or `anthropic` |
| `model_api.base_url` | `https://` plus a DNS host name with a dot, then an optional path of letters, digits and `. _ ~ / -`. No IP address, port, user info, query, fragment or `localhost`. Keep it under 256 characters. Kira adds the endpoint path itself: `openai` appends `/chat/completions` (so the URL usually ends in `/v1`), `anthropic` appends `/v1/messages` (so it usually has no `/v1`). Redirects are not followed, so give the final URL |
| `model_api.bytes_per_token` | Optional, `openai` only: a number from 1 to 8. The default is 3 |
| `model_arns` | Required with Bedrock. Must be absent with `model_api` |
| `bedrock_region` | Still required. It is where the tool functions and the key secret live |

### 8.3 Create the API key secret

You do this once, before `check`. Kira never creates or edits the secret.

- **Name:** exactly `PROJECT-ENVIRONMENT/model-api-key`, using your `project` and `environment`
  (for example `kira-staging/model-api-key`).
- **Place:** your `account_id`, in `bedrock_region`. AWS adds a 6-character suffix to the ARN, so
  the ARN reads `...:secret:PROJECT-ENVIRONMENT/model-api-key-XXXXXX`. Kira rejects any other ARN.
- **Value:** the bare API key and nothing else: no JSON, no spaces, no quotes. It must be 8 to 4096
  printable ASCII characters.
- **Versions:** exactly one version labelled `AWSCURRENT`. A new secret has one.
- **Encryption:** use the default key. Kira adds no KMS permission for this secret, so a secret
  under your own KMS key needs decrypt rights that you add yourself.

Use credentials that may create secrets (add `--profile NAME` if needed). This keeps the key out of
your shell history and removes the file afterwards:

```bash
umask 077
read -rs MODEL_API_KEY                       # paste the key; it is not shown
printf '%s' "$MODEL_API_KEY" > "$HOME/model-api-key.txt"
unset MODEL_API_KEY
aws secretsmanager create-secret --region BEDROCK_REGION --name PROJECT-ENVIRONMENT/model-api-key --secret-string "file://$HOME/model-api-key.txt"
rm "$HOME/model-api-key.txt"
```

You can also create it in the AWS console with the same name and value. To check the result
without reading the key, run:

```bash
aws secretsmanager describe-secret --region BEDROCK_REGION --secret-id PROJECT-ENVIRONMENT/model-api-key
```

The output must show that name, the ARN and exactly one version with `AWSCURRENT` in
`VersionIdsToStages`. The operator role (`ci_principal_arn`) needs `secretsmanager:DescribeSecret`
on `PROJECT-ENVIRONMENT/*` in `bedrock_region`. `check` screens it. The operator role does not need
to read the key.

### 8.4 What `check` and `apply` do differently

- **`check`** makes no Bedrock call. It calls `DescribeSecret` instead. A missing secret blocks it
  with "Create the model API key secret NAME before deploying". `preflight.json` then reports
  `model_catalog_visible: null` and `model_secret_present: true`. `check` does not read the key,
  call the endpoint or test your quota. Only the paid canary proves those.
- **`apply`** runs a read-only `model-secret` step before `owned-tools`. It pins the one current
  version of your secret as `model_secret` in `bindings.json`. It never reads the key value. The
  functions read the key at run time, using that exact version.
- **IAM.** The roles that call the model get `secretsmanager:GetSecretValue` on that secret, limited
  to that one version. They get no Bedrock permissions. In default mode the UI role is one of them.
- **Setting.** Each function receives a `MODEL_API` setting with the protocol, base URL, secret ARN
  and secret version. It never holds the key.

### 8.5 Rotate the key

A release reads the exact secret version it was pinned to, so rotation means a new release:

1. Add a new version of the secret. It becomes `AWSCURRENT`:

   ```bash
   aws secretsmanager put-secret-value --region BEDROCK_REGION --secret-id PROJECT-ENVIRONMENT/model-api-key --secret-string "file://$HOME/model-api-key.txt"
   ```

   Use the same private-file steps as in 8.3, and remove the file afterwards.
2. Choose a new `release_id` and a new work directory. Then run `dry-run`, `check` and `apply`
   again. The new run pins the new current version.
3. Keep the old version until the old release is retired. Retire it as described in
   [OPERATE.md](OPERATE.md).

### 8.6 Qualify it

The paid staging canary (3.7) shows that the key, the endpoint, tool calling and Kira's token checks
work together. Do not skip it. Then run the diagnostics evaluation with the `MODEL_API` setting in
your shell, and have a named person read the results
([evaluations/diagnostics/README.md](../evaluations/diagnostics/README.md)).

## 9. Optional: AgentCore runtime

`standalone` runs on Lambda. `agentcore` runs the work in Amazon Bedrock AgentCore hosts instead.
Set `"runtime_target": "agentcore"` in `runtime.json`. It works only with Bedrock models. A model
API (section 8) is rejected with it.

- **Extra permissions.** The CloudFormation execution role also needs Runtime and endpoint
  management, and `iam:PassRole` with `iam:PassedToService` set to
  `bedrock-agentcore.amazonaws.com`. `check` screens these.
- **ARM64 build.** `apply` builds an ARM64 host package. The manual command is in Appendix A.
- **Default mode.** `apply` creates one AgentCore runtime and endpoint (`agentcore-runtime`,
  `agentcore-endpoint`). The UI calls that endpoint directly with the UI role.
- **Team sign-in.** `apply` also creates a separate chat runtime and endpoint
  (`agentcore-chat-runtime`, `agentcore-chat-endpoint`).
- **The host.** It speaks the AgentCore HTTP `/ping` and `/invocations` contract and binds
  `0.0.0.0:8080` only in AgentCore hosting mode. Never expose it as a public API. Code ships as a
  versioned S3 ZIP on Python 3.12. AWS patches the language runtime, and you update the bundled
  dependencies. A local import check on macOS does not prove a real boot. See
  [AWS direct-code deployment](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html).

## Appendix A: manual commands

Use this to recover or inspect a stuck run, or to do what the tool refuses (enabling
investigation, reviewing deletions). These are the commands the automation runs for you. They have
not been run against real AWS. Pick one path per release. If you start by hand, do not run
`apply` on the same release afterwards.

**Files and names.** Automation and manual use the same file formats.

| Automation | Manual | Notes |
| --- | --- | --- |
| `deployment.json` | `deployment.json` | Same schema |
| `runtime.json` | `runtime.json` (older docs call it `durable.json`) | Same schema. Start from `infra/durable.example.json` (default), or from `infra/identity.example.json` for team sign-in. The `identity` block is what turns team sign-in on |
| `automation.json` | none | Profile, wheel path and first grants are automation only |
| `bindings.json`, written from `state.json` | `bindings.json`, written by you | JSON object of collected outputs. Never invent a value |
| `bundle/`, `build/...` | Any folders you pass | The commands below use the same layout |
| `ui-connection.json` | `.env` | See below |
| `scripts/run_customer_ui.py` | `streamlit run app.py` | The launcher ignores `.env` |
| Plan hash | Review hash | The plan hash guards `apply`. Each rendered bundle has its own review hash |

**Build and render.** Skip the lines that do not apply to you.

```bash
.venv/bin/python -m infra build --spec .local/customer/deployment.json --output .local/customer/build/tools --wheelhouse .build/wheels
.venv/bin/python scripts/build_pipeline.py --output .local/customer/build/pipeline --wheelhouse .build/wheels
# agentcore only (ARM64 host):
.venv/bin/python scripts/build_lambdas.py --function incident_investigate --architecture arm64 --output .local/customer/build/host --wheelhouse .build/wheels
# observers only:
.venv/bin/python scripts/build_observations.py --spec .local/customer/deployment.json --output .local/customer/build/observation --wheelhouse .build/wheels
.venv/bin/python -m infra.durable --spec .local/customer/deployment.json --config .local/customer/runtime.json --output .local/customer/bundle --build-dir .local/customer/build/pipeline --tool-build-dir .local/customer/build/tools
```

Add `--host-build-dir`, `--observation-build-dir` and `--bindings .local/customer/bindings.json`
as they apply. The render prints `review_hash`. **Every re-render changes it.** Commit source
first: mutating commands refuse a dirty tree or a different commit. To use one named profile for
every command, run it as `python -m infra.operator --profile NAME --module infra.durable_ops -- ...`.

**The stage cycle.** Each stack needs these three commands, then a wait. `STAGE` is a stage name
from the table below. Take `CHANGE_SET_ID` from the `Id` in `change-set.json` (or use the name
`review-` plus the first 24 characters of the review hash). `INSPECTED_HASH` is `review_hash` in
`inspected-change.json`. Execution requested is not deployment complete. Wait until CloudFormation
reports `CREATE_COMPLETE` or `UPDATE_COMPLETE` before you collect or seal.

```bash
.venv/bin/python -m infra.durable_ops change-set --bundle .local/customer/bundle --review-hash REVIEW_HASH --stage STAGE --output .local/customer/change-set.json
.venv/bin/python -m infra.durable_ops inspect --bundle .local/customer/bundle --review-hash REVIEW_HASH --stage STAGE --change-set CHANGE_SET_ID --output .local/customer/inspected-change.json
.venv/bin/python -m infra.durable_ops execute --bundle .local/customer/bundle --review-hash REVIEW_HASH --stage STAGE --change-set CHANGE_SET_ID --change-set-hash INSPECTED_HASH --output .local/customer/execution.json
```

Then `collect --stage STAGE --output FILE` reads the stack outputs, and `seal-runtime --stage STAGE`
adds a stack policy and termination protection to an immutable stage. Stage commands take
`--bundle`, `--review-hash` and `--output` in every case.

**Stage order.** Re-render after each binding, and use the new review hash. Stages marked
"release" are create-only, retained and sealed: never update one, publish a new `release_id`.
The others are updateable foundations. Rows that mention team sign-in, a model API or `agentcore`
apply only if you chose that option.

| Step | Stage or command | Save the result as binding |
| --- | --- | --- |
| 1 | `foundation-tools`, `foundation-monitor`, `durable-foundation` (render with empty bindings). Team sign-in adds `identity-foundation` and `identity-secret` | after `durable-foundation`, `collect` as `foundation` |
| 2 | `cursor-version` (read-only). Team sign-in adds `identity-version` (read-only). A model API adds `model-secret-version` (read-only, before step 7) | `secret`, and `identity`, `model_secret` |
| 3 | Team sign-in only: re-render, then run the cycle on `identity-foundation` again (adds `SessionIssuerRole`) | none |
| 4 | Team sign-in only: `infra.identity_ops pin-secret-version` | none. It labels the signing version and refuses to move a label |
| 5 | `upload --artifact-kind tools --build-dir ...` | `tool_artifacts` |
| 6 | `owned-tools` (release), `collect`, then `seal-runtime` | `tools` |
| 7 | `upload --artifact-kind pipeline` (and `host` for agentcore, `observation` for observers) | `artifacts`, `host_artifact`, `observation_artifacts` |
| 8 | agentcore only: `agentcore-runtime`, then `agentcore-endpoint` (release stages, each collected and sealed). Team sign-in adds the same pair as `agentcore-chat-runtime` and `agentcore-chat-endpoint` | `agentcore_candidate` (remove `RuntimeArn`, keep `RuntimeId` and `RuntimeVersion`), `agentcore`, and with team sign-in `agentcore_chat_candidate`, `agentcore_chat` |
| 9 | `durable-runtime` (release). Team sign-in adds `chat-runtime` (release) | `versions`, and `chat_version` |
| 10 | Observers only: `observation-foundation`, `observation-runtime` (release), then `seed-health` | `observation_versions` |
| 11 | `verify-candidate`. Optional reads: `verify-runtime`, `verify-observations` | none |
| 12 | Team sign-in only: first grants (7.6), then the UI and ticket (7.9) | none |
| 13 | `canary --allow-model-invocation`. Team sign-in adds `--access-ticket-file ...` | `--output canary.json` |
| 14 | `retirement-plan --receipt canary.json`. If it names alarms or subscriptions, review them, run `retire --receipt canary.json --retirement-plan FILE`, then get a new, empty plan | none |
| 15 | `routing` with `execute ... --receipt canary.json --retirement-plan FILE` (receipt under one hour old), then `observations` | none |
| 16 | `verify-routing`, `verify-observation-routing`, `collect --stage routing`. Team sign-in adds `collect --stage identity-foundation` | `UiRoleArn`, and `SessionIssuerRoleArn` |

Each binding is exactly the JSON that its command wrote to `--output`. `seed-health` writes
health metrics and may probe approved endpoints, but it runs no model and activates no schedule.
Never use `DEFAULT` or an invented version for an AgentCore endpoint. `--artifact-kind` accepts
`pipeline` (default), `tools`, `host` or `observation`.

**Enabling automatic investigation.** Set `investigation_paused` to `false` in `runtime.json`,
re-render (new review hash), then repeat `verify-candidate`, the canary, `retirement-plan` and the
`routing` cycle. A stale receipt or hash must never be reused. Do this only after
[ACCEPTANCE.md](ACCEPTANCE.md) passes in staging.

**Observer activation and inbox check.** After `routing` and `observations` pass, invoke the pinned
Canary function once (`CanaryVersionArn` in `observation_versions`) with your own AWS tools. The
event body is ignored. It needs `observability.enabled` set to `true` and makes no model call. Wait
for its incident, the initial notification and the test receipt. When the message arrives in the
primary inbox, record it with `attest-email`, using the received notification ID (32 hex digits
followed by `-initial`). The command is in
[OPERATE.md](OPERATE.md#respond-to-an-alert-or-incident). Never attest from a publish log or a
queue receipt. A new recipient voids an attestation, so repeat it at least every
`email_receipt_max_age_hours`.

**UI settings by hand.** Copy the JSON in `Outputs.RuntimeConnection.Value` of
`.local/customer/bundle/routing.json` into `.env` as `NAME=value` lines (see `.env.example`). Add
`MONITOR_REGION`, `INCIDENT_TABLE` (`foundation.TableName`) and `REPORT_BUCKET`
(`foundation.EvidenceBucket`). Do not set `KIRA_IDENTITY_HEADER`, `KIRA_ACCESS_POLICY_FILE` or
`KIRA_SESSION_SIGNING_KEY` (the launcher removes them).

- Default mode: set `APP_PASSWORD` (at least 12 characters). The generated connection has no
  `KIRA_AUTH_MODE`.
- Team sign-in: the generated connection sets `KIRA_AUTH_MODE=oidc`. Do not set `APP_PASSWORD`
  (the launcher removes it). For the canary only, set `KIRA_STAGING_TICKET_FILE` to an absolute path
  in a private folder.

Run `chmod 600 .env` (and `.streamlit/secrets.toml` with team sign-in), then
`.venv/bin/streamlit run app.py --server.address 127.0.0.1`. Real environment variables win over
`.env`. Restart after any change.

## Appendix B: longer tasks

**Hosting the UI for other people.** The tool does not create a UI host. The launcher is for one
person on loopback. For shared use you own the hosting.

- Without team sign-in the only protection is one shared password, and anyone who knows it has the
  UI role's read scope (section 4). Do not host that for others, except behind your own SSO or
  VPN proxy. Prefer team sign-in (section 7).
- Keep Streamlit on loopback behind your own TLS proxy. Do not expose the raw backend origin.
- Forward WebSockets. Accept only your exact public hostname and reject other `Host` and `Origin`
  values.
- Keep Streamlit's CORS and XSRF protection (`.streamlit/config.toml`) and keep
  `trustedUserHeaders` empty. Never let a proxy add identity headers.
- With team sign-in, register the final callback with your IdP and test sign-in again. Alert links
  must resolve through `status_base_url` to this UI, behind sign-in.
- A browser login or token never authorizes direct Lambda, tool or S3 access. Give users the URL
  and sign-in steps only after approval, and never share deployment credentials, passwords or
  session keys.

**Existing resources.** Kira's templates create log groups, topics and storage. If a resource of
the same kind already exists, decide who owns it before you apply. The tool never imports or
takes over foreign resources, and it never deletes them. Keep immutable release stacks and
retained evidence apart from the updateable foundations and routing.
