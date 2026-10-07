"""Lint identity-enabled releases in synthetic same/split-region target layouts."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infra import durable_templates, identity, owned_runtime  # noqa: E402
from infra.spec import load, prefix  # noqa: E402
from scripts.validate_durable import examples  # noqa: E402


def main():
    spec = load(ROOT / "infra/deployment.example.json")
    config = json.loads((ROOT / "infra/identity.example.json").read_text())
    with tempfile.TemporaryDirectory(prefix="kira-identity-") as tmp:
        files = []
        for mode in ("same", "split"):
            current = {**spec, "bedrock_region": spec["bedrock_region"] if mode == "same" else "us-east-1"}
            for target in ("standalone", "agentcore"):
                cfg = {**config, "runtime_target": target}
                # Build legacy fixtures before adding the mandatory identity binding.
                _, data, arts, versions = examples(
                    current,
                    {k: v for k, v in cfg.items() if k not in {"identity", "security"}},
                    include_bindings=True,
                )
                data["identity"] = {
                    "SigningSecretArn": f"arn:aws:secretsmanager:{current['bedrock_region']}:{current['account_id']}:secret:{prefix(current)}/session-signing-123abc",
                    "SigningSecretVersion": "a" * 32,
                }
                from infra.chat import fixture_bindings
                from infra.chat import runtime as chat_runtime

                fixture_bindings(current, data)
                stages = {
                    "durable-foundation": durable_templates.foundation(current, cfg),
                    "chat-runtime": chat_runtime(current, cfg, data, arts["incident_investigate"]),
                    "identity-foundation": identity.foundation(current, data),
                    "identity-secret": identity.signing_secret(current),
                    "durable-runtime": durable_templates.runtime(
                        current, cfg, arts, data["foundation"], owned_bindings=data
                    ),
                    "routing": durable_templates.active_routing(
                        current,
                        versions["InvestigateVersionArn"],
                        "",
                        "",
                        data["foundation"],
                        versions,
                        config=cfg,
                        owned_bindings=data,
                    ),
                }
                if target == "agentcore":
                    stages["agentcore-runtime"] = owned_runtime.agentcore_release(
                        current, cfg, data, arts["incident_ingress"]
                    )
                    stages["agentcore-chat-runtime"] = owned_runtime.agentcore_release(
                        current, cfg, data, arts["incident_ingress"], purpose="chat"
                    )
                    stages["agentcore-chat-endpoint"] = owned_runtime.agentcore_endpoint(
                        current, data["agentcore_chat_candidate"]["RuntimeId"], "1"
                    )
                for stage, value in stages.items():
                    path = Path(tmp) / f"{mode}-{target}-{stage}.json"
                    path.write_text(json.dumps(value))
                    files.append(str(path))
        subprocess.run(
            [str(Path(sys.executable).parent / "cfn-lint"), "--non-zero-exit-code", "warning", "-t", *files],
            check=True,
        )
    print(f"PASS: {len(files)} identity-enabled same/split-region templates")


if __name__ == "__main__":
    main()
