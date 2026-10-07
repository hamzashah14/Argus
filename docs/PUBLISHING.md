# Publishing a clean repository

Review the public README, guides, MIT license, dependency licenses and configured
CI before publishing. Run the public-file and secret checks, inspect staged files,
and commit reviewed public changes. Private settings and local work records belong
outside the tracked tree. `.gitignore` only prevents future additions: removing a
tracked file does not remove it from earlier commits.

If your working repository has private development history, prepare a fresh
snapshot rather than pushing that history to a new public remote:

```bash
.venv/bin/python scripts/prepare_public_repo.py --output .local/publication
```

The script requires clean committed source, validates public file boundaries and
documentation links, scans secret candidates and copies only the pinned commit's
regular files. It creates an independent `main` branch with one initial commit,
no inherited history and no remote. Ignored files and untracked assets are not
copied. Existing destinations are never overwritten. The original repository,
local private files and development history remain intact.

Review the new snapshot and run its tests/checks before connecting an empty GitHub
repository. Use the intended personal GitHub account and its SSH identity. Replace
the example owner/repository with your own values:

```bash
cd .local/publication
git log --oneline
git status --short
git remote add origin git@github.com:YOUR_ACCOUNT/YOUR_REPOSITORY.git
ssh -T git@github.com
# Confirm the SSH greeting identifies the intended account before publishing.
git push -u origin main
```

The SSH test normally returns a nonzero exit code even after successful GitHub
authentication; inspect the account named in its greeting. If it names a different
account, select the correct SSH identity before pushing. The export script itself
does not authenticate, contact GitHub, alter account settings or push.

Do not force-push over an existing repository. If the remote has initial files or
history, review them separately before combining anything. Configure branch
protection, required CI and GitHub private vulnerability reporting for the new repo.
Keep publication claims consistent with pending live production acceptance.
