# Individual identity and deployment wiring

P5.01 remains IN_PROGRESS pending real IdP/MFA/origin/IAM qualification. Optional
identity-enabled releases now provision a separate encrypted session table,
generated signing secret and scoped issuer/UI/runtime roles. Both standalone and
AgentCore propagate the deployment environment and identity settings. Releases
without identity configuration deny interactive staging/production access;
automatic incidents retain their IAM and ledger fencing. This is locally verified
implementation, not a qualified production release. See [customer setup](SETUP.md).

## Implemented behavior

Production and staging require native Streamlit OIDC. Development retains the
existing password flow; set `KIRA_AUTH_MODE=oidc` to exercise the individual path
in development. Backend enforcement depends on the configured deployment
ENVIRONMENT, not on a browser flag or a request-supplied environment.

Streamlit verifies the OIDC response; only its server-side `st.user` claims are
passed to session issuance. Never expose an endpoint accepting arbitrary claims.
Kira additionally requires the exact issuer/audience, nonempty subject, integer
unexpired `exp`, recent integer `auth_time` and verified `amr` containing `mfa`.
Providers that do not emit these claims are denied; no inferred MFA or email-only
membership. Real provider mappings/compatibility are pending. Native login is
not resource authorization; Kira checks that separately. See the primary
[Streamlit authentication documentation](https://docs.streamlit.io/develop/concepts/connections/authentication).

The actor is SHA-256 of the compact JSON `[issuer, subject]`; email/name are not
membership keys. Session references contain an opaque session ID, actor and
exact environment/account/release binding, signed with HMAC SHA-256. They are
bearer credentials: never log them or put them in report URLs.

Each backend action reads the authoritative identity grant and session with
DynamoDB `ConsistentRead=True`. Grants contain role, instance list, enabled flag,
revocation epoch and deployment binding. Permission is never supplied in the
prompt/request. A viewer can retrieve an in-scope report; only an investigator
can chat. Tool execution intersects user scope with deployment inventory and
checks current grants/session before each tool call and model iteration/budget
reservation. Report scope is checked before the evidence pointer/S3 body is read.

Idle expiry is 15 minutes; absolute expiry is the earlier of ID-token `exp` and
8 hours from IdP `auth_time`. An atomic conditional idle update cannot resurrect
a session deleted after its consistent read. UI refresh does not extend idle
expiry. Expiration checks do not rely on asynchronous DynamoDB TTL deletion.
Logout deletes the session; storage failure retains its reference for retry,
clears conversation data and blocks workspace access. Revocation is checked on
the next action, not cancellation of an already accepted external SDK request.
Rotating the signing key invalidates all outstanding references.

## Private configuration contract

Configure identity using the optional `identity` block in the durable JSON; see
`infra/identity.example.json`. Example inputs remain synthetic and undeployable.

- Native OIDC settings live in ignored `.streamlit/secrets.toml`: HTTPS callback
  ending `/oauth2callback`, independent random cookie secret, client ID/secret
  and exact issuer discovery URL. Use the provider's MFA policy. Require recent
  authentication with provider-supported `max_age`; verify actual emitted claims.
- Rendered `KIRA_ACCESS_POLICY_JSON` contains
  exactly `version: 1`, `binding: [environment, account, release]`, `issuer`
  (HTTPS) and `audience` (UI client ID). No credentials or user membership in it.
  UI and remote runtime need the same immutable configuration/binding. The private
  `KIRA_ACCESS_POLICY_FILE` alternative is retained; configuring both is denied.
- `KIRA_SESSION_KEY_ARN` and `KIRA_SESSION_KEY_VERSION` bind the independent
  Secrets Manager signing key. Workloads retrieve only that exact version under
  a matching IAM condition; no `AWSCURRENT` fallback. Successful reads use a
  bounded one-minute cache, failures are not cached. Per-action DynamoDB grant
  checks still apply. A private `KIRA_SESSION_SIGNING_KEY` alternative is retained
  for isolated fixtures; configuring both key mechanisms is denied. Never reuse
  APP_PASSWORD, the OIDC cookie/client secret or the log cursor secret.
- `KIRA_SESSION_TABLE`, `MONITOR_REGION` identify a dedicated encrypted DynamoDB
  table with string PK/SK, TTL attribute `ttl`, PITR and controlled retention.
  The identity foundation creates it with AWS-managed KMS encryption, PITR,
  deletion protection and retained deletion policy. It has no stream or indexes;
  never point identity at the incident stream table. TTL is expiry cleanup,
  not a grant-retention or backup-deletion policy (P5.03 remains pending).
- Operator-managed grant row: PK=`IDENTITY#<actor>`, SK=`META`, `binding` as above,
  `enabled` boolean, `epoch` positive integer, `role` viewer/investigator and
  `instance_ids` a unique nonempty subset of `ALLOWED_INSTANCE_IDS` (maximum 100).
  Disabling/removing a grant or changing its epoch revokes existing sessions.
  Increasing permissions requires an explicit operator access decision.

IAM wiring distinguishes grant management from session operations. The UI
can read `IDENTITY#*` and create/read/update/delete `SESSION#*`; the runtime only
reads `IDENTITY#*` and reads/updates `SESSION#*`. Neither workload may modify an
identity grant. The customer access administrator owns grant writes. Bind all
policies to exact table ARNs and leading-key conditions; verify denials live.
No DynamoDB Scan permission is needed by these paths. A limited session-issuer
role supports native OIDC login before routing promotion; it has no model, tool
or report access. The operator grant CLI uses a separate customer administrator.
Every reviewed grant update advances its epoch, including disabling access;
do not delete/recreate grants and reset epochs. Conditional writes compare all
authorization fields and reject concurrent changes. Raw subjects remain in
private request files, absent from saved review diffs and console output.

Release labels retain immutable signing versions for rollback. The pin operation
does not move a label already attached to another version. Live candidate checks
verify foundation template hashes, actual encryption/TTL/PITR/schema/stream
settings, secret ownership/version/label and actual limited-role grants/trust.
Post-promotion routing verification also checks the actual UI role and rejects
extra attached/inline policies. These verifiers are tested with synthetic AWS
responses; they have not been executed against customer resources. Render also
rejects environments beyond a conservative JSON-size limit of 4 KiB, before an
oversized configuration reaches Lambda's
[environment quota](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html).

Run the UI behind customer TLS with exact callback/origin configuration and
protected workload credentials. The default bind is loopback; container/proxy
binding needs an explicit override and protected network path. Keep CORS/XSRF
protections enabled. Nonempty Streamlit trusted-user-header mappings are rejected:
those mappings can override native cookie claims. The AgentCore HTTP host remains behind AWS IAM; its standalone
local HTTP server is not a public authenticated gateway. Do not grant browser
users the workload role, direct tool Lambda invocation or evidence-bucket reads.

## Acceptance still pending

The offline suite covers malformed claims, wrong issuer/audience, missing MFA,
forged/replayed-after-logout references, scope/role violations, expiry, unavailable
storage, policy revocation during work, conditional session deletion races,
unauthorized report reads and browser-state bypass. It does not validate a real
OIDC signature/callback, MFA enrollment, IAM permissions, encrypted table, TLS,
load, eventual cloud delivery or a deployed origin boundary.

P5.02 distributed login/chat budgets, automatic/chat capacity isolation and
session-issuance abuse controls remain NOT_STARTED. P5.03 redaction and retained
security-audit collection remain NOT_STARTED. Existing request MemoryBudget and
browser limits are not per-user/distributed quotas. Native Streamlit may log
upstream errors outside Kira's allowlisted audit events; secure log handling and
real-data qualification remain pending. Do not enable broad access on this slice.
