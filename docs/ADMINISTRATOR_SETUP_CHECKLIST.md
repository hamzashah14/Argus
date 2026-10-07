# Administrator setup checklist: AWS backend to first UI use


**Automation option:** use [deployment automation](DEPLOYMENT_AUTOMATION.md) for
private configuration templates, offline dry-run, read-only checks, staged backend
provisioning, initial grants and UI connection output. The checklist still defines
customer IAM/bootstrap, server telemetry, provider/native-login and mailbox duties.

Updated: 7 October 2026. Applies to the current Phase 5 implementation.

This is the ordered manual setup guide for a customer operating Kira in their
own AWS account. The administrator can be the customer themselves. Maintainers
do not provision or manage a customer account, database, identity provider or UI.

**Current status:** repository implementation is locally tested; live AWS, SSO,
model, telemetry and inbox qualification remain pending. No project resources
have been deployed in this user's account. This document does not execute a
deployment or start Phase 6. The committed example configurations are synthetic
and must not be deployed unchanged.

## 1. Understand what you are setting up

The administrator runs CLI tools from a trusted workstation. Those tools build
packages and generate CloudFormation templates, then execute reviewed stages in
the customer's AWS account. Deployment returns connection references for the UI;
it does not generate a new UI application or automatically host a website.

| Location | Administrator configures | Project provides |
| --- | --- | --- |
| Administrator workstation | Python, AWS access, private deployment inputs, reviewed CLI runs | Build, render, deployment and verification tools |
| Customer AWS account | Permissions, model access, quotas, authorized deployment and operations | Templates for Lambda, queues, DynamoDB, S3, secrets, notifications, alarms and audit resources |
| Each monitored server | Instance role, collector, real log paths, metrics, heartbeat and readiness behavior | Inventory-derived collector configuration and heartbeat script |
| Customer identity provider | OIDC application, MFA, identities and callback registration | Native OIDC login and backend session/access checks |
| Customer UI machine or host | Backend configuration, AWS workload access, OIDC secrets; HTTPS/proxy for hosted access | Existing Streamlit UI |
| Customer mailboxes | Subscription confirmation and real delivery checks | SNS-based initial, follow-up and fallback notification paths |

The default `standalone` backend uses separate incident and chat Lambda functions;
no dedicated EC2 server is required for Kira. Optional `agentcore` hosting adds
separate incident/chat AgentCore Runtimes. Monitored EC2/application infrastructure
is customer-owned and is not created by this onboarding workflow. Alerts can run
while the UI is closed.

There are three milestones:

1. **Local preview:** development password and UI only; AWS/SSO are unnecessary.
2. **Administrator staging login:** deployed identity foundations, OIDC, matching
   configuration and an approved user grant. The administrator logs in to obtain
   the private canary session; full routing is not promoted yet.
3. **Operational access:** verified/promoted backend, correct UI role, telemetry,
   model checks and notification checks. Broader production access requires all
   remaining release gates, not just a successful login.

## 2. Choose the pilot and record the inputs

**Where:** administrator workstation and customer planning records.

- [ ] Select the AWS account, environment and monitoring/Bedrock regions.
- [ ] Choose `standalone` or `agentcore`; use a small standalone pilot when
      additional AgentCore hosting is not required.
- [ ] Select an existing Linux EC2 service, its instance ID and responsible owner.
      If no workload exists, create or identify a pilot workload separately.
- [ ] Record exact application/container/Nginx log paths and intended log groups,
      disk mount, process executable and real CloudWatch metric dimensions.
- [ ] Select the Bedrock model/profile and its exact IAM resource scope.
- [ ] Choose primary, incident fallback and observation fallback notification
      recipients. Keep the fallback channels independently usable.
- [ ] Decide where users will run the UI, its OIDC callback, and its stable HTTPS
      incident-status URL. A laptop's `127.0.0.1` URL is not a shared email link.
- [ ] Assign deployment/access, incident-response, security/data and budget owners.
      One person may hold several roles, but record the responsibilities.
- [ ] Approve retention, redaction/data handling, chat/incident limits, expected
      traffic and a pilot spending budget. Record rollback and backup ownership.

**Complete when:** actual inputs and owners are recorded privately. Model/query
allowances are not a hard dollar cap; paused investigations still leave storage,
monitoring and other provisioned costs. This guide supplies no assumed monthly bill.

## 3. Prepare the administrator workstation

**Where:** repository root on the administrator's machine.

- [ ] Obtain the reviewed source revision and Python 3.12, Git and AWS CLI.
- [ ] Create the virtual environment and install the locked dependencies.
- [ ] Prepare the hash-verified Lambda wheelhouse for builds.
- [ ] Create owner-only directories for customer configuration and evidence.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/dev.lock
.venv/bin/python -m pip download --require-hashes --only-binary=:all: --dest .build/wheels -r requirements/lambda.lock
umask 077
mkdir -p .local/customer/private
chmod 700 .local/customer .local/customer/private
```

These commands install/download dependencies; they do not deploy AWS resources.
A separate UI-only machine can install `requirements/app.lock` instead of the
development lock. Run commands from the repository root. Keep `.env`,
`.streamlit/secrets.toml`, customer JSON, grants, receipts and session tickets out
of Git. Check the repository's ignore rules before storing private files.

Cloud mutations require a clean reviewed source revision. Preserve unrelated
work and use a clean checkout rather than deleting files to satisfy that check.

**Complete when:** dependencies install successfully, build inputs are available,
and private storage/source revision are ready.

## 4. Configure AWS access, ownership, model and quotas

**Where:** customer AWS/IAM administration and the workstation's credential chain.

- [ ] Select the intended AWS profile/SSO session or assumed role. Confirm the
      account before any writes, for example with `aws sts get-caller-identity`;
      keep its response private. Renew expiring credentials when needed.
- [ ] Establish the declared CloudFormation deployment role and customer UI
      workload principal. Supply the CI principal required by the spec, even if
      release work is initially performed from a workstation.
- [ ] Assign scoped deployment, verification, access-administration and canary
      permissions. Generated workload roles are distinct from administrator roles.
- [ ] For AgentCore, also authorize the exact Runtime/endpoint management and
      execution-role passing required by the reviewed templates.
- [ ] Review existing resource ownership/import decisions before templates create
      log groups, topics or other potentially overlapping resources.
- [ ] Verify model access/entitlements and model/profile permissions in the chosen
      region. The runtime needs Converse tools and the implemented
      `bedrock-runtime CountTokens` path for its exact requests. A model listing
      alone does not prove compatibility; the paid staging canary proves execution.
- [ ] Verify Lambda concurrency, model throughput and other relevant service
      quotas against the rendered capacity. The previous account check reported
      Lambda concurrency **10**; this is an unresolved prerequisite for this user's
      deployment, not a recommended reservation.

Use the normal AWS credential chain: local profile/SSO, assumed roles or host
workload roles. Do not put AWS access keys into inventory JSON or browser inputs.
Browser SSO identifies the user; the UI process separately needs an authorized
AWS workload identity. Signing in with OIDC does not grant AWS IAM permissions.

**Complete when:** account, ownership, permissions, model prerequisites and quotas
are checked. See [deployment permissions and model requirements](implementation/phase-3/GUIDE.md)
and [resource ownership](implementation/phase-2/OWNERSHIP.md).

## 5. Create the private deployment configuration

**Where:** administrator workstation, ignored `.local/customer/`.

For the current identity/observation path, use these starting shapes:

```bash
cp infra/observability.example.json .local/customer/deployment.json
cp infra/identity.example.json .local/customer/durable.json
```

Run the copies only when initializing new files; preserve existing configuration.

| Private file | Administrator must replace/review |
| --- | --- |
| `deployment.json` | Account, regions, environment, new release ID, model/ARNs, declared IAM principals, recipients, instance inventory, log suffixes, process/disk settings, Nginx fixtures, service owners, health routes and collector metric IDs |
| `durable.json` | Runtime choice, fixed HTTPS status URL, incident fallback recipient, retention, concurrency, investigation limits, identity issuer/audience and shared/user chat/login/token/audit policies |
| `bindings.json` | Actual outputs collected during deployment: versioned uploaded objects, tool/runtime versions, foundations and exact secret versions; do not fill with invented ARNs |

- [ ] Replace every synthetic account, instance, model, role, address and `.invalid`
      URL. Set `reference_only:false` only for a real reviewed customer spec.
- [ ] Retain `executor_mode:qualified`. Keep investigations paused and observation
      schedules disabled during initial preparation.
- [ ] Match OIDC issuer/audience to the registration in step 6.
- [ ] Review the policy values rather than blindly adopting example capacities.
- [ ] Keep credential/secret values out of these JSON files.

**Complete when:** real configuration validates and an offline plan renders.
Changing `reference_only` alone does not make the examples valid infrastructure.

## 6. Register SSO with the customer's identity provider

**Where:** customer identity-provider administration console and the UI machine.

- [ ] Register an OIDC application for Kira's web UI; obtain its exact issuer,
      client ID, client secret and discovery URL.
- [ ] Register the exact callback URL ending in `/oauth2callback`. For a local
      staging pilot, use loopback only if the provider explicitly permits it.
      Hosted/team access requires the customer's HTTPS hostname.
- [ ] Enforce MFA and verify the signed claims include `iss`, stable `sub`, `aud`,
      integer `exp` and `auth_time`, and `amr` containing `mfa`. Kira rejects
      authentication older than eight hours. Provider compatibility is not automatic.
- [ ] Obtain each approved user's immutable provider subject through authorized
      provider administration. Email addresses are not membership identifiers here.
- [ ] Create private `.streamlit/secrets.toml` on each UI host, with owner-only
      access. Generate an independent cookie secret and store the provider secret.

Configuration shape; replace placeholders and fill both empty secret entries
privately. Empty secrets are not usable authentication configuration:

```toml
[auth]
redirect_uri = "https://YOUR_UI_HOST/oauth2callback"
cookie_secret = ""
client_id = "YOUR_OIDC_CLIENT_ID"
client_secret = ""
server_metadata_url = "https://YOUR_IDENTITY_HOST/.well-known/openid-configuration"
client_kwargs = { scope = "openid", prompt = "login", max_age = 28800 }
```

```bash
chmod 600 .streamlit/secrets.toml
```

Provider parameters must be verified for the selected provider. A provider unable
to emit the required claims needs an engineered adapter; do not remove checks.
The cookie, provider client, runtime signing and log-cursor secrets are separate.

**Complete when:** registration, callback, MFA and claim contract are established;
actual browser login is checked after identity deployment and user grants.
See [current SSO setup](implementation/phase-5/SETUP.md).

## 7. Build and review the deployment plan

**Where:** administrator workstation. These steps do not create cloud resources.

```bash
.venv/bin/python -m infra build --spec .local/customer/deployment.json --output .build/customer-tools --wheelhouse .build/wheels
.venv/bin/python scripts/build_pipeline.py --output .build/customer-pipeline --wheelhouse .build/wheels
.venv/bin/python scripts/build_observations.py --spec .local/customer/deployment.json --output .build/customer-observations --wheelhouse .build/wheels
.venv/bin/python -m infra.durable --spec .local/customer/deployment.json --config .local/customer/durable.json --output .local/customer/plan --build-dir .build/customer-pipeline --tool-build-dir .build/customer-tools --observation-build-dir .build/customer-observations
```

For AgentCore, also build the ARM64 host and add `--host-build-dir` to rendering:

```bash
.venv/bin/python scripts/build_lambdas.py --function incident_investigate --architecture arm64 --output .build/customer-host --wheelhouse .build/wheels
```

- [ ] Inspect generated resources, IAM/trust, account/regions, names, inventory
      scope, encryption, retention/PITR, budgets and artifact hashes.
- [ ] Record the exact bundle review hash privately.
- [ ] As outputs become available, update `bindings.json` and re-render with
      `--bindings .local/customer/bindings.json`. Review the new hash every time.

Bootstrap renders have fewer stages than fully bound renders. Do not try to
deploy a stage before its prerequisites and actual bindings exist.

**Complete when:** the administrator has reviewed the exact plan being executed.

## 8. Deploy foundations and collect outputs

**Where:** CLI on the workstation; resulting resources are in customer AWS.

For each applicable stage use the inspected change-set workflow below. Uppercase
values are placeholders from the exact plan/command outputs, not literal inputs.
These commands create/change AWS resources and are for an authorized live run.

```bash
.venv/bin/python -m infra.durable_ops change-set --bundle .local/customer/plan --review-hash REVIEW_HASH --stage STAGE --output .local/customer/change-set.json
.venv/bin/python -m infra.durable_ops inspect --bundle .local/customer/plan --review-hash REVIEW_HASH --stage STAGE --change-set CHANGE_SET_ID --output .local/customer/inspected-change.json
.venv/bin/python -m infra.durable_ops execute --bundle .local/customer/plan --review-hash REVIEW_HASH --stage STAGE --change-set CHANGE_SET_ID --change-set-hash INSPECTED_HASH --output .local/customer/execution.json
```

Wait for actual CloudFormation completion, then collect outputs with `collect`
using the same bundle/hash/stage/output arguments. Execution requested is not
deployment complete. Save stage-specific results privately before another run.

- [ ] Deploy `foundation-tools` and `foundation-monitor` in their declared regions.
- [ ] Deploy `durable-foundation`; collect its output under `bindings.foundation`.
      It supplies the incident database, evidence storage and durable queues.
- [ ] Deploy `identity-foundation` and `identity-secret`. Collect identity table
      outputs and signing-secret metadata; bind its exact version.
- [ ] Re-render and update the identity foundation to create `SessionIssuerRole`,
      restricted to the declared UI workload principal. Pin the release signing
      version with `infra.identity_ops pin-secret-version`.
- [ ] Deploy `observation-foundation` and review ingress/dead-letter policies for
      every declared observer/canary rule. Collect any required outputs.

You do not install a database server or manually create application tables beside
these stacks. CloudFormation provisions the incident and session/grant DynamoDB
tables and private evidence storage. Administrators still own retention, access
and backup/restore procedures.

**Complete when:** foundations completed, outputs/versions are bound, and the
limited session issuer trust/permissions are correct. Follow the detailed
[identity ordering](implementation/phase-5/SETUP.md#ordered-infrastructure-wiring)
alongside [foundation deployment](implementation/phase-3/GUIDE.md).

## 9. Confirm all notification subscriptions

**Where:** actual recipient mailboxes, plus CLI/cloud verification.

- [ ] Open and confirm the SNS subscription email for the primary recipient.
- [ ] Confirm the incident fallback recipient's subscription.
- [ ] Confirm the separate observation fallback recipient's subscription.
- [ ] Verify the topic/subscription matches the intended account, environment and
      recipient. Resolve missing/pending confirmations and mail filtering.
- [ ] Arrange independent responders and an authenticated reachable status URL.

Subscription confirmation enables delivery; it does not prove that incident
emails reach the inbox. Actual initial/follow-up/fallback delivery is tested in
step 15. The SQS test recipient receipt also does not prove human inbox delivery.

**Complete when:** all required subscriptions are confirmed; real inbox checks
remain tracked until activation. Other chat/notification connectors are not
implemented simply because email works.

## 10. Configure telemetry on every monitored server

**Where:** each inventory server and the customer's CloudWatch account.

- [ ] Attach/configure the approved instance role and network access for exact
      CloudWatch logs/metrics. Do not install administrator credentials on servers.
- [ ] Install CloudWatch Agent; apply the inventory-derived configuration and
      start/enable its service. Templates do not install the agent remotely.
- [ ] Map actual application/container/Nginx paths to the declared log groups and
      streams. Validate file permissions, stream identity and retention ownership.
- [ ] Publish required memory, disk and process metrics. Verify actual `InstanceId`,
      disk path, process `exe`/`pid_finder` and other dimensions match inventory.
- [ ] For Nginx, configure combined access/error logging and validate sanitized
      matching and nonmatching samples. Request counts and diagnostic-event counts
      are separate; do not add them together as unique requests.
- [ ] Install `scripts/collector_heartbeat.py` in a protected server path; create
      and enable a supervised timer. Keep the clock synchronized and rotate logs.
- [ ] Ship the heartbeat file with CWAgent to the declared dedicated heartbeat
      group and fixed instance-ID stream. Verify fresh timestamps in both a required
      collector metric and the shipped heartbeat.
- [ ] Implement/verify service readiness semantics: an unhealthy essential
      dependency must make readiness fail, or have its own declared health route.

Example heartbeat invocation on the server, substituting its real instance ID:

```bash
python3 /opt/kira/scripts/collector_heartbeat.py --instance-id "$INSTANCE_ID" --file /var/log/kira-collector-heartbeat.log
```

Use a root-owned installation/unit and file access appropriate for CWAgent. A
systemd timer uses `OnBootSec=30s`, `OnUnitActiveSec=60s`, `AccuracySec=5s`; enable
it explicitly and verify timer/service status. The script only writes a local
heartbeat; CWAgent ships it. Quiet application logs are not a heartbeat.

The current health adapter supports reviewed public HTTPS routes, without
credentials, redirects, query strings or private addresses. Do not expose a
private service just for this adapter; VPC-only probing needs additional adapter
work. Current examples do not qualify Windows collectors, arbitrary AWS service
types or automatic autoscaling discovery.

**Complete when:** actual logs, metric dimensions, heartbeat and readiness are
verified. See [server telemetry instructions](implementation/phase-4/GUIDE.md#prepare-actual-customer-telemetry).

## 11. Deploy immutable tools, incident/chat runtimes and observers

**Where:** administrator CLI and customer AWS.

- [ ] Upload exact tool artifacts through `infra.durable_ops upload`; collect
      versioned object bindings and the log-cursor secret version.
- [ ] Re-render, deploy `owned-tools`, collect numeric tool versions and seal it.
- [ ] Upload/bind the pipeline and observation artifacts.
- [ ] Deploy/collect/seal `durable-runtime`, `chat-runtime` and
      `observation-runtime` as their complete bindings allow. Chat uses separate
      capacity from automatic incidents.
- [ ] For AgentCore, upload the ARM64 host, deploy/collect/seal the incident Runtime
      then its exact release endpoint. Do the same for the separate chat Runtime
      and chat endpoint before the chat gateway. Ensure log ownership/retention
      exists before invocation; do not use `DEFAULT` or invented versions.
- [ ] Re-render with all actual bindings and verify candidates and observers.
- [ ] Before strict coverage for enabled observations, run reviewed `seed-health`,
      wait for metric discovery, and recheck coverage. This writes health metrics
      and may probe approved endpoints; it does not run a model or activate schedules.

Use `seal-runtime --stage STAGE` for immutable stages after completion. Do not
update sealed release stacks: changes require a new release, reviewed bindings
and cutover. The detailed artifact/binding instructions are in
[runtime deployment](implementation/phase-3/GUIDE.md),
[observation deployment](implementation/phase-4/GUIDE.md#deploy-and-verify-the-additional-stages)
and [Phase 5 chat additions](implementation/phase-5/SETUP.md).

**Complete when:** deployed code/configuration/roles match the exact candidate,
versions are sealed and actual telemetry coverage passes. Verification of
configuration alone does not establish model behavior or delivery.

## 12. Grant the first administrator/application user access

**Where:** separate access-administrator CLI identity; authoritative grant table.

No first user is automatically made an administrator. There is no public signup.
Application roles are `viewer` (reports) and `investigator` (investigations within
scope). AWS deployment/access administration remains a separate IAM responsibility.

- [ ] Obtain the approved person's immutable OIDC `sub` from the provider.
- [ ] Create a private request with exactly `subject`, `enabled`, `role` and
      `instance_ids`. Scope it to a nonempty subset of the reviewed inventory.
- [ ] Use the exact complete candidate bundle to preview the grant, review its
      identity/release/role/scope and apply it with the access-administrator role.

```bash
.venv/bin/python -m infra.identity_ops grant-plan --bundle .local/customer/plan --review-hash REVIEW_HASH --request .local/customer/private/access-request.json --output .local/customer/private/access-plan.json
.venv/bin/python -m infra.identity_ops grant-apply --bundle .local/customer/plan --review-hash REVIEW_HASH --request .local/customer/private/access-request.json --grant-plan .local/customer/private/access-plan.json --output .local/customer/private/access-result.json
```

The staging canary requires an `investigator` grant. Grant updates increment the
revocation epoch; revoke using `enabled:false`, not delete/recreate. A new release
needs reviewed grant rebinding. The UI workload cannot grant itself membership.

**Complete when:** the first intended user has an active matching grant and the
access administrator retains the private review/result.

## 13. Configure the UI and perform the first staging login

**Where:** UI machine, repository root.

- [ ] Initialize a private `.env` from `.env.example` if one does not already
      exist. Configure staging/OIDC; a shared password cannot authenticate staging
      or production.
- [ ] Copy the exact `Outputs.RuntimeConnection.Value` JSON fields from the reviewed
      routing template into UI environment settings. It is configuration, not a
      URL or command to execute. Do not invent ARNs, fingerprints or secret bytes.
- [ ] Add the incident table, report bucket and monitoring region from actual
      foundation outputs. Match the same backend release/policies.
- [ ] Configure AWS workload access through the declared principal. Before
      promotion, assume the limited `SessionIssuerRole`; it does not have chat/
      report permissions. After promotion use the verified routing `UiRoleArn`.
- [ ] Put provider settings in `.streamlit/secrets.toml` and restrict both files
      to their owner. Remove conflicting stale environment/policy overrides.

| UI settings | Source |
| --- | --- |
| Environment, runtime choice, account/regions, model, allowed instances, tool/release/limit references and qualified `CHAT_FUNCTION_ARN` | Exact rendered `RuntimeConnection` |
| `KIRA_ACCESS_POLICY_JSON`, `KIRA_SESSION_TABLE`, `KIRA_SESSION_KEY_ARN`, `KIRA_SESSION_KEY_VERSION`, `KIRA_WORK_POLICY`, `KIRA_DIAGNOSTIC_POLICY` | Identity-enabled `RuntimeConnection`; exact immutable versions and policies |
| `MONITOR_REGION`, `INCIDENT_TABLE`, `REPORT_BUCKET` | Verified foundation bindings |
| OIDC callback/client/discovery/cookie settings | Private provider registration and `.streamlit/secrets.toml` |
| AWS profile/assumed/workload role | Customer AWS credential chain; limited issuer during bootstrap, UI role after promotion |

```bash
chmod 600 .env .streamlit/secrets.toml
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

`app.py` loads `.env`; pre-existing process environment values take precedence.
Restart the UI after changing configuration. Sign in using the provider and MFA.
For the local staging canary only, configure `KIRA_STAGING_TICKET_FILE` to an
absolute file path in an owner-only directory, then use **Save staging canary
session** in the UI. Remove the ticket/settings after the canary. This is a private
short-lived credential, not a public download or production bypass.

**Complete when:** the first user signs in with matching claims/grant and can
obtain the authorized staging session. Login here precedes promotion; opening
the UI successfully is not operational readiness.

## 14. Qualify the backend and promote routing

**Where:** separately scoped staging operator CLI; customer AWS.

- [ ] Verify candidate/IAM/coverage and approve a bounded paid model canary.
- [ ] Run the canary with the private investigator session file; review actual
      model/logs/metrics results. This uses a separate operator invocation role,
      not the limited session issuer role.
- [ ] Generate/review the retirement plan. Retire stale resources when required
      and execute reviewed routing with the exact valid receipt/retirement plan.
- [ ] Re-render/re-canary/re-review any changed paused/enabled settings. Never
      activate by modifying a template or carrying forward a stale receipt/hash.
- [ ] After promotion, switch UI AWS access to `UiRoleArn`, apply the verified
      connection output and run routing verification.
- [ ] Verify allowed/denied scopes, viewer/investigator behavior, logout,
      expiry/revocation and actual audit receipts. Complete the required live gates
      before broad production access.

Exact verification/canary/promotion commands are in
[runtime qualification](implementation/phase-3/GUIDE.md#verify-canary-and-promote)
and [identity bootstrap](implementation/phase-5/SETUP.md). Automatic investigations
stay paused until their relevant gates and budget are approved.

**Complete when:** the selected runtime/model/tools and promoted UI role are
actually qualified. The current project's live checks are still pending.

## 15. Activate and test alerting/notifications, then share the UI

**Where:** operator CLI, monitored workload, actual mailboxes and UI host.

- [ ] Execute reviewed service routing and observation settings; verify qualified
      targets, schedules, queue mappings, alarm actions and dashboard.
- [ ] Run the initial no-model notification canary after activation; inspect the
      incident/publisher and SQS receipt, then independently check the real inbox.
- [ ] Record `attest-email` only for the actual received notification ID and inbox.
      A successful SNS publish or SQS receipt is insufficient.
- [ ] Exercise real primary initial/follow-up notifications and both fallback
      mailboxes. Confirm incident links resolve to the intended authenticated UI.
- [ ] Check missing telemetry, missing observer heartbeat, failed delivery,
      revoked-user and rollback scenarios in the acceptance procedures.
- [ ] For team hosting, configure customer HTTPS/TLS, exact Host/Origin policy,
      WebSocket forwarding and restricted backend access. Preserve Streamlit
      CORS/XSRF; keep trusted-user-header overrides empty and Streamlit on loopback
      behind the proxy. Register the final callback and test it again.
- [ ] Give users the UI URL and their provider sign-in instructions after access
      and release approval. Do not distribute deployment credentials or session keys.

**Complete when:** real notifications, authenticated UI access and the required
release checks pass. A local UI may be enough for chat, but the full notification
link workflow requires the configured reachable HTTPS status UI. See
[observation acceptance](implementation/phase-4/ACCEPTANCE.md) and
[identity live acceptance](implementation/phase-5/SETUP.md#live-acceptance-still-not_run).

## Final readiness and routine administration

Before granting operational access, confirm:

- [ ] Real deployment inputs, ownership, AWS access and quotas approved.
- [ ] Model access and exact runtime compatibility demonstrated in staging.
- [ ] Foundation/runtime/chat/observer resources verified and release versions bound.
- [ ] Every monitored server's actual telemetry and declared health checks verified.
- [ ] OIDC/MFA/callback configured; intended users granted correct release/scope.
- [ ] UI workload role, connection settings, report access and login/logout tested.
- [ ] All SNS subscriptions confirmed and real delivery/link checks completed.
- [ ] Retention/redaction/audit, recovery, budget and remaining release gates approved.

After onboarding, the administrator still renews/rotates access, reviews users and
recipients, monitors failures/DLQs and spend, maintains backups, updates dependencies
and qualifies releases. Static inventory changes require a rebuilt reviewed release;
there is no automatic fleet discovery. Revoke departing users and retire obsolete
recipients through the reviewed procedures. Follow
[security operations](implementation/phase-5/SECURITY_OPERATIONS.md) and
[operational runbooks](implementation/phase-4/RUNBOOKS.md).

For **today's local preview only**, none of the cloud steps has been performed.
Open `http://127.0.0.1:8501`, use the private `.env` file's `APP_PASSWORD`, and click
**Open workspace**. “Workspace” is a label, not an additional account or name.
The disconnected setup screen and disabled investigations are expected.
