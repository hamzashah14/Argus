"""Fail on new secret candidates; narrow synthetic/hash exclusions are explicit."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    # Never scan ignored .env/config/private evidence into public artifacts.
    paths = sorted(
        set(
            subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True
            ).splitlines()
        )
    )
    paths = [name for name in paths if (ROOT / name).is_file()]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "detect_secrets",
            "scan",
            "--no-verify",
            "--exclude-files",
            r"(^requirements/.*\.lock$|^\.secrets\.baseline$)",
            *paths,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    scanned = json.loads(result.stdout)
    baseline_path = ROOT / ".secrets.baseline"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {"results": {}}
    allowed = {
        (name, item["type"], item["hashed_secret"])
        for name, items in baseline["results"].items()
        for item in items
        if item.get("is_secret") is False
    }
    new = []
    for name, items in scanned["results"].items():
        for item in items:
            if (name, item["type"], item["hashed_secret"]) not in allowed:
                new.append({"file": name, "line": item["line_number"], "type": item["type"]})
    # Never print candidate values, even on failure.
    print(json.dumps({"new_candidates": new, "reviewed_baseline_candidates": len(allowed)}, indent=2))
    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
