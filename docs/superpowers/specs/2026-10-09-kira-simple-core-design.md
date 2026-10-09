# Kira simple core: design

Status: draft for review. Nothing in this document is implemented yet.

## 1. Purpose

Kira helps people investigate incidents on their own servers by reasoning over
the CloudWatch logs and metrics they already have. Today a newcomer must create
three IAM roles, fill in three JSON files, put a CloudWatch agent on every
server with a fixed log-group layout, and run a ten-stage deployment before the
first answer. That is too much for a first try and too much for most teams.

This design makes Kira easy to adopt in two ways of working:

- **Individual:** one person on their own machine, with their own AWS
  credentials and nothing deployed.
- **Team:** several people sharing one hosted instance with sign-in, and
  optionally automatic investigation of the team's CloudWatch alarms.

### Success criteria

1. A person with existing CloudWatch log groups gets a useful, evidence-cited
   answer about a chosen EC2 instance in about 15 minutes, with no deployment.
2. A team gets a shared UI with per-person access, and optional alert
   investigations, from one container and one template, with no IAM roles that
   must exist beforehand.
3. Kira never requires a particular server, agent or log layout. Server
   configuration, telemetry shipping and alarms stay the user's own work. Kira
   documents what is useful and checks readiness, but does not install or
   dictate anything.
4. The investigation engine keeps its current safety properties: read-only
   tools, an explicit allowlist of what can be read, redaction, and bounded
   tokens, tool calls and time.

### Non-goals for the first release

- Installing or configuring agents, log shipping or alarms on servers.
- Automatic remediation. Kira suggests and people decide.
- Clouds other than AWS, and model hosting inside Kira.
- Targets other than EC2 instances. Containers, ECS tasks and Lambda functions
  can be added later as another entry kind with the same shape.
- A durable ledger, leases and fencing for alert processing, and per-person
  grants held in a database. These stay in the archived enterprise code.
- Bedrock AgentCore as a runtime. It can return later as an optional adapter.

## 2. Terms

- **Instance entry:** one EC2 instance in the configuration, with its exact
  instance ID, a human name, and the log groups and metrics Kira may read for it.
- **Engine:** the model loop, the read-only tools, redaction and limits.
- **Allowlist:** the instance entries, log groups and metrics in the
  configuration. Anything not listed is unreachable.

## 3. Configuration: `kira.toml`

One file, read with Python's standard `tomllib`, so there is no new dependency.
It holds no secrets. Secrets are referenced by name or ARN.

```toml
[aws]
region = "eu-central-1"
profile = "default"            # used by individual mode only

[model]
provider = "bedrock"           # "bedrock", "openai" or "anthropic"
id = "your-model-id"
# For openai/anthropic: base_url and the ARN of a Secrets Manager secret
# holding the API key (kept out of this file).

[limits]                       # optional; safe defaults apply
tokens_reserved = 32000
model_steps = 8
tool_calls = 8
log_queries = 24
window_minutes = 15

[[instances]]
id = "i-0aaa0000000000001"     # exact EC2 instance ID, the identifier the tools use
name = "webbff-prod-1"         # the EC2 Name tag, how people and the agent refer to it
service = "webbff"             # optional label that groups instances
log_groups = ["/ecs/webbff-prod"]
log_stream_prefix = "prod-1"   # optional: limits reads to this instance's streams
[[instances.metrics]]
name = "cpu"
namespace = "AWS/EC2"
metric = "CPUUtilization"
```

### Rules

- Instance IDs are unique and match the existing instance-ID format. Names are
  unique. At most 100 instances.
- Log group names must exist in the configured region. A log group may be shared
  by several instances when each sets a distinct `log_stream_prefix`.
- Each instance reads only the log groups it lists, and only the streams that
  start with its prefix when one is set.
- Built-in EC2 metrics (CPU, status checks) work with no entries. Custom
  metrics are listed explicitly with namespace, name and dimensions.
- Unknown keys and malformed values are rejected with an error that names the
  field and never echoes the value.

### Trust boundary

The file is the allowlist. In individual mode the user owns it. In team mode it
lives in the deployment (a container file or a parameter) and users cannot edit
it from the UI. A model request that names an unlisted instance or log group is
rejected before any AWS call.

## 4. Engine and tools

The engine keeps the current model loop, both model providers (Bedrock and the
Model API provider), redaction, the diagnosis validator and the limit checks.

### Tools

| Tool | Purpose | Change from today |
| --- | --- | --- |
| `list_instances` | Returns each configured instance's ID, name, service and which telemetry exists | New |
| `fetch_logs` | Discovers and searches the instance's configured log groups | Reads the explicit mapping instead of deriving groups from `<prefix>/<instance-id>/<suffix>`; applies `log_stream_prefix` |
| `fetch_metrics` | Reads built-in and listed metrics for the instance | Reads the listed metrics from the configuration |

Tools keep taking `instance_id`. The model resolves a name such as
`webbff-prod-2` to its ID through `list_instances`. The runtime's existing
checks (the instance must be allowed, the window and line limits, the response
contract and the redaction) are unchanged.

### Handler placement

The same handler code runs in three places: in the local process (individual
mode and the team container) and in the alert Lambda. The existing
local-tools adapter, which runs the handlers in-process behind the unmodified
`LambdaTools`, becomes the way both local modes call them.

### What is replaced

`KIRA_LOCAL_TOOLS` and its one-file JSON format are replaced by `kira.toml`.
The fixed log-group layout rule is removed.

## 5. Individual mode

Commands (a console script named `kira`, also runnable as `python -m kira`):

| Command | What it does |
| --- | --- |
| `kira init` | Read-only discovery: lists EC2 instances (Name tags), matching log groups and available metrics, and writes a draft `kira.toml` for the user to edit. Refuses to overwrite without `--force` |
| `kira doctor` | Read-only readiness check: credentials and region, each listed instance exists, each log group exists and has recent events, each metric has recent data, the model is configured. Prints the exact fix for each failure. Costs no model tokens unless `--ping-model` is given |
| `kira ask "question" --instance NAME_OR_ID` | One investigation, printed with evidence citations and stated uncertainty |
| `kira ui` | The local Streamlit chat, bound to `127.0.0.1` |

The user's own AWS profile or SSO session is used. A read-only IAM policy file
ships in the repository (log discovery and queries, metric reads, model invoke
or the secret read for a Model API key). Nothing is deployed and no state is
stored.

Security statement for the docs: the process holds the user's read credentials
directly, so Kira's checks are enforced in code and not by IAM. Use a read-only
profile and keep the UI on the loopback address.

## 6. Team mode

One container image (a Dockerfile in the repository) that runs the UI. The user
runs it wherever they already run services. It takes `kira.toml`, Streamlit's
OIDC settings and a task or instance role carrying the read-only policy.

### Sign-in and access

- Authentication is Streamlit's OIDC login against the team's identity
  provider. Multi-factor authentication is enforced at the provider. Kira
  checks the provider's `amr` claim when the provider supplies it and says so
  when it does not.
- Authorization is an allowlist in `kira.toml`:

```toml
[[users]]
sub = "OIDC_SUBJECT"           # the immutable subject, not an email
role = "investigator"          # "viewer" reads reports only; "investigator" may chat
instances = ["webbff-prod-1", "webbff-prod-2"]   # names or IDs; "*" for all listed
```

- A request is allowed only when the signed-in subject is listed, the role
  permits it, and the instance is in the user's list. A signed-in user who is
  not listed sees a message saying so and nothing else.

### State and limits

- No database, signing secret or gateway function. Sessions are Streamlit's.
- Per-user request limits are held in memory per container process.
- Each request writes one structured audit line (time, subject, instance,
  outcome, token counts, never prompt or log content) to standard output, so
  the platform's log service keeps it.

### Trade-offs stated plainly

- Removing someone means editing the allowlist and restarting the container.
- Limits are per process, not shared across containers. Run one container, or
  accept per-container limits.
- There is no per-person revocation list, session store or shared quota. The
  archived enterprise identity module covers those needs.

## 7. Alert mode (optional)

One CloudFormation template creates:

- an input SNS topic that the user's existing CloudWatch alarms publish to;
- an SQS queue with a dead-letter queue and a Lambda that consumes it, running
  the same engine and the same handlers;
- a small DynamoDB table with a time-to-live attribute used only to drop
  duplicate alarm events;
- an optional private, versioned, encrypted report bucket;
- an output SNS topic that receives each investigation report. The user
  subscribes email or a chat integration to it.

### Flow

1. An alarm changes state and publishes to the input topic.
2. The Lambda reads the alarm's instance ID from its dimensions and finds that
   instance in the configuration. If the alarm has no instance ID, or the
   instance is not listed, Kira publishes a short message saying why it did not
   investigate. It never guesses.
3. The Lambda investigates within the configured limits and publishes the
   report text (and the report's object key when a bucket is enabled).

### Choices

- The user's alarms already notify them, so Kira sends no separate first alert.
- The template creates its own roles. Deploying it needs permission to create
  IAM roles but no pre-existing role.
- The configuration is delivered as a Lambda-packaged file or an SSM
  parameter. The model API key, when used, is read from Secrets Manager.
- Spend is bounded per run by the limits and overall by a reserved-concurrency
  parameter. Nothing caps total spend.

### Trade-offs stated plainly

- Delivery is at least once, so a duplicate report is possible when a duplicate
  alarm event slips past the de-duplication.
- There is no ledger, lease or fencing. A stuck run is bounded by the Lambda
  timeout and the dead-letter queue.

## 8. Telemetry is the user's work

Kira does not install agents, ship logs or create alarms. The documentation
gives one page on what makes an investigation useful and optional example
configurations, none of them required:

- At least one log group per instance that contains the application's logs.
- Metrics beyond the built-in EC2 set, such as memory and disk, if the user
  wants the agent to look at them.
- Alarms that carry the instance ID in their dimensions, for alert mode.

`kira doctor` verifies that what the configuration points at really exists and
is recent, and reports gaps without changing anything.

## 9. Code disposition

| Area | Decision |
| --- | --- |
| Model loop, providers, redaction, diagnosis validator, limits, metrics helper | Keep |
| Local-tools adapter and the handlers | Keep, generalize to the explicit mapping, share across all three modes |
| Streamlit app | Keep; add the allowlist and audit line for team mode |
| New | `kira.toml` loader, `kira` CLI, `init`, `doctor`, the alert template and handler, the Dockerfile, the read-only IAM policy |
| Deployment generators, the resumable automation, release sealing, bundle and change-set tooling | Move to an `enterprise` branch |
| Durable pipeline, ledger, observers | Move to the `enterprise` branch |
| Full identity module (grants, sessions, quotas, erasure) | Move to the `enterprise` branch |
| AgentCore runtime | Not in the first release; may return as an optional adapter |

The `v0-enterprise` tag already marks the last state that contains everything.
The `enterprise` branch is created from the commit before the move so the
history stays reachable.

## 10. Security and privacy

- Tools are read-only. Kira does not change servers or AWS resources, other
  than its own alert stack when the user deploys it.
- What can be read is limited to the allowlist, enforced in code before any AWS
  call. In individual and team container modes the credentials can read more
  than the allowlist, so use a read-only role scoped as tightly as the platform
  allows.
- Log and metric excerpts go to the configured model after redaction.
  Redaction is best effort, not a guarantee. With Bedrock they stay in the
  user's account. With a Model API they leave it, and the user's data owner
  must approve that.
- Bounded tokens, tool calls, query windows and time apply in every mode.
- Team mode has per-person access but no shared revocation or quota service.

## 11. Testing and delivery

- Everything is tested offline with fakes, as today. The existing runtime and
  tool security tests stay and must pass unchanged where the behavior is
  unchanged.
- New tests cover the configuration loader (valid and each rejection), the
  allowlist (unlisted instance and log group rejected before any AWS call),
  stream-prefix filtering, `list_instances`, `init` and `doctor` against fake
  clients, the team allowlist and audit line, and the alert handler (instance
  found, not listed, no instance ID, duplicate event).
- The template is linted with cfn-lint in CI.
- The first real AWS check follows the alert milestone and exercises a much
  smaller deployment than today's.
- Continuous integration keeps running on every push to `main`.

## 12. Milestones

Each milestone can be released and used on its own.

1. **Configuration and generalized tools.** `kira.toml` loader, explicit
   instance mapping, `list_instances`, stream prefix, local adapter on the new
   configuration. Acceptance: the engine answers over a fake CloudWatch with
   arbitrary log-group names, and unlisted instances and groups are rejected.
2. **Individual mode.** `kira` console script with `init`, `doctor`, `ask` and
   `ui`, the read-only policy file, and the individual quickstart page.
   Acceptance: a person with existing log groups reaches a cited answer
   without deploying anything.
3. **Team mode.** OIDC login, the allowlist, the audit line, the Dockerfile
   and the team page. Acceptance: a listed user can investigate only their
   instances, an unlisted user cannot, and the audit lines contain no content.
4. **Alert mode.** The template, the handler, de-duplication and the alerts
   page. Acceptance: template lint passes, handler tests pass, and a staging
   deployment in a real account investigates a test alarm.
5. **Consolidation.** Move the enterprise code to its branch, remove what the
   new modes no longer use, and shrink the documentation to the individual,
   team and alert pages plus one telemetry guide.

## 13. Open questions and risks

- **Stream filtering:** confirm that Logs Insights can limit a query to log
  streams by prefix efficiently. If not, filter on the stream name field and
  document the cost.
- **Alarm shape:** confirm which alarm types carry an instance ID in their
  dimensions. Alarms without one produce the "not investigated" message.
- **MFA claim:** confirm what Streamlit's OIDC login exposes. If `amr` is not
  available, Kira relies on the provider enforcing MFA and says so.
- **Duplicate suppression key:** choose the key (alarm name plus state-change
  time) and confirm it is stable across redelivery.
- **Configuration delivery to the Lambda:** packaged file or SSM parameter;
  pick the one that lets users change targets without rebuilding.
- **Existing configurations:** decide whether `kira init` can also read a
  current `deployment.json`. It is only worth it if existing users need it.
- **Packaging:** the project has no installable package today. Milestone 2
  needs a `pyproject.toml` entry point so `kira` is a real command.
- **Runtime access checks:** the generalization keeps `instance_id` and the
  current checks, which keeps this the smallest edit to security-critical code.
  Any change there needs the existing security tests as the safety net.
- **Nothing here has run on real AWS.** The first real check is part of
  milestone 4.
