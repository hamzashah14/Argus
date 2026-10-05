"""Build deterministic Lambda ZIPs from hash-verified wheels, shared code and catalog."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kira.metrics import validate_catalog  # noqa: E402 — runnable from outside the repository

FUNCTIONS = ("fetch_logs", "fetch_metrics", "trigger_investigation")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(functions, output, catalog_path, wheelhouse):
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Lambda builds require Python 3.12.")
    catalog = json.dumps(
        validate_catalog(json.loads(catalog_path.read_text())), sort_keys=True, separators=(",", ":")
    ).encode()
    lock = ROOT / "requirements/lambda.lock"
    output.mkdir(parents=True, exist_ok=True)
    # An isolated download destination excludes stale, extra wheels. pip verifies
    # hashes even when reading wheels from a caller-provided offline wheelhouse.
    with tempfile.TemporaryDirectory(prefix="kira-wheels-") as temp:
        command = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--require-hashes",
            "--only-binary=:all:",
            "--platform",
            "manylinux2014_x86_64",
            "--python-version",
            "312",
            "--implementation",
            "cp",
            "--abi",
            "cp312",
            "--dest",
            temp,
            "-r",
            str(lock),
        ]
        if wheelhouse:
            command += ["--no-index", "--find-links", str(wheelhouse.resolve())]
        subprocess.run(command, check=True)
        entries = {}
        wheels = {}
        for wheel in sorted(Path(temp).glob("*.whl")):
            wheels[wheel.name] = digest(wheel.read_bytes())
            with zipfile.ZipFile(wheel) as archive:
                for name in archive.namelist():
                    if name.endswith("/") or ".data/" in name or name.endswith(".pyc"):
                        continue
                    if name.startswith("/") or ".." in Path(name).parts or name in entries:
                        raise ValueError("Invalid or conflicting wheel entry")
                    entries[name] = archive.read(name)
        for path in sorted((ROOT / "kira").glob("*.py")):
            entries[str(path.relative_to(ROOT))] = path.read_bytes()
        entries["config/metric-catalog.json"] = catalog
        entries["requirements/lambda.lock"] = lock.read_bytes()
        manifest = {
            "python": "3.12",
            "architecture": "x86_64",
            "lock_sha256": digest(lock.read_bytes()),
            "wheels": wheels,
            "functions": {},
        }
        for function in functions:
            source = ROOT / "lambda" / function / "lambda_function.py"
            files = {**entries, "lambda_function.py": source.read_bytes()}
            artifact = output / f"{function}.zip"
            with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for name, data in sorted(files.items()):
                    info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            manifest["functions"][function] = {
                "artifact": artifact.name,
                "sha256": digest(artifact.read_bytes()),
                "bytes": artifact.stat().st_size,
                "source_files": {
                    name: digest(data)
                    for name, data in files.items()
                    if name.startswith("kira/")
                    or name in {"lambda_function.py", "config/metric-catalog.json"}
                },
            }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--function", choices=FUNCTIONS, action="append")
    parser.add_argument("--output", type=Path, default=ROOT / ".build/lambda")
    parser.add_argument("--catalog", type=Path, default=ROOT / "config/metric-catalog.json")
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    build(args.function or FUNCTIONS, args.output, args.catalog, args.wheelhouse)


if __name__ == "__main__":
    main()
