"""Compare two clean builds and import each package without installed app deps."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    outputs = [ROOT / ".build" / f"lambda-{suffix}" for suffix in ("a", "b")]
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_lambdas.py"),
                "--output",
                str(output),
                "--wheelhouse",
                str(ROOT / ".build/wheels"),
            ],
            check=True,
        )
    a, b = [json.loads((path / "manifest.json").read_text()) for path in outputs]
    if a != b:
        raise AssertionError("Independent builds do not match")
    imports = []
    for name, artifact in a["functions"].items():
        with tempfile.TemporaryDirectory(prefix="kira-artifact-") as temp:
            with zipfile.ZipFile(outputs[0] / artifact["artifact"]) as archive:
                archive.extractall(temp)
            # -S removes site-packages: the SDK and shared library must come from
            # the ZIP. No client is constructed or credentials accessed.
            run = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-c",
                    "import boto3,lambda_function; from kira.metrics import catalog; assert isinstance(catalog(),list); print(boto3.__version__)",
                ],
                cwd=temp,
                env={"PATH": os.defpath, "AWS_EC2_METADATA_DISABLED": "true"},
                text=True,
                capture_output=True,
                check=True,
            )
            imports.append({"function": name, "sdk_version": run.stdout.strip(), "result": "PASS"})
    evidence = {"deterministic_builds": "PASS", "isolated_imports": imports, "manifest": a}
    (ROOT / ".build/build-validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("PASS: identical independent ZIPs and isolated imports for both read-only tools")


if __name__ == "__main__":
    main()
