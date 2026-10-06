# Detection and observability design

One customer-owned deployment, no hosted maintainer service. Extend the reviewed
inventory with optional explicit observation settings; old Phase 2/3 configurations
remain valid. All new schedules disabled in synthetic fixtures. No model inference
is needed for a delivery canary. Use current durable acceptance/initial alerting.

- Public HTTPS readiness/dependency routes from a pinned release configuration;
  no arbitrary user URL, redirect, query credential, private/metadata destination or
  payload logging. Run outside the application process. Private VPC-only endpoints
  need a reviewed network adapter; public-worker reachability must not be assumed.
- Validate observed metric timestamps and collector/log heartbeat expectations.
  Sparse request/error logs are not collector heartbeats. Collectors should emit
  an explicit periodic log heartbeat; missing business traffic stays unknown/idle.
  Maintenance suppresses application/freshness actions while pipeline monitors run.
- Map every service alarm to its exact descriptor, owner and evidence source.
  Count Nginx 500/502/503/504 requests from access logs separately from error-log
  diagnostic events. Never sum those as if they were unique failed requests.
  Inventory drift blocks verification; autoscaled fleets need explicit refresh.
- Structured safe logs with incident/fence identifiers and bounded outcome codes;
  use low-cardinality metric dimensions, never customer payloads, secrets or IDs
  as metric dimensions. Use existing CloudWatch/queues/ledger, no added agent framework.
- Independent sender publishes a validated synthetic source through ingress and
  initial notification, with no WORK intent. A separate recipient queue/consumer
  stores an actual recipient receipt. An independent verifier checks expected
  incident and receipt deadlines, subscriptions and inbox-check freshness; alerts
  go directly to fallback rather than through the possibly failed primary notifier.
  SNS email has no native inbox delivery proof; trusted operator receipt attestation
  and periodic real-channel exercises stay distinct from SQS recipient proof.
- Avoid hourly inbox spam by default: daily synthetic notification, checks every
  five minutes. Frequency/threshold/retention and added CloudWatch costs are explicit.
  Independent CloudWatch missing-heartbeat alarms watch the observer itself.

G4 requires live stopped listener/hung readiness/dependency failure/recovery,
stopped collector/log shipper, exact sanitized log fixtures and primary notifier/
subscription fault tests. Local mocks and rendered templates do not close findings.
