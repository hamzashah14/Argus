# Deployment location and cost responsibilities

The customer owns every AWS resource, credential, identity provider, mailbox and
bill. There is no required maintainer service or subscription.

| Location | What runs there |
| --- | --- |
| Administrator workstation | Python deployment/build CLI, private settings and reviewed receipts |
| Customer AWS regions | Tools, pipeline, chat gateway, storage, notifications, alarms and optional AgentCore/observers |
| Monitored customer EC2 servers | Application, CloudWatch agent, heartbeat and telemetry configuration |
| Customer UI machine/host | Streamlit, scoped AWS workload credentials and native OIDC secrets |
| Customer identity provider/mailboxes | Authentication/MFA and recipient confirmation/delivery checks |

The backend does not require a dedicated EC2 server for Kira. `standalone` uses
Lambda; `agentcore` adds separate runtime hosts/endpoints. The UI can run locally,
and cloud alerts continue when it is closed. An always-on shared UI needs separate
customer hosting, HTTPS/proxy and network controls. The deployment CLI does not
create that host or install monitored-server software.

Costs depend on the account, regions, model, fleet, schedules, retention and usage.
Review Bedrock inference, CloudWatch log ingestion/querying/metrics/alarms,
Lambda, DynamoDB/PITR, S3/versioning, KMS, Secrets Manager, SNS/SQS, CloudTrail data
events and optional AgentCore. Retained storage, keys and alarms can keep incurring
charges even when investigations or observers are paused.

Set explicit approved token/query budgets, capacity and retention before applying.
Model reservations and query counts are execution bounds, not a hard dollar cap.
Logs Insights has no implemented pre-query maximum billed-byte setting. Billing
notifications are not automatic shutdown. Verify actual regional usage and costs
in the customer's bounded staging pilot before enabling production.

The [automation guide](DEPLOYMENT_AUTOMATION.md) explains previews and billable
apply. The [operations runbooks](OPERATIONS.md#maintenance-and-cost-emergency)
describe pausing model work while retaining capture and initial notifications.
