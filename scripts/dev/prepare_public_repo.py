"""Export committed public files into an independent repository; never push."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.dev.check_public_repository import check, forbidden_path  # noqa: E402


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def prepare(root, destination):
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    if not destination.is_relative_to(root / ".local") or destination == root / ".local":
        raise ValueError("Publication copy must be a new directory under ignored .local/")
    if destination.exists():
        raise ValueError("Publication destination exists; refusing to overwrite it")
    if git(root, "status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("Commit reviewed public changes before preparing a publication copy")
    revision = git(root, "rev-parse", "HEAD").decode().strip()
    entries = []
    for item in git(root, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not item:
            continue
        metadata, raw_name = item.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        name = raw_name.decode()
        if kind != "blob" or mode not in {"100644", "100755"} or forbidden_path(name):
            raise ValueError(f"Unsafe or private committed entry: {name}")
        entries.append((mode, blob, name))
    errors = check(root, [name for _, _, name in entries])
    if errors:
        raise ValueError("Public repository checks failed: " + "; ".join(errors))
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".publication-", dir=destination.parent))
    try:
        for mode, blob, name in entries:
            output = temporary / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(git(root, "cat-file", "blob", blob))
            output.chmod(0o755 if mode == "100755" else 0o644)
        git(temporary, "init", "--template=", "-b", "main")
        # Keep the personal source identity, without inheriting remotes or history.
        for key in ("user.name", "user.email"):
            value = git(root, "config", "--get", key).decode().strip()
            git(temporary, "config", key, value)
        git(temporary, "add", "--all")
        git(temporary, "-c", "core.hooksPath=/dev/null", "commit", "-m", "Initial public release")
        if git(temporary, "rev-list", "--count", "HEAD").strip() != b"1":
            raise ValueError("Publication repository must have exactly one initial commit")
        if git(temporary, "remote").strip():
            raise ValueError("Publication repository unexpectedly inherited a remote")
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/publication")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / "scripts/dev/check_secrets.py")], cwd=ROOT, check=True)
    destination = prepare(ROOT, args.output)
    print(f"Prepared independent publication repository: {destination}")
    print("Branch: main; one initial commit; no remote configured; nothing pushed")


if __name__ == "__main__":
    main()
