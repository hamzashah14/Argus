# Security reporting

Do not post credentials, customer data, exploit details or raw cloud responses in
public issues. If the repository enables GitHub private vulnerability reporting,
use its **Security → Report a vulnerability** form. If it is unavailable, request
a private contact channel from the maintainer without disclosing vulnerability
details publicly. No dedicated security email or response SLA is established.

Include affected source/version, a synthetic reproduction, impact and relevant
denial/scope boundaries. Operators retain responsibility for their own AWS account,
identity provider, hosting, telemetry, data classification, costs and incident response.

The project is locally tested and has not completed live production qualification.
Before production use, complete the [live acceptance checklist](docs/ACCEPTANCE.md)
and rehearse the security procedures in [operations](docs/OPERATE.md).

## Deployment security model

Kira is customer-operated, so you choose how much access it gets. Read this before you
expose the UI to anyone else.

**Default: local single-user mode.** One shared password (`APP_PASSWORD`, at least 12
characters) protects the web UI. Chat has no gateway and runs with the UI role's AWS
credentials. These protections still apply: the `ALLOWED_INSTANCE_IDS` allowlist,
pinned numeric tool versions, bounded `RUNTIME_LIMITS`, release binding, the diagnostic
policy and redaction. These do not exist: per-person identity, audit or revocation, a
shared spend cap, a lockout after wrong passwords and dedicated chat capacity (chat uses
the same tool functions or AgentCore runtime as incident investigations). The throttle of
20 requests per hour is kept per browser session, so a new session resets it. Anyone who
has the password can use the model and tools the UI role can reach and read every
incident report. Keep the UI on `127.0.0.1` or behind your own SSO or VPN proxy.

**Optional: OIDC module.** An `identity` block in the runtime configuration adds OIDC
sign-in with MFA, per-person grants, revocation, audit, per-user and shared quotas and a
dedicated chat gateway. Use it when more than one person uses the UI.

**Model provider.** With Bedrock, redacted excerpts go to Amazon Bedrock in your account
and region. With a Model API, redacted log and metric excerpts and your chat questions leave your
AWS account for that provider's HTTPS endpoint. The provider sets its own retention and
quotas and bills you, and redaction is best effort. The API key lives in a pinned
Secrets Manager version and never in configuration or environment variables. In the
default mode the UI role can read that version. The Model API option has never run
against a live provider.
