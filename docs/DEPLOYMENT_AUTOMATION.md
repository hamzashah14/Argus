# Deployment automation and settings

Customer-owned backend deployment, implemented locally after Phase 5. Live AWS
qualification remains pending. This CLI does not install software on monitored
EC2 instances, create an EC2 UI host, register an identity provider or operate a
managed service. Run it from a clean, reviewed macOS/Linux checkout with Python
3.12 and the project's locked dependencies; Windows administrators can use WSL.

The normal sequence is **init → fill private configuration → dry-run → check →
apply → complete the named human dependency → resume apply**. Interrupted AWS
operations retain progress. Completed provisioning is distinct from production
acceptance: the initial deployment keeps automatic investigations paused.

## 1. Generate settings

```bash
.venv/bin/python -m infra.automation init --work-dir .local/customer
```

This creates owner-only JSON templates without AWS access. It never overwrites
existing files. The examples remain `reference_only: true` until replaced with
actual customer values; `check` and `apply` reject synthetic inputs before AWS.
No AWS key, password, provider secret or session ticket belongs in these files.

| File | Settings to provide |
|---|---|
| `.local/customer/automation.json` | Credential profile, locations of the other files and verified wheelhouse; initial user access requests |
| `.local/customer/deployment.json` | Account, regions, project/environment/release ID, model ID and allowed model ARNs, existing EC2 inventory, telemetry/filter expectations, roles and notification recipient |
| `.local/customer/runtime.json` | Standalone/AgentCore, fixed HTTPS UI/status URL, distinct fallback email, retention, initial notification capacity, model/tool limits, OIDC issuer/client ID and work/security budgets |

All relative paths resolve against `automation.json`, not the terminal's current
directory. The generated wheelhouse path points to `.build/wheels` in the checkout.
Prepare hash-verified Lambda wheels once if they are not available:

```bash
.venv/bin/python -m pip download --require-hashes --only-binary=:all: --dest .build/wheels -r requirements/lambda.lock
```

`apply` then builds inventory-bound tools, six pipeline functions, optional ARM64
AgentCore host and optional observers automatically, using the verified wheels.
It does not install or upgrade application dependencies.

**AWS identity and roles.** Use a customer credential profile/SSO role session
that assumes the spec's `ci_principal_arn`. `profile: null` uses the standard SDK
credential chain; a named profile is used consistently by checks and subprocesses,
without inherited static credentials overriding it. The distinct CI/operator,
UI workload and CloudFormation execution roles must already exist. The execution
role must explicitly trust CloudFormation and have scoped infrastructure creation
permissions; the operator needs the scoped deployment/verification, simulation,
key-label, initial-access and canary operations. This tool does not grant itself
administrator permission or change organizational policies. A customer security
administrator must establish these identities first if they do not exist.

Example automation-file shape (keep real values private):

```json
{
  "version": 1,
  "spec": "deployment.json",
  "runtime_config": "runtime.json",
  "profile": "customer-deployment",
  "wheelhouse": "../../.build/wheels",
  "initial_access": [
    {
      "subject": "replace-with-provider-immutable-subject",
      "enabled": true,
      "role": "investigator",
      "instance_ids": ["i-0123456789abcdef0"]
    }
  ]
}
```

Use immutable provider subjects, not email addresses. Grants use the configured
issuer and a unique subset of inventory. The automation reviews/applies each
initial grant through the existing conditional identity APIs, and does not bump
epoch when an already matching grant is encountered during resume. An empty list
requires an access administrator to use the existing reviewed grant commands
before native staging login. Existing grants are release-specific; review the
plan carefully because rebinding a grant invalidates old-release sessions.

**Deployment inventory.** Set actual account ID/regions and `reference_only: false`.
Keep `executor_mode: qualified` and `investigation_paused: true`. Choose
`runtime_target: standalone` for the simpler deployment, or `agentcore` for
independent incident/chat AgentCore hosts. Use a new release ID for new code or
configuration; immutable releases cannot be edited in place. Existing EC2
instances, configured telemetry, and valid CloudWatch dimensions must match the
inventory. The tool supplies collector examples; installing/configuring agents
and the application's telemetry remains the administrator's responsibility.
See the [administrator checklist](ADMINISTRATOR_SETUP_CHECKLIST.md) for exact
log, metric, heartbeat and Nginx requirements.

**SSO and secrets.** The runtime file holds only issuer/audience references.
Register the OIDC client, exact callback, provider MFA/claims and allowed origin
with the customer's IdP. Put client/cookie secrets in owner-only ignored
`.streamlit/secrets.toml`. They are separate from the cursor/session-signing secrets
AWS generates automatically. Browser login cannot be substituted by a fabricated
user/session or a shared production password. See [identity setup](implementation/phase-5/SETUP.md).

## 2. Preview without deploying

```bash
.venv/bin/python -m infra.automation dry-run --config .local/customer/automation.json --work-dir .local/customer
```

This command makes **zero AWS calls and zero AWS writes**. It validates configuration
and writes private `plan.json` with the exact configuration/source hash, ordered
steps, account/region/role/model/budget inputs, bootstrap templates, anticipated
resource types and stack names, permission-screen requests and human dependencies.
It also generates `collector-examples/<instance-id>.json` without connecting to servers.

The displayed `plan_hash` is required by apply. The preview is not an AWS price
quote, proof of permissions, or a server-generated CloudFormation change set.
Bootstrap templates are exact. Later runtime templates need actual foundation
outputs, S3 object versions and qualified Lambda/AgentCore versions, so their exact
bindings are produced during apply. Each actual cloud change set is subsequently
inspected against that rendered template and saved privately before execution.
Changing configuration or the source commit invalidates the plan hash.

## 3. Read-only account and permission check

```bash
.venv/bin/python -m infra.automation check --config .local/customer/automation.json --work-dir .local/customer
```

Checks target account/current operator role, the three existing IAM roles and
CloudFormation trust, enabled regions, existing nonterminated EC2 inventory,
Lambda reservation headroom and Bedrock model/profile metadata. It simulates
screened operator and execution-role actions, including `iam:PassRole` with the
intended service and initial-access leading-key conditions. Missing results,
missing context, explicit/implicit denials and inability to simulate block apply;
private `preflight.json` lists affected actions/resources. API failures produce
`error.json` with the operation/error code, without raw cloud messages or credentials.

This is a conservative permission screen, **not a complete deployment policy
builder or an authorization guarantee**. Some actions require wildcard resources;
scoped conditional policies can need context the screen does not supply. Do not
attach AdministratorAccess to bypass a blocker. Have the security administrator
review the exact screen, role policies and required deployment/verifier APIs.
Model catalog visibility does not prove entitlement, CountTokens/tool support or
runtime access. AWS documents simulator limitations and differences from real
execution: [IAM simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html).

## 4. Apply the reviewed plan

Substitute the hash from your own dry-run output:

```bash
.venv/bin/python -m infra.automation apply --config .local/customer/automation.json --work-dir .local/customer --plan-hash YOUR_PLAN_HASH
.venv/bin/python -m infra.automation status --work-dir .local/customer
```

Applying creates billable customer resources. `apply` rechecks prerequisites,
builds packages, creates regional/durable/identity foundations, collects actual
outputs and generated secret versions, binds the limited session issuer, labels
the signing version, uploads/pins artifact versions, creates/seals tools and
runtime candidates, and collects their qualified versions. AgentCore adds the
separate incident/chat runtime/endpoint stages. Observation deployments additionally
create/seal observers and explicitly seed enabled health checks before strict
coverage/model qualification. The script writes `ui-connection.json` when the
candidate is ready.

The approved plan authorizes these additive/nonreplacement steps without repeated
per-step prompts. Every change set still passes existing template/role/account
inspection and digest checks. Deletions, replacements, foreign ownership, failed
stacks, drift and nonempty legacy-retirement diffs stop automation. It never deletes
queues/evidence/subscriptions to recover a failure. CFN requests carry stable
idempotency tokens; resume reconciles actual owned stack status/template rather
than treating local journal entries as proof of success. Lost responses can still
require operator inspection; blind paid/model or destructive retries are forbidden.

Automatic waiting defaults to 900 seconds per command, polling AWS progress every
five seconds. Set `--wait-seconds 0` to advance once, or up to 3600 for a longer run.
A pending AWS operation returns `WAITING`/exit 2 after that limit; rerun the same
command to resume. Human dependencies return immediately. Each process caches its
successful preliminary permission screen while advancing; a new apply process
rechecks it. Capacity checks account for verified reservations already created by
this deployment, and existing per-stage checks remain active.

The private work directory includes atomic `state.json`, rendered `bundle/`,
artifact builds, `preflight.json`, actual change-set reviews, canary/key/grant
receipts and `operations.log`. Keep it: do not edit or discard the journal to force
a retry. All paths stay under ignored `.local/` or private evidence. A file lock
prevents two processes using the same work directory. Do not concurrently run the
same release from two different directories; AWS ownership/create-only checks are
additional defenses, not a distributed deployment lock.

## 5. Complete native staging login, then resume promotion

Configure the customer's scoped UI profile to assume the generated
`staging_issuer_role_arn`. This is distinct from the deployment profile. Configure
OIDC secrets/callback/MFA, then run:

```bash
mkdir -p .local/customer/private
chmod 700 .local/customer/private
.venv/bin/python scripts/run_customer_ui.py --connection .local/customer/ui-connection.json --profile customer-staging-ui --staging-ticket-file .local/customer/private/canary.ticket
```

The launcher checks account/assumed role and uses generated connection references,
without copying AWS credentials. It binds the UI to loopback and disables ambient
`.env` loading. Native OIDC/MFA and the initial investigator grant are still required.
Sign in and use **Save staging canary session**. The existing app restricts the
export to staging, loopback and an owner-only directory. Now explicitly authorize
the paid staging model/tool test:

```bash
.venv/bin/python -m infra.automation apply --config .local/customer/automation.json --work-dir .local/customer --plan-hash YOUR_PLAN_HASH --allow-model-invocation --access-ticket-file .local/customer/private/canary.ticket
```

After a passing recent exact-bundle canary, automation obtains the retirement diff,
executes eligible routing/observation changes and checks actual registration.
Primary/fallback subscription confirmation and real mailbox delivery remain human
checks. If registration fails on pending email confirmation, confirm the inbox
messages and resume. A paid canary is not blindly repeated: an ambiguous outcome
or expired receipt requires inspection and an explicit `--retry-canary` together
with the paid flag and a valid private ticket. Retries retain prior receipt/request
history. Remove the ticket and export setting after staging.

After promotion configure the UI profile for the generated `ui_role_arn` and launch
without the ticket option:

```bash
.venv/bin/python scripts/run_customer_ui.py --connection .local/customer/ui-connection.json --profile customer-ui
```

## Status, deployment location and limits

- `WAITING` (exit 2): in-progress AWS operation or named human prerequisite; resume
  with unchanged config/hash. No success claimed.
- `FAILED` (exit 1): failed prerequisite/API/gate; diagnose privately and repair.
  AccessDenied is never interpreted as absent infrastructure. Check AWS stack
  events for the actual failed resource; do not blindly delete retained resources.
- `INFRASTRUCTURE_READY_MANUAL_ACCEPTANCE_PENDING` (exit 0): provisioning and
  registration passed; automatic investigation remains paused. This is **not**
  production qualification or proof an email reached a person.

Backend resources run in the customer's AWS regions. The UI runs on the machine
where its launcher runs. No EC2 host is created for it; always-on team UI hosting,
TLS/reverse proxy and network restrictions are customer decisions. EC2/application
and collector setup stays manual. Provider registration/native login and email
confirmation cannot be completed on the user's behalf by a backend deployment CLI.

Production configuration can provision paused candidates, but the existing paid
canary gate is staging-only. It stops at the explicit staging/production-cutover
handoff. Production promotion, enabling investigations, real IdP/IAM/model/delivery,
load, restore and rollback acceptance remain the existing later-phase gates. There
is no flag that bypasses them. The user deferred live verification; this feature
has local mocked/offline evidence only, and has made no AWS calls or deployments.
