"""Re-run the original checks and capture syntax/dependency evidence offline.

This is a baseline harness, not the Phase 1 discovered test suite or CI pipeline.
Unexpected socket access fails, even if real credentials exist on the host.
"""
import argparse
import ast
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import runpy
import socket
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/implementation/evidence/phase-0/baseline-manifest.json").read_text())
    sources = [row for row in manifest["files"] if Path(row["path"]).suffix in {".py", ".sh", ".json"}]
    result = {"python": platform.python_version(), "network": "denied in test process", "checks": [],
              "command": ".venv/bin/python scripts/phase0/verify.py --output docs/implementation/evidence/phase-0/baseline-checks.json"}
    result["dependencies"] = {
        name: importlib.metadata.version(name) for name in
        ("boto3", "botocore", "jmespath", "python-dateutil", "s3transfer", "six", "urllib3")
    }
    for row in sources:
        path = ROOT / row["path"]
        content = path.read_bytes()
        if path.suffix == ".py":
            ast.parse(content, filename=str(path))
        elif path.suffix == ".json":
            json.loads(content)
        else:
            subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True, text=True)
        result["checks"].append({"path": row["path"], "syntax": "PASS", "sha256": hashlib.sha256(content).hexdigest()})
    total = 0
    result["self_checks"] = []
    # Clear environmental overrides so the baseline stays deterministic.
    with patch.dict(os.environ, {"AWS_EC2_METADATA_DISABLED": "true"}, clear=True), \
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in baseline checks")), \
            patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden in baseline checks")):
        for name, expected in (("fetch_logs", 9), ("fetch_metrics", 6), ("trigger_investigation", 6)):
            path = ROOT / "lambda" / name / "lambda_function.py"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                namespace = runpy.run_path(str(path), run_name="__main__")
            names = sorted(key for key in namespace if key.startswith("test_") and callable(namespace[key]))
            if len(names) != expected:
                raise AssertionError(f"{name}: expected {expected} original checks, found {len(names)}")
            total += len(names)
            result["self_checks"].append({"module": name, "result": "PASS", "count": len(names), "tests": names})
    result.update(result="PASS", original_checks=total, cloud_calls=0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: {total} original self-checks; {len(sources)} syntax checks; no cloud calls")


if __name__ == "__main__":
    main()
