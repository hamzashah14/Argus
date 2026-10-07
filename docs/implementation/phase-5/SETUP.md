# Customer identity setup and qualification

P5.01–P5.06 local implementation complete; live verification pending. No deployment has occurred. These are operator
procedures for an eventual customer staging environment. Never run the synthetic
reference on AWS. Follow the Phase 3/4 bootstrap, reviewed change-set, sealing,
coverage and promotion gates; this guide adds identity ordering. Keep automatic
investigation paused until its acceptance gates pass. Local budgets/redaction/diagnostic controls are implemented, but actual customer
identity, policy, model and retention acceptance remain pending. See
[local completion](LOCAL_COMPLETION.md) and [security operations](SECURITY_OPERATIONS.md)
before enabling broad access or sensitive-data evaluation.

## What the customer supplies

The customer registers an OIDC application, selects its exact issuer/client ID,
enforces MFA and verifies that signed ID claims include `iss`, `sub`, `aud`,
integer `exp` and `auth_time`, and `amr` containing `mfa`. No email-based membership
or inferred MFA. Configure provider-supported recent authentication parameters;
Kira rejects authentication older than eight hours regardless of the browser
cookie. A provider that cannot emit this contract needs an explicitly engineered
adapter and acceptance tests; removing the checks is not an adapter.

Run the web UI on the customer's machine for a small pilot, using the customer's
AWS credential chain and scoped assumed role. Always-on alerts still execute in
the customer's AWS account when the UI is closed. AgentCore is optional; standalone
avoids its additional runtime. There is no maintainer control plane or required
UI hosting server. OIDC, DynamoDB/PITR, secret storage and cloud workers have
customer-selected costs; no estimate substitutes for an approved regional budget.

If a team hosts the UI, the customer owns hosting, TLS, exact callback/origin,
network restrictions and credential isolation. Keep Streamlit bound to loopback
behind a customer TLS proxy; do not expose the raw backend origin. Configure
WebSocket forwarding and an exact public hostname, reject other Host/Origin
values, and preserve Streamlit CORS/XSRF protections. Trusted-user-header identity
overrides must remain empty. Backend AgentCore authorization remains AWS IAM.
Neither a browser login nor a JWT authorizes direct Lambda/tool/S3 access.

Create owner-only ignored `.streamlit/secrets.toml` with a provider-specific
configuration following [Streamlit's OIDC setup](https://docs.streamlit.io/develop/concepts/connections/authentication).
Use independent random cookie and provider client secrets; never place their
values in durable JSON or public evidence. A single-provider shape is:

```toml
[auth]
redirect_uri = "https://customer.example.invalid/oauth2callback"
cookie_secret = "REPLACE_PRIVATELY"
client_id = "REPLACE_WITH_CUSTOMER_CLIENT_ID"
client_secret = "REPLACE_PRIVATELY"
server_metadata_url = "https://identity.example.invalid/.well-known/openid-configuration"
client_kwargs = { scope = "openid", prompt = "login", max_age = 28800 }
```

Parameters are provider-dependent and must be verified. A local staging provider
may explicitly permit a loopback callback; public/team deployment requires TLS.
Record the final callback, origin and MFA enrollment in private acceptance records.
Do not enable token exposure in Streamlit secrets or add identity headers at a proxy.

## Ordered infrastructure wiring

1. Copy `infra/identity.example.json` to ignored customer configuration. Replace
   issuer/audience and other synthetic settings with reviewed values; retain the
   chosen runtime target. Render from clean committed source with the private
   customer spec. Empty bindings render the existing bootstrap foundations plus
   `identity-foundation` in the monitoring region and `identity-secret` in the
   Bedrock region. The generated signing secret is separate from log cursors and
   OIDC secrets. Neither rendering nor collecting reads the secret value.
2. Review/create/inspect/execute the two identity foundation change sets using
   `infra.durable_ops`, then wait for completion. Collect the current signing
   metadata with `identity-version`; add its two output fields beneath
   `bindings.identity`. This metadata collector is read-only and chooses the
   unique current version; the release thereafter uses that immutable version.
3. Re-render with these bindings and update `identity-foundation` through another
   reviewed change set. It now creates `SessionIssuerRole`, trusting only the
   declared UI workload principal. This role can read grants, manage sessions, reserve distributed login allowances,
   retain classified access records and read the exact signing version. It cannot modify grants, invoke models/tools or
   retrieve reports. Verify ownership and trust; never give it to browser users.
4. Pin the selected signing version using `infra.identity_ops pin-secret-version`.
   The release-specific label protects it from becoming an unlabeled deprecated
   version. The command requires clean reviewed source, account and foundation
   verification. It refuses to retarget an existing label; create a new release
   for a new key. Keep rollback labels until a reviewed retirement/deletion action.
   Unlabeled versions can be removed by AWS; see
   [version-label semantics](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_UpdateSecretVersionStage.html).
5. Continue the Phase 3/4 build/upload/collect sequence for tools, durable runtime,
   optional automatic AgentCore host/endpoint, and observations. Identity-enabled
   releases additionally create a separate immutable `chat-runtime` Lambda; AgentCore
   mode also creates `agentcore-chat-runtime` then `agentcore-chat-endpoint` before
   the chat gateway. Collect each output using its exact stage name, including
   `ChatVersionArn` under `bindings.chat_version`; bind/seal all candidates before
   routing. Chat uses the already verified incident-investigate ZIP, without creating
   an unverified new package. Re-render complete bindings and seal immutable stages.
   Run `verify-candidate`: it requires the exact key label, identity grants/roles,
   isolated chat function/host, capacity and access trail settings. Actual audit
   receipt and model behavior still require the live gates.
6. Prepare the local UI environment from the reviewed routing template's
   `Outputs.RuntimeConnection.Value` JSON; it contains references, never key bytes.
   Add `INCIDENT_TABLE`/`REPORT_BUCKET` and `MONITOR_REGION` from verified foundation
   bindings for eventual report access. Remove stale policy-file/direct-key
   overrides. Required shared values include `ENVIRONMENT`, `BEDROCK_REGION`,
   `EXPECTED_ACCOUNT_ID`, `RUNTIME_RELEASE`, `ALLOWED_INSTANCE_IDS`, identity
   inline JSON/table/key references `KIRA_WORK_POLICY`/`KIRA_DIAGNOSTIC_POLICY` and the qualified `CHAT_FUNCTION_ARN`. Use the same
   release fingerprint as the backend. Initially assume only `SessionIssuerRole`
   through the customer UI workload principal; chat/report attempts will lack
   chat/report grants until promotion. The production UI role has no direct model,
   tool or AgentCore invocation permission. Do not synthesize a backend session.
7. Have the customer access administrator review/apply the investigator grant
   below, using the exact complete candidate bundle. Sign into the loopback UI
   with native OIDC/MFA and obtain the private canary ticket as below. Run the
   explicitly paid staging canary using a separately scoped operator IAM principal
   permitted to invoke the exact candidate chat version (the issuer role cannot),
   review its receipt, and promote through the
   unchanged retirement/change-set gates. Delete the private ticket afterward.
8. After promotion, assume the routing output `UiRoleArn` instead of the limited
   issuer role, copy the verified `RuntimeConnection` and run `verify-routing`.
   It verifies actual UI trust/grants including identity permissions. Complete
   the live acceptance matrix below before wider access. Never broaden the
   issuer role into a model/tool/report administrator to bypass ordering.

Metadata collection and version pin commands, after the relevant reviewed stages:

```bash
.venv/bin/python -m infra.durable_ops identity-version --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/signing-version.json
.venv/bin/python -m infra.identity_ops pin-secret-version --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/key-pin.json
```

Every re-render changes the review hash; use the hash belonging to that exact
plan. Customer JSON/bindings/receipts stay private. Reference bundles are rejected
before any AWS client is constructed. No command above was run on AWS here.

## Grants, revocation and rollback

The customer access administrator supplies a private request with exactly
`subject`, `enabled`, `role` (`viewer` or `investigator`) and `instance_ids` (a
nonempty unique subset of deployment inventory). Obtain the immutable subject
through an authorized provider administration process, not a typed email or
prompt. The issuer comes from the reviewed deployment configuration. Keep request
and plan files under an owner-only directory; the CLI saves output files mode 0600.

```bash
umask 077
mkdir -p .local/customer/private
chmod 700 .local/customer/private
# Privately create access-request.json with the authorized subject/role/scope.
.venv/bin/python -m infra.identity_ops grant-plan --bundle .local/customer/plan --review-hash REVIEW_HASH --request .local/customer/private/access-request.json --output .local/customer/private/access-plan.json
# Review actor, before/after binding, enabled flag, role, scope and incremented epoch.
.venv/bin/python -m infra.identity_ops grant-apply --bundle .local/customer/plan --review-hash REVIEW_HASH --request .local/customer/private/access-request.json --grant-plan .local/customer/private/access-plan.json --output .local/customer/private/access-result.json
```

The administrator needs exact-table `GetItem`/`PutItem` restricted to `IDENTITY#*`
with `ForAllValues:StringLike` and `Null:false` leading-key conditions, plus the
read-only CloudFormation/DynamoDB metadata/IAM/Secrets Manager Describe permissions
used by the verifiers and STS account check. Key pinning separately needs exact
secret `UpdateSecretVersionStage`. These administrative grants are not attached
to UI/runtime workloads by this project. The customer's security owner assigns
the administrator role and access-review responsibility.

Every grant update increments epoch. Set `enabled:false` and review/apply to
revoke; never delete/recreate a grant with epoch one. Concurrent writes or a
changed plan fail rather than overwriting another operator. If an apply response
is lost, inspect a new read-only plan before another decision; do not blindly retry
a write. Existing sessions fail at their next authorized action. An already
accepted AWS request may finish; revocation is not forced cancellation.

Bindings admit one release per actor. A new issuer/audience/key/model/tool/limit
or release fingerprint requires an explicitly reviewed grant rebinding; preparing
it invalidates the actor's old-release sessions. Coordinate cutover in a customer
maintenance window. Rollback similarly requires reviewed rebinding and a fresh
OIDC session, plus retirement of obsolete caller permissions/endpoints. Restoring
a database backup can restore revoked grants/epochs: isolate restored storage and
reconcile current access decisions before reconnecting it. Local restore/deletion and rotation controls are documented in
[security operations](SECURITY_OPERATIONS.md); actual rehearsals remain pending.

## Private staging canary ticket

Only for a local macOS/Linux operator pilot, set `KIRA_STAGING_TICKET_FILE` to the absolute path
of a ticket in an owner-only directory. It is absent by default. Start the staging
UI bound to `127.0.0.1`, sign in via OIDC and click **Save staging canary session**
in the operator expander. The app verifies an active investigator grant/session,
then atomically writes mode 0600. It provides no browser download, raw-claim
issuance endpoint or production bypass. Public binds and production deny export.
The file is a short-lived bearer credential; never commit, upload or copy it into
logs/URLs. The canary reads it from disk, not a command-line token argument:

```bash
.venv/bin/python -m infra.durable_ops canary --allow-model-invocation --access-ticket-file .local/customer/private/canary.ticket --bundle .local/customer/plan --review-hash REVIEW_HASH --output .local/customer/canary.json
rm .local/customer/private/canary.ticket
```

Remove the export setting after staging. The limited issuer role creates the
session; the paid canary invokes the dedicated chat Lambda's actual
role and optional separate AgentCore chat host. Its operator principal needs exact
qualified candidate InvokeFunction permission, not direct model/tool permissions. No notification is sent by that chat canary.

## Live acceptance still NOT_RUN

Use private evidence and a bounded approved staging budget. Record the exact
source, bundle, issuer/client/callback, workload roles and key version without
credentials or raw claims. Exercise:

- Valid native OIDC signature/state/nonce, recent MFA, logout and reauthentication;
  reject absent/expired/wrong-audience claims and unregistered users.
- Viewer versus investigator, cross-instance chat/tool/report requests, revoked
  epoch/disabled grant, idle/absolute expiry and storage/secret unavailability.
- Actual UI/issuer/runtime IAM denials for grant writes, scans, foreign secret
  versions and direct tool/evidence access by end users; review resource policies,
  SCPs and credential handling as well as verified workload inline policies.
- Host/Origin and proxy/direct-origin bypass, XSRF, WebSocket and cookie behavior,
  header impersonation and public unauthenticated entry paths.
- Key version rotation/rollback, grant rebinding, stale caller/endpoints removal,
  backup restoration, access logging and customer security-owner review.

Synthetic tests cannot satisfy these gates. No real IdP or origin exists yet;
distributed budgets, redaction, retained audit and structured diagnosis now have
local evidence, but no real provider/AWS/model/inbox qualification. All six tasks
remain VERIFYING and G5 NOT_RUN. Follow the full pending matrix in
[local completion](LOCAL_COMPLETION.md). No findings are closed by this guide.
