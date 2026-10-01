# P0.05 — Prerequisites and live-verification deferral

Status: **VERIFYING — local assessment complete, live verification deferred by
the user's explicit synthetic-reference choice**. No AWS API calls were made.

## Observed locally

| Check | Result | Meaning |
|---|---|---|
| Source and examples | Present | All current source/template files captured in the baseline manifest |
| `config.env` / `.env` | Both absent | No project-specific target selected |
| AWS CLI executable | Present | Does not establish authentication, permissions or a selected account |
| AWS profile/region/access-key variables in process environment | Absent at inspection | Other credential providers/profiles were not inspected or ruled out |
| Target customer/account | Not selected | Synthetic `000000000000` is deliberately non-deployable |
| Python runtime | 3.12.14 available; default system interpreter 3.14.7 | Use the isolated 3.12 harness for comparable results |
| Source/dependency validation | See baseline-checks evidence | Tests do not verify cloud permissions or model access |

## Live evidence required after a customer selects a target

Owner: customer infrastructure operator (person not assigned). Store private output
under `docs/implementation/evidence/private/`; attach sanitized summaries here.

| Capability | Read-only evidence to collect | Current result |
|---|---|---|
| Identity and environment | Explicit profile/role, expected account, `sts get-caller-identity`, region/partition, staging vs production boundaries | NOT_RUN |
| Fleet and service ownership | Selected EC2 instances/tags, service owners, health endpoints, static/autoscaled policy | NOT_RUN |
| Model/agent | Regional model/inference-profile availability, agent/alias routing, policies and access conditions | NOT_RUN |
| Runtime permissions | Role/policy/trust inspection and available policy simulation for tools/UI/worker | NOT_RUN; inspection alone cannot prove successful invocation |
| Quotas and capacity | Lambda concurrency, applicable Bedrock model quotas and Logs Insights limits in selected regions | NOT_RUN |
| Logs and metrics | Groups/retention/subscriptions, exact emitted dimensions, sample timestamps/freshness, bounded read access | NOT_RUN |
| Notification | Topic attributes/policies, subscription confirmation state, verified recipient owner | NOT_RUN; subscription state is not proof of inbox delivery |
| Existing resource ownership | Roles, functions/versions/aliases, action groups, rules/targets, alarms/filters, topic subscribers, tags and IaC stacks | NOT_RUN |
| Migration | Identify import/replace/retain/retire decisions per existing resource, including legacy fetch-health | NOT_RUN; never infer ownership from a name alone |
| Security/data | UI exposure/IdP, key ownership, data residency, redaction/retention requirements, release and recovery owners | NOT_RUN |

Do not run `setup-iam.sh`, `setup-lambdas.sh`, `deploy.sh`, `setup-alerts.sh`,
`generate_sample_data.py` or `set-alarm-state` as a read-only preflight: they write
resources/data or trigger paid investigations and notifications. The setup scripts
also lack the Phase 2 isolation guarantees.

Real model invocation, end-to-end email, alarm injections and rollback rehearsals
are integration tests with side effects/cost. Schedule them against the verified
customer staging target at the appropriate phase. Until then, capability and live
delivery remain **unverified**, even if local policy inspection looks correct.

## Re-entry requirements

Collect the chosen profile/role and expected account; monitor/model regions and
model; service inventory/owners; approved recipients/fallback; deployment/identity
constraints; and a live budget. No secret keys need to be pasted into chat or
committed. Replace the synthetic inventory with a private customer-specific record
and link a sanitized capability summary before any target-account mutation.
