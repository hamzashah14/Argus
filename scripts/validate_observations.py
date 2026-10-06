"""Validate complete Phase 4 additions in both hosting and region layouts, without AWS."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from infra import observation_templates  # noqa: E402
from infra.spec import load, name  # noqa: E402
from scripts.validate_durable import examples  # noqa: E402


def fixtures(spec, config):
    prior, bindings, artifacts, versions = examples(spec, config, include_bindings=True)
    observation_versions = {
        logical
        + "VersionArn": f"arn:aws:lambda:{spec['monitor_region']}:{spec['account_id']}:function:{name(spec, function.replace('_', '-'), True)}:1"
        for function, logical in observation_templates.FUNCTIONS.items()
    }
    observation_artifacts = {
        function: artifacts["incident_ingress"] for function in observation_templates.FUNCTIONS
    }
    return {
        **prior,
        "observation-foundation": observation_templates.foundation(spec, bindings["foundation"], config),
        "observation-runtime": observation_templates.runtime(
            spec, bindings["foundation"], observation_artifacts, config
        ),
        "observations": observation_templates.active(
            spec, bindings["foundation"], observation_versions, versions
        ),
    }


def main():
    spec = load(ROOT / "infra/observability.example.json")
    config = json.loads((ROOT / "infra/durable.example.json").read_text())
    with tempfile.TemporaryDirectory(prefix="kira-phase4-") as temp:
        files = []
        for mode in ("same", "split"):
            current = {**spec, "bedrock_region": "us-east-1" if mode == "split" else spec["bedrock_region"]}
            for target in ("standalone", "agentcore"):
                for stage, value in fixtures(current, {**config, "runtime_target": target}).items():
                    path = Path(temp) / f"{mode}-{target}-{stage}.json"
                    path.write_text(json.dumps(value))
                    files.append(str(path))
        subprocess.run(
            [str(Path(sys.executable).parent / "cfn-lint"), "--non-zero-exit-code", "warning", "-t", *files],
            check=True,
        )
    print(f"PASS: {len(files)} Phase 4 same/split-region standalone/AgentCore templates")


if __name__ == "__main__":
    main()
