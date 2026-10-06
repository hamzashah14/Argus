"""Prove deterministic ARM64 AgentCore ZIP builds and bundled import compatibility."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_lambdas import build  # noqa: E402


def main():
    outputs = [ROOT / ".build" / f"agentcore-{suffix}" for suffix in ("a", "b")]
    manifests = [
        build(
            ("incident_investigate",),
            output,
            ROOT / "config/metric-catalog.json",
            ROOT / ".build/wheels",
            architecture="arm64",
        )
        for output in outputs
    ]
    if manifests[0] != manifests[1]:
        raise AssertionError("AgentCore host builds differ")
    # Our locked SDK dependencies are pure Python. Reject architecture-specific
    # binaries rather than mistake an import on macOS for proof of Linux ARM64.
    package = outputs[0] / "incident_investigate.zip"
    with tempfile.TemporaryDirectory(prefix="kira-agentcore-") as temp:
        with zipfile.ZipFile(package) as archive:
            if any(p.endswith((".so", ".dll", ".dylib", ".pyd")) for p in archive.namelist()):
                raise AssertionError(
                    "Host verification requires a native Linux ARM64 runner for binary dependencies"
                )
            archive.extractall(temp)
        subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                "import boto3,kira_agentcore,kira.execution,kira.runtime; print(boto3.__version__)",
            ],
            cwd=temp,
            env={"PATH": os.defpath, "AWS_EC2_METADATA_DISABLED": "true"},
            check=True,
        )
    evidence = {
        "deterministic_builds": "PASS",
        "pure_python_bundled_imports": "PASS",
        "architecture": "arm64",
        "live_agentcore_boot": "PENDING",
        "manifest": manifests[0],
    }
    (ROOT / ".build/agentcore-build-validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("PASS: identical ARM64 host ZIP pair; pure Python bundled imports; live AgentCore boot pending")


if __name__ == "__main__":
    main()
