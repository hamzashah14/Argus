# Customer production acceptance checklist

Use an approved customer staging deployment and private evidence. Do not deploy
synthetic reference inputs. Backend provisioning is distinct from production
acceptance; keep automatic investigation paused while qualifying the release.
The repository has local automated validation; live AWS, identity, load, recovery
and real inbox delivery still require customer verification.

Freeze source, qualified artifacts, bundle/spec/config hash, inventory, model/target,
identities, owners and approved budget. Record all UTC transitions, intended metric
samples, initial notification timestamps, receipts, recovery links and safe causes.
Raw logs, cloud API responses and contacts belong in ignored private evidence.

| Task/scenario | Required actual result | Status |
|---|---|---|
| stopped listener; EC2 still running | Availability alarm, accepted incident and actual initial receipt within measured target | Pending customer verification |
| stalled headers/trickling body/DNS or TLS failure | Whole-route timeout enforced; no hanging observer; diagnosis distinguishes network evidence | Pending customer verification |
| stopped Nginx and an unhealthy essential dependency | Readiness fails independently of process/instance metrics; each initial receipt observed | Pending customer verification |
| restore each fault | Healthy samples/OK observed and atomic link to preceding incident, including delayed/duplicate OK | Pending customer verification |
| stop CWAgent, then stop heartbeat timer, then break log shipping | Distinct fresh-metric/heartbeat failures; telemetry alarm and receipt; no invented application hang | Pending customer verification |
| idle healthy service, log rotation and clock skew | Sparse business logs stay idle; explicit heartbeat works; invalid/future timestamps fail | Pending customer verification |
| maintenance entry/exit | Planned service/check suppression; observer monitoring remains; resume/bootstrap and receipt proven | Pending customer verification |
| exact fleet/metric coverage | Every mandatory instance, namespace/dimension/disk path/process descriptor and owner matches published evidence | Pending customer verification |
| real sanitized Nginx | Actual format/timezone/status extraction, 500/502/503/504 positive, byte/status negative cases; separate request vs diagnostic counts | Pending customer verification |
| replace/scale instance | Reviewed inventory refresh/new release and retirement; no orphan or silently unobserved member | Pending customer verification |
| trace one incident | Ingest/dedupe/queue/attempt/tool/model/report/publish/receipt fields correlated; no raw secrets; retention verified | Pending customer verification |
| model denied/outage, tool error/no-data, deadline/report failure | Distinct logs/outcome metrics/dashboard evidence; durable terminal/degraded accounting | Pending customer verification |
| disable primary notifier or mapping | Expectation exists, initial delivery missing; independent CloudWatch fallback receipt observed | Pending customer verification |
| remove/unconfirm/filter primary or test subscriber | Registration rejects drift; canary/fallback detects lost receipt; actual mailbox checks remain distinct | Pending customer verification |
| disable sender/observer/receipt consumer | Missing canary/heartbeat/Lambda/queue alarm reaches working independent route | Pending customer verification |
| transport denied, DLQ growth, queue age/stale outbox | Signal/action owner proven; safe recovery, no drops or unexplained deletions | Pending customer verification |
| fresh/stale/missing real inbox attestation and recipient change | Actual received ID required; old-recipient/future/expired attestation does not qualify delivery | Pending customer verification |
| fallback route fault/exercise | Native failed-delivery/configuration signal reaches primary route; fallback inbox receipt independently retained | Pending customer verification |
| second-operator runbooks | Named primary/backup follow safe replay, collector/model/recipient/credentials/cost/maintenance recovery without implementer intervention | Pending customer verification |

Public acceptance evidence must summarize timings and outcomes without customer
identifiers or raw payloads. Use ledger accounting for accepted events; approximate
metric counters are supporting diagnostics. Both runtime targets need their actual
qualification if offered as supported deployments. Linux collector checks do not
prove Windows telemetry support. Private-only network endpoints and automatic
fleet discovery are outside this adapter and need explicit additional work.

Completion requires successful fault/recovery records for every row, signed
customer operational ownership, actual primary/fallback receipts, verified budgets
and no unexplained backlog/drop.

Also complete these deployment-specific checks:

- [ ] Hosted CI passes on the frozen source and hash-verified dependency locks.
- [ ] Exact model CountTokens/Converse tools, model IAM, entitlements and quotas work.
- [ ] Sealed functions, artifacts, runtime endpoints and policies match the reviewed bundle.
- [ ] Native OIDC/MFA, callbacks/origins, viewer/investigator scopes, revoked grants,
      session expiry and fail-closed storage behavior pass [identity acceptance](IDENTITY.md#live-acceptance).
- [ ] Chat and alert load, distributed allowances, queue capacity, deadlines and
      hard worker termination/recovery meet customer targets without unexplained drops.
- [ ] Redaction, audit receipt/integrity, retention, all-version erasure and isolated
      backup restore pass [security operations](SECURITY_OPERATIONS.md).
- [ ] Immutable-release rollback and target switching preserve event accounting,
      epochs, pinned policies and conservative model/tool reservations.
- [ ] HTTPS incident links require authorized access; primary and fallback inboxes
      actually receive messages. Deployment status alone does not prove delivery.
- [ ] Named primary/backup operators, service owners, budget and security owners
      approve handover, emergency procedures and any time-limited exceptions.

Qualify each offered runtime target separately. Production cutover and enabling
investigations require a reviewed customer release procedure after these checks;
the automation CLI does not bypass the staging-only paid canary restriction.
