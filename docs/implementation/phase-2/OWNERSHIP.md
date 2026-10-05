# Phase 2 resource ownership and migration decisions

Reference scope: `kira/staging`, synthetic account `123456789012`, same-region
example in eu-central-1. Generated templates also validate a split-region variant.
No resource in this document has been discovered or created in the customer's AWS
account. Review the actual private plan/change sets before provisioning.

| Resource family | Owner | New deployment | Existing deployment migration | Retirement |
|---|---|---|---|---|
| Artifact buckets | Regional foundation | New versioned private bucket for each purpose | Never adopt by matching a name; explicit CloudFormation import review only | Retain bucket and object versions; manual cleanup after rollback window |
| Cursor secret | Tools foundation | Generated value, later pinned by release label/VersionId | Create an environment-specific secret; old cursor tokens may expire | Retain; keep labeled versions required by retained releases |
| Telemetry log groups | Monitoring foundation | Names from environment + inventory | Move producer config after staging validation; importing an existing group needs a separate reviewed ownership plan | Retain old groups/history; never delete by prefix |
| Metric filters | Monitoring foundation | Exact configured positive/negative fixtures | Validate the customer's actual log format, then replace only owned filters | CFN removes retired filters; logs stay retained |
| Tool functions, versions, agent and alias | Release stacks | New release-specific resources | Replace legacy mutable `aiops-*` functions/agent; never update them in place from the new workflow | Keep sealed stacks and permissions through rollback window |
| Investigation worker | Release stack | New numbered version bound to candidate alias | New worker; routing switches only after canary | Keep previous worker/role/version; do not remove its grants during candidate setup |
| Alarms / EventBridge rule | Routing stack | Inventory-derived alarm names and exact instance event pattern | New environment resources; inspect old legacy rules/alarms separately before retiring them | Disable obsolete owned alarm actions first; CFN removes alarms; preserve unrelated resources |
| SNS subscribers | Routing stack | Lambda subscription plus explicit customer recipient | Never enumerate/delete arbitrary account recipients | Unsubscribe exact stack-owned obsolete endpoint before routing update; verify new confirmation |
| Runtime roles | Owning stack | Separate tools/agent/worker/UI/CI roles and Phase 3 identity boundaries | Replace broad shared legacy roles; no automatic revocation of unrelated roles | Retain release roles along with functions |
| CloudFormation deployment role | Customer bootstrap/IAM system | Customer creates/reviews it | Reuse only after scope review; never delegate to UI/application | Customer IAM lifecycle |
| CI and UI bootstrap principals | Customer identity system | Existing distinct roles required | Customer selects workload/OIDC/SSO trust | Customer identity lifecycle |

The new stack lifecycle does not automatically import untagged legacy resources.
If a stack with the target name exists without exact Project/Environment/ManagedBy
tags, mutation is rejected. CloudFormation import is intentionally a separate
operator-reviewed action; it is not guessed from a function or topic name.

The configured account was previously assessed as having no project resources.
Therefore the default migration is **new environment-scoped creation**, not import.
For a future existing customer, retain the old path while validating the candidate,
review ingress/recipient cutover, then disable and retire the old owned path under
that customer's approval. The new reconciler does not claim ownership of legacy
unmanaged recipients; leaving both paths enabled could duplicate alerts.

`log_segment` supports a reviewed prefix change within the same environment.
The new log groups are created and the old ones retained; filters move through a
reviewed foundation change set. Move producer configuration deliberately, then
validate telemetry and build a new catalog/log-scope release before promotion.
A project/environment rename is a new ownership boundary and requires an explicit
migration review, not automatic retirement of the former stack.

Rollback_days is the minimum retention policy, not an automatic deletion timer.
There is no deletion-by-age command. Record retained releases and their dependents
privately; only remove them after no active UI, ingress, secret pin or rollback
procedure references them.

## Verified reference sources (2026-10-05)

- [Lambda Version resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-version.html): numbered snapshot and CodeSha256 guard.
- [Bedrock Agent](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html) and [AgentAlias](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agentalias.html): candidate resources, preparation and routing metadata.
- [Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html): capacity checks retain the required unreserved pool.
- [EventBridge PutTargets](https://docs.aws.amazon.com/eventbridge/latest/APIReference/API_PutTargets.html): per-entry failures require inspection.
- [CloudFormation stack policy](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html): update guard, separate from IAM authorization.

These service references informed implementation. They are not evidence of a
successful deployment or compatibility of this candidate with a chosen live model.
