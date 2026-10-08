import subprocess

import pytest

from scripts.dev.check_public_repository import check, forbidden_path
from scripts.dev.prepare_public_repo import prepare


def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "--template=", "-b", "main"], cwd=root, check=True, capture_output=True)
    for key, value in (("user.name", "Synthetic Author"), ("user.email", "author@example.invalid")):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
    (root / ".gitignore").write_text(".local/\n.env\n")
    (root / "README.md").write_text("# Example\n")
    commit(root)
    return root


def commit(root):
    subprocess.run(["git", "add", "--all"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Synthetic checkpoint"],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.production",
        ".aws/credentials",
        "docs/implementation/STATE.md",
        "AGENTS.md",
        "../outside",
        "/absolute",
        "private.key",
        "canary.ticket",
        ".local/a.json",
        ".git/config",
    ],
)
def test_private_and_unsafe_paths_are_rejected(path):
    assert forbidden_path(path)


def test_public_example_and_license_paths_are_allowed():
    for path in (".env.example", "examples/deployment.example.json", "docs/DEPLOY.md", "LICENSE"):
        assert not forbidden_path(path)


def test_export_has_no_private_history_or_untracked_files(tmp_path):
    root = repository(tmp_path)
    (root / "private-history.txt").write_text("synthetic private work record")
    commit(root)
    (root / "private-history.txt").unlink()
    commit(root)
    (root / ".env").write_text("synthetic private setting")
    (root / "untracked.txt").write_text("untracked asset")
    output = prepare(root, root / ".local/publication")
    assert check(output) == []
    assert subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=output).strip() == b"1"
    assert not subprocess.check_output(["git", "remote"], cwd=output).strip()
    assert not (output / ".env").exists()
    assert not (output / "private-history.txt").exists()
    assert not (output / "untracked.txt").exists()
    assert (root / ".env").exists()
    assert subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=root).strip() == b"3"


def test_dirty_source_and_existing_destination_are_refused(tmp_path):
    root = repository(tmp_path)
    output = root / ".local/publication"
    (root / "README.md").write_text("changed")
    with pytest.raises(ValueError, match="Commit reviewed"):
        prepare(root, output)
    commit(root)
    prepare(root, output)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        prepare(root, output)


def test_symlink_and_tracked_private_data_are_refused(tmp_path):
    root = repository(tmp_path)
    (root / "link").symlink_to("README.md")
    commit(root)
    with pytest.raises(ValueError, match="Unsafe or private"):
        prepare(root, root / ".local/publication")
    (root / "link").unlink()
    (root / "AGENTS.md").write_text("synthetic local notes")
    commit(root)
    with pytest.raises(ValueError, match="Unsafe or private"):
        prepare(root, root / ".local/publication")


def test_doc_links_cannot_point_to_unpublished_files_or_missing_anchors(tmp_path):
    root = repository(tmp_path)
    (root / "README.md").write_text("# Example\n[private](.env)\n[missing](README.md#absent)\n")
    commit(root)
    errors = check(root)
    assert any("Unpublished" in error for error in errors)
    assert any("Missing documentation anchor" in error for error in errors)


def test_destination_cannot_escape_private_workspace(tmp_path):
    root = repository(tmp_path)
    with pytest.raises(ValueError, match="under ignored"):
        prepare(root, tmp_path / "outside")
    (root / ".local").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="under ignored"):
        prepare(root, root / ".local/publication")
