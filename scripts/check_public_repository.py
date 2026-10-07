"""Check tracked public files, documentation links and private-path boundaries."""

import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOTS = {
    "AGENTS.md",
    "PRODUCTION_READINESS_AUDIT.md",
    "PRODUCTION_IMPLEMENTATION_PLAN.md",
    "IMPLEMENTATION_TRACKER.md",
    "OPEN_SOURCE_PRODUCT_PLAN.md",
    "PRODUCT_ROADMAP_TRACKER.md",
    "config.env",
    ".streamlit/secrets.toml",
    "config/access-policy.json",
    "docs/PROJECT_EVOLUTION_AND_ONBOARDING.md",
}
PRIVATE_PREFIXES = ("docs/implementation/", ".local/", ".build/", ".aws/", ".venv/")


def forbidden_path(name):
    path = PurePosixPath(name)
    return (
        path.is_absolute()
        or ".." in path.parts
        or ".git" in path.parts
        or name in PRIVATE_ROOTS
        or name.startswith(PRIVATE_PREFIXES)
        or (path.name.startswith(".env") and name != ".env.example")
        or path.suffix in {".pem", ".key", ".ticket"}
        or path.name in {".DS_Store", "credentials", ".gitmodules"}
        or "__pycache__" in path.parts
    )


def tracked_paths(root):
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return {name.decode() for name in raw.split(b"\0") if name}


def heading_anchors(text):
    anchors = set()
    counts = {}
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if fenced or not re.match(r"^#{1,6}\s", line):
            continue
        title = re.sub(r"^#+\s+", "", line).strip().lower()
        anchor = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        suffix = counts.get(anchor, 0)
        counts[anchor] = suffix + 1
        anchors.add(anchor if not suffix else f"{anchor}-{suffix}")
    return anchors


def check(root, paths=None):
    root = Path(root).resolve()
    paths = tracked_paths(root) if paths is None else set(paths)
    errors = []
    for name in sorted(paths):
        if forbidden_path(name):
            errors.append(f"Private or unsafe tracked path: {name}")
            continue
        path = root / name
        if path.is_symlink():
            errors.append(f"Tracked symlink is not supported for publication: {name}")
            continue
        if not path.is_file():
            errors.append(f"Tracked file is missing: {name}")
            continue
        if path.suffix != ".md" or forbidden_path(name):
            continue
        text = path.read_text()
        if re.search(r"docs/implementation/|implementation/phase-|\bPhase[s]?\s+\d|/Users/", text):
            errors.append(f"Internal context or obsolete documentation reference: {name}")
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            target = target.strip("<>")
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            resolved = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not resolved.is_relative_to(root):
                errors.append(f"Documentation link leaves repository: {name} -> {target}")
                continue
            rel = resolved.relative_to(root).as_posix()
            if rel not in paths:
                errors.append(f"Unpublished documentation target: {name} -> {target}")
            elif url.fragment and resolved.suffix == ".md":
                if unquote(url.fragment) not in heading_anchors(resolved.read_text()):
                    errors.append(f"Missing documentation anchor: {name} -> {target}")
    return errors


def main():
    errors = check(ROOT)
    for error in errors:
        print(error)
    print(f"{'FAIL' if errors else 'PASS'}: public file boundaries and documentation links")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
