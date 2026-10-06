# G4 staging acceptance — NOT_RUN

This is the execution matrix for an **approved customer staging deployment**.
There is no project AWS infrastructure or real service/recipient evidence yet.
G1 hosted CI and live G2/G3 also remain pending. All 20 findings remain OPEN;
P4.01–P4.06 remain VERIFYING despite passing repository tests. Production handover
requires later phases too. Do not create resources from reference-only fixtures.

Freeze source, qualified artifacts, bundle/spec/config hash, inventory, model/target,
identities, owners and approved budget. Record all UTC transitions, intended metric
samples, initial notification timestamps, receipts, recovery links and safe causes.
Raw logs, cloud API responses and contacts belong in ignored private evidence.

| Task/scenario | Required actual result | Status |
|---|---|---|
| P4.01 stopped listener; EC2 still running | Availability alarm, accepted incident and actual initial receipt within measured target | NOT_RUN |
| P4.01 stalled headers/trickling body/DNS or TLS failure | Whole-route timeout enforced; no hanging observer; diagnosis distinguishes network evidence | NOT_RUN |
| P4.01 stopped Nginx and an unhealthy essential dependency | Readiness fails independently of process/instance metrics; each initial receipt observed | NOT_RUN |
| P4.01 restore each fault | Healthy samples/OK observed and atomic link to preceding incident, including delayed/duplicate OK | NOT_RUN |
| P4.02 stop CWAgent, then stop heartbeat timer, then break log shipping | Distinct fresh-metric/heartbeat failures; telemetry alarm and receipt; no invented application hang | NOT_RUN |
| P4.02 idle healthy service, log rotation and clock skew | Sparse business logs stay idle; explicit heartbeat works; invalid/future timestamps fail | NOT_RUN |
| P4.02 maintenance entry/exit | Planned service/check suppression; observer monitoring remains; resume/bootstrap and receipt proven | NOT_RUN |
| P4.03 exact fleet/metric coverage | Every mandatory instance, namespace/dimension/disk path/process descriptor and owner matches published evidence | NOT_RUN |
| P4.03 real sanitized Nginx | Actual format/timezone/status extraction, 500/502/503/504 positive, byte/status negative cases; separate request vs diagnostic counts | NOT_RUN |
| P4.03 replace/scale instance | Reviewed inventory refresh/new release and retirement; no orphan or silently unobserved member | NOT_RUN |
| P4.04 trace one incident | Ingest/dedupe/queue/attempt/tool/model/report/publish/receipt fields correlated; no raw secrets; retention verified | NOT_RUN |
| P4.04 model denied/outage, tool error/no-data, deadline/report failure | Distinct logs/outcome metrics/dashboard evidence; durable terminal/degraded accounting | NOT_RUN |
| P4.05 disable primary notifier or mapping | Expectation exists, initial delivery missing; independent CloudWatch fallback receipt observed | NOT_RUN |
| P4.05 remove/unconfirm/filter primary or test subscriber | Registration rejects drift; canary/fallback detects lost receipt; actual mailbox checks remain distinct | NOT_RUN |
| P4.05 disable sender/observer/receipt consumer | Missing canary/heartbeat/Lambda/queue alarm reaches working independent route | NOT_RUN |
| P4.05 transport denied, DLQ growth, queue age/stale outbox | Signal/action owner proven; safe recovery, no drops or unexplained deletions | NOT_RUN |
| P4.05 fresh/stale/missing real inbox attestation and recipient change | Actual received ID required; old-recipient/future/expired attestation does not qualify delivery | NOT_RUN |
| P4.05 fallback route fault/exercise | Native failed-delivery/configuration signal reaches primary route; fallback inbox receipt independently retained | NOT_RUN |
| P4.06 second-operator runbooks | Named primary/backup follow safe replay, collector/model/recipient/credentials/cost/maintenance recovery without implementer intervention | NOT_RUN |

Public acceptance evidence must summarize timings and outcomes without customer
identifiers or raw payloads. Use ledger accounting for accepted events; approximate
metric counters are supporting diagnostics. Both runtime targets need their actual
qualification if offered as supported deployments. Linux collector checks do not
prove Windows telemetry support. Private-only network endpoints and automatic
fleet discovery are outside this adapter and need explicit additional work.

Completion requires successful fault/recovery records for every row, signed
customer operational ownership, actual primary/fallback receipts, verified budgets
and no unexplained backlog/drop. Update tracker gates/findings only when their
individual remediation acceptance requirements pass; passing G4 alone does not
imply G6 production qualification.
