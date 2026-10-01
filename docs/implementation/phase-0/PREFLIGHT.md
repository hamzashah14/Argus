# P0.05 — New-deployment prerequisite assessment

Status: **DONE as a new-deployment assessment, with deployment gaps recorded**.
The user clarified that no EC2, Bedrock or project infrastructure has been created.
The configured CLI account has now been verified through STS and inspected read-only
in its configured region, `eu-central-1`. The region is an observed CLI setting,
not a final deployment/model-region decision.

The plan now explicitly distinguishes assessment of an empty account from testing
services that have not been built. Phase 0/G0 is complete for this starting point.
Model invocation, effective runtime/deployment permissions, telemetry and notification
delivery remain **unverified** and are assigned to the later tasks below.

## Observed evidence on 2026-10-01

[Sanitized capability summary](../evidence/phase-0/account-preflight-summary.json).
Full account ID and principal ARN are only in ignored local evidence under
`docs/implementation/evidence/private/`; no credentials are recorded in project files.

| Check | Actual result | Interpretation |
|---|---|---|
| AWS CLI | One configured profile, `default`; region `eu-central-1` | Explicit profile used for inspection |
| STS GetCallerIdentity | PASS; IAM user principal | Authentication verified; not a claim of deployment permission |
| EC2 DescribeInstances | 0 non-terminated instances in inspected region | Existing fleet is not available; use synthetic fixtures |
| Bedrock ListAgents | 0 matching `aiops-` agents | Agent/alias will be provisioned later |
| Bedrock ListFoundationModels, text output | Metadata listing succeeded; 44 entries | Catalog readable; selected-model entitlement/invocation/quota not verified |
| Lambda GetAccountSettings | 10 concurrent executions; 0 functions | Small regional quota must inform deployment/capacity design |
| Lambda ListFunctions | 0 matching `aiops-` functions | No existing project tools/worker in inspected region |
| SNS ListTopics | 0 matching `aiops-` topics | Topics/subscriptions are future resources; no delivery test possible yet |
| CloudWatch DescribeAlarms | 0 `aiops-` metric alarms | Detection coverage not deployed |
| Logs DescribeLogGroups | 0 `/aiops/` groups | Telemetry collection/read access to actual log data not verified |
| EventBridge ListRules | 0 `aiops-` rules on default event bus | Trigger route not deployed |
| Project `config.env` / `.env` | Absent | No private deployment/UI configuration generated |

Initial sandbox requests failed to reach AWS endpoints. Network-enabled read-only
retries succeeded. API metadata reads were the only cloud operations: no resource
creation/configuration changes, paid model calls, sample data or notifications.

Inspection scope is **one configured region**, current project-name prefixes and
the default EventBridge bus. This is not an all-region/all-name/global-IAM audit.
The user's statement supplies the new-deployment context; metadata independently
confirms the listed absence. Recheck relevant global names and chosen target regions
before creating stacks; no legacy migration should be assumed solely from naming.

## Follow-ups required before their dependent deployment work

| Gap / decision | Owner | Required task and evidence |
|---|---|---|
| Final staging account, monitor/model regions, environment naming and approved spend | User / deployment operator | P2.01: record intended targets and budget before any provisioning |
| Bedrock model choice, regional support/entitlement and model-specific quotas | User selects model; engineering verifies | P2.04/P2.05/P6.01: inspect chosen model/profile and test invocation in staging |
| Deployment role, existing global IAM names, runtime trust/policies and workload identity | Deployment/security operator | P2.01/P2.02/P2.05: reviewed resource plan and effective permission checks |
| Lambda concurrency of 10; current example requests reserved concurrency 2 | Deployment operator | P2.05/P3.07/P6.03: resolve quota/control feasibility and prove bounded execution |
| EC2 pilot and telemetry sources | User selects future pilot; engineering provisions/configures | P2/P4.03/P6.01: actual dimensions, log access, freshness and health coverage |
| Notification recipient/owner and fallback route | User / notification operator | P3.04/P4.05/P6.01: confirmed subscriptions and actual delivery evidence |
| UI host/IdP, named operational roles, evidence residency/retention and recovery requirements | User / future operator | P5/P6/P7: record live choices and prove controls before broad access/rollout |

AWS documents that reserved concurrency must leave 100 units for unreserved
functions. With an observed total of 10, the existing example's positive reservation
cannot be assumed to work. Record this as a deployment gap; do not silently proceed
without a paid-work limit or change the account quota in Phase 0.
[AWS reserved concurrency documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html).

## Reproducing the assessment

Use the intended profile and region explicitly. Commands are read-only:
`aws sts get-caller-identity`, `aws ec2 describe-instances` (exclude terminated),
`aws bedrock-agent list-agents`, `aws bedrock list-foundation-models --by-output-modality TEXT`,
`aws lambda get-account-settings`, `aws lambda list-functions`, `aws sns list-topics`,
`aws cloudwatch describe-alarms --alarm-name-prefix aiops-`,
`aws logs describe-log-groups --log-group-name-prefix /aiops/`, and
`aws events list-rules --name-prefix aiops-`. Use pagination, keep raw account output
private, and summarize only project resources. The private inspection snapshot and
its script hash are referenced in the sanitized evidence.

Do not run setup/deploy scripts, sample-data generation or alarm injections as a
read-only preflight. New services and their integration checks are later-phase work.
Nothing needs to be created merely to finish the Phase 0 assessment.
