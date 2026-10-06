# Model-runtime compatibility and budget decision

Discovered during Phase 3 on 6 October 2026. The user selected **code-owned Python
runtime using Bedrock models**, then clarified that customers must have the option
of **AWS AgentCore or standalone execution**. Both targets run the same owned
orchestration layer. Implement this within Phase 3; no cloud deployment or Phase 4
work is authorized by that selection.

The previous model adapter and Phase 2 agent candidate used Bedrock Agents Classic.
AWS states that accounts without prior qualifying Agents activity cannot create
agents after 30 July 2026. Existing qualifying accounts can continue using the
service. The user confirmed no project EC2/Bedrock infrastructure exists; this
does not establish the account's eligibility. The previous read-only catalog
check did not test CreateAgent eligibility.
[AWS maintenance-mode notice](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html).

The InvokeAgent API does not expose a per-request aggregate token or tool-call
budget. The previous worker enforced local time, number of attempts, concurrent
queue invocations and stored output bytes. These are useful limits; they do not
prove a strict aggregate model-token or CloudWatch scan cap inside the service's
orchestration loop. Closing the client stream also cannot prove that upstream
model/tool execution has stopped. [InvokeAgent API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeAgent.html).

## Recommended project direction

Own the orchestration loop in a portable Python package and use customer-owned
Bedrock model inference. This is a project recommendation based on the open-source,
customer-operated and eventual desktop requirements. Run the same package in a
bounded Lambda worker and offer AgentCore as a selectable customer deployment
target. AWS recommends AgentCore for new agent workloads and supports code-defined
agents there. [AWS migration guidance](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html).

The loop reserves and enforces per-incident model tokens, model steps, tool
calls, CloudWatch query counts/windows and an absolute deadline before starting each
operation. It should persist usage and partial evidence with the incident fence,
stop before the next operation would exceed its allowance, and produce DEGRADED
with an independent follow-up. It must validate model/tool capability and the
applicable tokenizer/counting behavior before enabling automatic investigations.

Preserve the durable ledger/outbox/notification layer. Replace the model adapter,
candidate model/tool binding, IAM policies and verification as one reviewed change.
Port the web chat adapter too so a new deployment can actually use both entry
points. Retain a clearly named Classic adapter only for eligible customers.

## Implementation and remaining verification within Phase 3

The shared loop, durable aggregate reservations, qualified tools, both adapters,
web chat integration, immutable release templates, candidate verification and
paid staging canary path are implemented. See [validation](VALIDATION.md) and
[operator guide](GUIDE.md). Keep the synthetic model paused.

Remaining work is live G2/G3 verification: selected-model Converse/tool/CountTokens
capability, actual IAM scopes, AgentCore boot and exact endpoint binding, concurrent
ledger reservations, worker/host termination, delivery and the 1,000-accepted-event
failure matrix under an approved budget. Unsupported CountTokens fails before
inference. Not every Bedrock model/profile is compatible with this contract.

Reservation is conservative: no refunds after ambiguous requests. Observed usage
is a lower bound if a response is lost. Query counts, time windows, result bytes
and cancellation bound operations but **do not enforce a hard pre-query billed
scan-byte or dollar cap**. This limitation remains part of the open acceptance
work; the plan has not been satisfied by renaming its scan-budget requirement.

## Customer-selectable execution targets

User requirement: support both targets, with a customer choice. AgentCore is a
hosting target for the project's Python loop; it is not a replacement for that
loop. AWS explicitly supports custom agents without a framework.
[AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html).

| Layer | Shared behavior | Target-specific behavior |
|---|---|---|
| Orchestration | Prompt/tool contracts, model loop, authorization, budgets, deadlines, result contract | None: one implementation |
| Standalone target | Calls the Python loop directly | Existing customer Lambda worker first; container/local adapters can reuse it later |
| AgentCore target | Hosts that same Python loop | Customer Runtime endpoint, execution role, session binding and authenticated invocation |
| Incident control plane | Durable acceptance, fenced claims, reservations, evidence/outbox and independent notifications | Same customer ledger; AgentCore sessions do not replace incident records |
| Model provider | Bedrock Converse and model-specific CountTokens | Customer region, qualified model capability and permissions |

Implemented deployment configuration: `runtime_target: standalone | agentcore`.
The current provider is Bedrock. Select the target
in validated deployment/operator configuration, not an arbitrary chat parameter.
The standalone label does not mean a local/offline model: Bedrock still needs
customer credentials and network access. The desktop phase remains later.

Implementation order within P3.05/P3.07/P3.08:

1. Define a versioned request/result contract and implement the shared Python loop
   with injected model, tool, budget and checkpoint interfaces.
2. Integrate direct execution into the existing worker and web chat. Keep incident
   budgets durable across all attempts and both targets.
3. Add an AgentCore host exposing the documented HTTP health/invocation contract
   and a bounded authenticated client using `InvokeAgentRuntime`. Bind each call
   to its customer, incident, attempt, fence, absolute deadline and release.
   The remote host must verify current ownership and reserve budget before every
   model/tool operation; caller-supplied counters or a disconnected stream cannot
   authorize continued work. Interactive sessions need a separate identity and
   conversation namespace.
4. Add immutable artifact/model/tool bindings, scoped execution/caller IAM,
   customer-owned deployment templates, candidate verification and rollback for
   each target. No Agents Classic creation dependency in either new-account path.
5. Exercise identical contract/budget fixtures for both adapters, plus remote
   acknowledgement loss, caller/host termination, stale fences, session isolation
   and target switching. Qualify each deployed target with actual AWS evidence.
6. Document customer selection and costs. Switching an active incident deployment
   requires pausing investigations and resolving active leases before promotion.
   Do not automatically fail over between targets or dispatch the same attempt to
   both: ambiguous completion can otherwise repeat billable work. Initial alerts
   remain independently queued throughout.

AgentCore uses a distinct service/API from Agents Classic. HTTP hosting requires
the published service contract; the data-plane permission is
`bedrock-agentcore:InvokeAgentRuntime` for the intended Runtime resource.
[HTTP contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html),
[invocation API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html).

Framework recommendation, not a user-selected dependency: use the existing SDK
and a small owned loop for the current bounded investigation. LangGraph is a
candidate if explicit branching, human approval or resumable reasoning later
requires graph orchestration; it can run without LangChain. LangChain supplies
model/tool abstractions, and LlamaIndex supplies data/retrieval and agent workflows;
neither is currently required by the two-target requirement. Keep these concerns
behind interfaces rather than introducing three overlapping frameworks.
[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview),
[LangChain](https://docs.langchain.com/oss/python/langchain/overview),
[LlamaIndex](https://developers.llamaindex.ai/python/framework/).

All infrastructure, credentials, model charges and AgentCore charges belong to
the customer. Maintainers provide open-source code and deployment instructions,
with no hosted control plane or maintainer-operated managed service.

This document records the decision and its implementation. All Phase 3 tasks are
VERIFYING after local checks; no live acceptance gate has passed. Standalone is
the default to avoid requiring AgentCore charges. See
[deployment and cost](DEPLOYMENT_AND_COST.md) for customer setup responsibilities.
