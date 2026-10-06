# Customer deployment, manual work and cost

Recorded 6 October 2026 in response to the user's affordability question.
This is customer-operated open-source software. Maintainers do not need to run
a shared production account, subscription service or hosted customer database.
Each operator owns credentials, infrastructure, data and its cloud bill.

## Where the project runs

| Component | Deployment location | Always-on customer server required? |
|---|---|---|
| Web chat and incident viewer | Customer laptop or existing Python/Streamlit host | Only while using the UI; a stable hosted UI is needed for reachable notification links |
| Automatic capture, queues, ledger, evidence and notifications | Customer AWS: Lambda, SQS, DynamoDB, S3/KMS, SNS, CloudWatch/EventBridge | No EC2 instance dedicated to Kira |
| Standalone investigation (default) | Customer Lambda worker; chat uses the UI process | No separate agent host; both still call paid Bedrock inference |
| AgentCore investigation (optional) | Customer AgentCore Runtime and pinned endpoint, with the same ledger/tools | AWS-hosted runtime with additional consumption charges |
| Monitored workloads | Customer's existing application infrastructure | Application costs are separate; Kira does not create the application/EC2 fleet |
| Desktop application | Later phase, on the user's Mac/Windows computer | Not implemented; still needs customer cloud access |

Automatic alerts continue when the laptop/UI is closed because the event pipeline
runs in AWS. Local UI alone does not provide a stable HTTPS notification link.
The current durable config requires a fixed HTTPS status URL; the customer must
provide an appropriately authenticated, reachable UI for the complete linked
notification workflow. An existing internal host with TLS can be used; a new paid
public domain/hosting subscription is not an intrinsic requirement. Do not deploy
the synthetic `.invalid` URL or expose the unfinished multi-user UI publicly.
Authentication and per-user controls remain later Phase 5 work.

## Manual setup that remains

One-time customer choices and authorization cannot be inferred by software:

1. Provide an AWS account and deployment identity, configure CLI/SSO credentials,
   and select allowed regions, runtime target and a supported Bedrock model. Model
   permissions, any provider entitlement steps and actual quotas must be verified.
   Standalone does not require creating an Agents Classic agent or AgentCore Runtime.
2. Declare the real service/instance inventory, owners, log groups and monitoring
   scope. Install/configure telemetry collectors on monitored workloads as required;
   the templates do not install the CloudWatch agent on an existing EC2.
3. Bootstrap distinct customer IAM identities/deployment permissions, review the
   generated resource/change plan, and execute the documented staged deployment.
   The CLI generates and verifies templates/artifacts; currently the operator
   collects bindings and approves stages as described in [GUIDE.md](GUIDE.md).
   This checkpoint does not supply a completed one-click installer.
4. Choose primary/fallback recipients and confirm SNS email subscriptions. Supply
   a stable HTTPS status URL if using notification links. Slack/other connectors
   are not implemented merely because SNS email works.
5. Set retention and a spending budget, run staging validation, and enable automatic
   investigations only after the selected target/model passes. Resolve the recorded
   Lambda concurrency gap rather than assume reservations will be accepted.

Routine ownership also remains: renew SSO sessions where needed, update dependencies
and releases, review failed delivery/DLQs, investigate telemetry gaps, maintain
retention/backups, approve inspected replay and respond to incidents. Current tools
read evidence; they do not repair customer applications automatically. Later release
packaging may simplify setup, but cannot remove customer authorization/ownership.

## Affordable recommended path

Continue with offline fixtures and local tests while developing: these do not call
AWS and incur no AWS usage charges. No infrastructure has been deployed by this
implementation session. Local **live** chat is different: it calls Bedrock/tools.

For the first live pilot, use the local UI or an existing host, standalone execution,
one existing service and one region that supports the selected model and required
APIs. Keep automatic investigations paused until measured pilot cost is acceptable.
Avoid a dedicated EC2 host, load balancer or NAT gateway just to run Kira; the
current default does not require them. AgentCore remains optional. Do not remove
durable storage, independent initial notifications or encryption solely to make
an untested production architecture appear cheaper.

AWS is not free because the code is open source. Relevant billing dimensions:

- Bedrock inference is priced by the selected model and input/output use. Reserved
  token counters constrain operations, not a universal dollar price.
  [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).
- Lambda execution/requests, queues, database requests/storage/PITR, object versions,
  notifications, logs/query scans, metrics and alarms contribute to the bill.
  [Lambda pricing](https://aws.amazon.com/lambda/pricing/),
  [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/).
- KMS customer keys and the cursor secret have storage/key and request charges;
  pausing the model does not remove these or other provisioned/storage charges.
  [KMS pricing](https://aws.amazon.com/kms/pricing/),
  [Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/).
- AgentCore adds Runtime CPU/memory consumption and related storage/network costs.
  The caller Lambda waits for the remote result, so its duration and AgentCore
  session can both be billed. It is not a cost-free replacement for the worker.
  No paid LangSmith/framework service is required by the owned loop.
  [AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/).

Keep retained release stacks/artifacts and staging duplication in estimates;
retention needed for rollback is not automatic resource teardown. Idle infrastructure
can still cost money. Free-tier credits/eligibility cannot be assumed for this account.

Before provisioning, estimate the actual model, region, service count, alarms,
log ingest/query volume, incidents and manual chats. There is no defensible fixed
monthly total without those inputs. Use the
[AWS Pricing Calculator](https://calculator.aws/) and record pilot usage separately
from the customer's application bill. Billing alerts are notifications, not an
instant hard spending cutoff. Existing limits bound automatic incident attempts,
tokens and queries; Insights has no enforced pre-query billed-byte cap here, and
chat quotas per user are still pending Phase 5.

Maintainer cost can stay at local development plus any explicitly approved pilot;
customers pay for their own deployments. If even a small live trial is unaffordable,
continue offline and keep live production qualification pending rather than promise
that mocks prove production behavior.
