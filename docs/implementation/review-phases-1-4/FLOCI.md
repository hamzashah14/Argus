# Floci assessment and proposed local integration plan

Checked primary documentation on 6 October 2026. **Recommend Floci for a scoped
local integration layer, followed by a small separately budgeted AWS staging
qualification.** No Floci installation, Docker startup or cloud work was performed.
This recommendation does not change the customer-owned AWS operating model.

Floci is an open-source local AWS emulator with SDK-facing APIs and Docker-based
Lambda execution. It is promising for inexpensive repeated queue/storage/handler
integration exercises. Exact operation behavior needs a pinned-version trial;
the project is not currently integrated with it.
[Floci project](https://github.com/floci-io/floci).

## Compatibility that matters for this project

| Area | Primary documentation and project dependency | Decision |
|---|---|---|
| DynamoDB | Documents transactions, GSIs and Streams. Its native backend omits expired items from reads before a 60-second deletion sweep. AWS TTL timing must not be inferred from this behavior. | Trial ledger transactions, conditional fencing, queries, stream recovery and contention; separately inject still-present expired rows. [DynamoDB docs](https://floci.io/floci/services/dynamodb/) |
| SNS/SQS/S3/Lambda | These are candidate local pipeline services, including Lambda event source mappings. Documented SQS mapping maximum concurrency is stored but not enforced; invocation is serialized per mapping. | Test real messages/persistence/partial batches; use a separate concurrency fault harness. A local load result will not establish two-worker AWS throughput. [Lambda docs](https://floci.io/floci/services/lambda/) |
| Logs Insights | Documented query subset excludes `stats` and regex `like` filtering. Our log tool uses both, including `stats count(*) ... by bin(...)`. | Current log tool cannot be assumed to work unchanged. Record unsupported queries; use an explicitly labelled scripted adapter for orchestration tests or add upstream compatibility before claiming exact tool integration. Do not weaken production queries for the emulator. [CloudWatch docs](https://floci.io/floci/services/cloudwatch/) |
| Bedrock | Default Converse backend is canned; optional proxy connects to an OpenAI-compatible backend such as local Ollama. CountTokens is not listed among documented operations, while our runtime requires it before inference. | Mandatory CountTokens/token-accounting capability probe on the pinned version. Until proven, scripted model tests; proxy inference remains a separate optional experiment with explicit compute/provider costs. [Bedrock Runtime docs](https://floci.io/floci/services/bedrock-runtime/) |
| AgentCore | Runtime control plane is metadata emulation; InvokeAgentRuntime returns a fixed non-streaming JSON response and does not execute the uploaded host. Our client requires bounded SSE from our host. | No end-to-end AgentCore qualification through this stub. Run our actual host locally for HTTP/SSE/deadline tests; use real AgentCore later for ARM64 boot, isolation and service permissions. [AgentCore docs](https://floci.io/floci/services/bedrock-agentcore/) |
| CloudFormation | SetStackPolicy is documented as a no-op and GetStackPolicy returns an empty policy; ValidateTemplate is a stub. Our gates require the exact sealed policy. | Unmodified sealed release workflow is incompatible with that documented behavior. Keep strict AWS gates; trial lower-level component setup or a distinctly labelled local deploy harness. Never accept a local receipt as an AWS promotion receipt. [CloudFormation docs](https://floci.io/floci/services/cloudformation/) |
| IAM | Enforcement is disabled by default. Even with it enabled, supported condition keys and service role behavior need contract testing. | Enable it for explicit denial tests, and separately retain real AWS least-privilege qualification. Permissive local success is not security evidence. [IAM docs](https://floci.io/floci/services/iam/) |

CloudWatch EMF extraction, alarms/schedules, exact filters, S3 version/KMS behavior,
Lambda retry/DLQ semantics and the project's AgentCore CloudFormation resource
types also need explicit probes. Service-name support alone does not establish
compatibility. No pinned Floci version was run, so the table is a documentary
assessment, not a measured compatibility result.

## Step-by-step proposal

1. **Fix the existing release/recovery/observer review blockers first.** Preserve
   the current architecture and scope; Phase 5 remains awaiting user direction.
2. **Create an explicit local environment.** Separate fake account/region/config,
   dummy credentials, local evidence and clear LOCAL EMULATION UI/status labels.
   Do not load the operator's AWS profile or mount their `.aws` directory. Pin a
   reviewed Floci release and image digest; no floating `latest` in repeatable CI.
3. **Enforce endpoint isolation.** Provide one reviewed client/resource factory
   used by CLI, worker, tools, UI and tests. Audit direct boto3 resource/client
   creation. Host and container endpoint addresses differ; configure each
   explicitly. Deny AWS/metadata egress in the local harness and fail if a required
   service lacks a local endpoint. Do not turn off reference-only cloud protection
   just to make the AWS deployment CLI accept fixtures.
4. **Run a minimal capability matrix before a full stack.** Conditional/transaction
   operations and GSI/stream behavior; SQS visibility/partial batch/DLQ; SNS
   attributes/filter delivery; versioned S3 evidence; Lambda packaging/qualified
   invocation; Logs Insights query results; CountTokens/Converse; IAM denial;
   CloudFormation stack seals; metric/alarm behavior. Record supported, unsupported
   and behavior differences against the pinned emulator version. Fail rather than
   silently skipping required contracts.
5. **Build a separate local component harness.** Deploy only the supported durable
   foundation/queues/handlers. Run the real code-owned orchestration and HTTP host
   locally with controlled scripted model/tool behaviors for gaps. Mark every
   adapter/stub in evidence. This tests our logic around the services; it does not
   qualify an unsupported AWS feature. Keep strict AWS deployment verification.
6. **Run deterministic integration faults.** Duplicate/reordered ingress, stopped
   dispatcher/reconciler, lost queue acknowledgement, concurrent claims, process
   kill, deadline exhaustion, storage failure, third notification ambiguity and
   duplicate canary receipt. Reconcile at least 1,000 accepted events to terminal
   or recoverable records without paying for 1,000 model invocations. Supplement
   emulator-serialized consumers with an explicit parallel harness. Test container
   restart/state persistence as a separate durability scenario.
7. **Add reproducible local CI and documentation.** Start with empty isolated
   state, wait for health, run the contract/fault suites, collect sanitized evidence
   and clean up owned local containers/volumes. Label receipts as local, keep
   unsupported cases visible and retain hosted CI as pending until it actually runs.
8. **Perform a small AWS qualification later.** Use one customer staging target,
   a supported model and approved budget/time window. Verify actual role denials,
   model tools/CountTokens, AgentCore boot/SSE if selected, queue/stream behavior,
   real notification mailboxes, exact metrics and rollback. Preserve the other
   load/fault/soak gates until completed; a smoke test alone does not close them.

Daily development can therefore proceed without repeatedly paying AWS for every
test. Floci still uses local machine resources, and a proxy configured with a paid
provider can incur charges. It does not host a deployed customer application or
replace the cloud telemetry that a real customer must supply. Standalone remains
the simpler initial deployment target; AgentCore stays an optional customer choice.
