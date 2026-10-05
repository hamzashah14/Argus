"""Lint every generated CloudFormation stage using a synthetic, non-deployable binding."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from infra import templates  # noqa: E402
from infra.spec import load, name  # noqa: E402


def examples(spec):
    artifacts = {}
    for function in ("fetch_logs", "fetch_metrics", "trigger_investigation"):
        purpose = "monitor" if function == "trigger_investigation" else "tools"
        artifacts[function] = {
            "bucket": templates.bucket_name(spec, purpose),
            "key": f"releases/{spec['release_id']}/" + "a" * 64 + ".zip",
            "version_id": "synthetic-object-version",
            "sha256": "a" * 64,
        }
    secret = {
        "arn": f"arn:aws:secretsmanager:{spec['bedrock_region']}:{spec['account_id']}:secret:{name(spec, '')[:-1]}/log-cursor-AbCdEf",
        "version_id": "a" * 32,
    }
    worker = f"arn:aws:lambda:{spec['monitor_region']}:{spec['account_id']}:function:{name(spec, 'trigger-investigation', True)}:1"
    return {
        "foundation-tools": templates.foundation(spec, "tools"),
        "foundation-monitor": templates.foundation(spec, "monitor"),
        "tools": templates.tools_release(spec, artifacts, secret),
        "alias": templates.candidate_alias(spec, "ABCDEFGHIJ"),
        "worker": templates.worker_release(
            spec, artifacts["trigger_investigation"], "ABCDEFGHIJ", "KLMNOPQRST"
        ),
        "routing": templates.routing(spec, worker, "ABCDEFGHIJ", "KLMNOPQRST"),
    }


def main():
    spec = load(ROOT / "infra/deployment.example.json")
    with tempfile.TemporaryDirectory(prefix="kira-cfn-") as temp:
        files = []
        for region_mode in ("same", "split"):
            if region_mode == "split":
                spec = {**spec, "bedrock_region": "us-east-1"}
            for stage, template in examples(spec).items():
                path = Path(temp) / f"{region_mode}-{stage}.json"
                path.write_text(json.dumps(template))
                files.append(str(path))
        subprocess.run(
            [str(Path(sys.executable).parent / "cfn-lint"), "--non-zero-exit-code", "warning", "-t", *files],
            check=True,
        )
    print("PASS: 12 generated CloudFormation templates (same and split region)")


if __name__ == "__main__":
    main()
