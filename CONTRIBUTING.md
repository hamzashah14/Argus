# Contributing

Use Python 3.12 and `requirements/dev.lock` with `pip install --require-hashes`.
Run the checks in [README](README.md#development) before opening a pull request.
CI also builds and imports deployable packages independently and renders complete
synthetic releases for both runtime targets.

Use synthetic fixtures and injected SDK clients in tests. Do not depend on a
developer's AWS account or invoke paid models, notification channels or deployed
resources in default tests. Preserve denial, fencing, budget, redaction and
scope regressions when changing runtime behavior. Exercise meaningful failure
paths as well as successful requests.

Update the relevant customer guide when commands, settings, IAM boundaries or
manual responsibilities change. Deployment plans bind clean source and immutable
artifacts; new source/configuration needs a new reviewed release.

Keep credentials, real inventory, logs, cloud responses and private work records
under ignored private storage. Never paste sensitive payloads into issues, PRs,
screenshots or test fixtures. Check `git diff --cached` and run the public-file and
secret checks before committing. `.gitignore` does not remove previously committed
data; follow [publishing](docs/PUBLISHING.md) when preparing a new public repository.

Explain the concrete behavior change, relevant validation and remaining live
limits in each pull request. Report suspected vulnerabilities privately as
described in [SECURITY.md](SECURITY.md).
