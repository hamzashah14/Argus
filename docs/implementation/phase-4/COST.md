# Phase 4 cost and setup

Everything remains customer-operated. The web UI can run locally or on an existing
customer host; automatic alerts and these observers run in the customer's AWS
account. No new EC2 instance, NAT gateway, load balancer, paid framework, CloudWatch
Synthetics browser or AgentCore deployment is required by these additions.
AgentCore remains an optional Phase 3 choice. No cloud charges were incurred by
Phase 4 local tests/builds; no project resources were created.

Manual setup is still required for real inventory/readiness semantics, customer
IAM/SSO and quotas, collectors and the heartbeat timer, subscription confirmation,
private deployment inputs, reviewed change sets, staging qualification and periodic
mailbox/fallback tests. The code supplies templates, checks and runbooks; it does
not create application infrastructure or operate it for the customer.

Default enabled schedules generate 288 observer invocations and one marked
synthetic notification per day. Each service adds one custom metric per route and
one freshness metric; outcome EMF metrics, operational/service alarms, the dashboard,
log ingestion/storage/query scans and AWS requests/storage also affect cost.
The three new Lambdas, receipt SQS/DLQ and SNS topics use customer resources.
EMF does not make custom metrics free. Native/custom metrics, alarms, dashboards
and log usage have distinct billing rules; pricing/free-tier eligibility varies.
See [current CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) and
[AWS Pricing Calculator](https://calculator.aws/). No fixed monthly price is
promised without real regions, fleet, query volume and approved usage.

Use one existing service and standalone execution for an approved small pilot.
Keep `enabled: false` and `investigation_paused: true` until that approval; local
build/render/test commands cost no AWS usage. Daily canaries are cheaper/quieter
than hourly ones but detect some primary pipeline failures more slowly. Slower
observer schedules trade freshness for fewer requests; custom-metric/alarm/storage
costs are not necessarily reduced proportionally. Opening/refreshing the dashboard's
Logs Insights widget can incur scan charges; limit its time window and refreshes.
Billing alerts are notifications, not an instant spending cutoff.

Pausing schedules stops their work but does not remove provisioned alarms, retained
log/storage/keys/secrets or the Phase 3 pipeline's ongoing costs. Follow the cost
emergency runbook; preserve capture/evidence and explain backlog rather than
removing safeguards to claim production qualification. If a pilot is unaffordable,
keep G4 pending and continue offline. [Phase 3 cost guide](../phase-3/DEPLOYMENT_AND_COST.md)
contains the complete base architecture's billing and deployment choices.
