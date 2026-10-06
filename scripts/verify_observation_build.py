"""Rebuild three inventory-bound observers twice and import each with only bundled dependencies."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infra.observations import build_release  # noqa: E402
from infra.spec import load  # noqa: E402


def main():
    outputs = [ROOT / ".build" / f"observation-{suffix}" for suffix in ("a", "b")]
    for output in outputs:
        build_release(load(ROOT / "infra/observability.example.json"), output, ROOT / ".build/wheels")
    a, b = [json.loads((path / "manifest.json").read_text()) for path in outputs]
    if a != b:
        raise AssertionError("Observation packages differ between independent builds")
    imports = []
    for function, artifact in a["functions"].items():
        with tempfile.TemporaryDirectory(prefix="kira-observation-") as temp:
            with zipfile.ZipFile(outputs[0] / artifact["artifact"]) as archive:
                archive.extractall(temp)
            result = subprocess.run(
                [sys.executable, "-S", "-c", "import boto3,lambda_function; print(boto3.__version__)"],
                cwd=temp,
                env={"PATH": os.defpath, "AWS_EC2_METADATA_DISABLED": "true"},
                text=True,
                capture_output=True,
                check=True,
            )
            imports.append({"function": function, "sdk_version": result.stdout.strip(), "result": "PASS"})
    evidence = {"deterministic_builds": "PASS", "isolated_imports": imports, "manifest": a}
    (ROOT / ".build/observation-build-validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("PASS: three identical observation ZIP pairs and three isolated imports")


if __name__ == "__main__":
    main()
