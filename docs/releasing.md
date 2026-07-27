# Releasing pow-cli

Releases are automated by [`.github/workflows/publish.yml`](../.github/workflows/publish.yml).
Pushing a version tag builds the package once, publishes it to TestPyPI automatically,
then publishes the same artifacts to PyPI after a maintainer approves the `pypi`
environment.

## Who can release

Only `bemunin` can publish. The workflow's first step compares both
`github.actor` (who pushed the tag) and `github.triggering_actor` (who re-ran the
workflow) against that login and fails before checkout otherwise, so a tag pushed by
anyone else reaches neither index. The PyPI job additionally waits on the `pypi`
environment's required reviewers.

To hand the release role to someone else, change `RELEASER` in
`.github/workflows/publish.yml` and add them as a reviewer on the `pypi` environment.
Note this guard lives in the workflow file, so anyone with write access to the repo
could edit it — see the ruleset suggestion under [One-time setup](#one-time-setup) to
close that off.

## Tag format

Tags are **PEP 440** and must match `version` in `packages/pow-cli/pyproject.toml`
exactly, minus the leading `v`:

| Release      | Version in `pyproject.toml` | Tag         |
| ------------ | --------------------------- | ----------- |
| Stable       | `0.2.0`                     | `v0.2.0`    |
| Release cand.| `0.2.0rc1`                  | `v0.2.0rc1` |
| Beta         | `0.2.0b1`                   | `v0.2.0b1`  |
| Alpha        | `0.2.0a1`                   | `v0.2.0a1`  |

SemVer-style tags such as `v0.2.0-rc.1` are rejected by the workflow. Some older tags
in this repo use that style; they are history and are not re-tagged.

## Steps

Two scripts at the repo root do the work. Neither one commits — that stays yours.

1. **Bump the version.**
   ```bash
   uv run bump.py --bump minor --bump rc   # 0.2.0rc1 -> 0.3.0rc1
   uv run bump.py --bump stable            # 0.2.0rc1 -> 0.2.0
   uv run bump.py 0.3.0                    # exact version
   ```
   Updates `packages/pow-cli/pyproject.toml`, the root `pyproject.toml`, and
   `uv.lock`. Nothing else. Add `--dry-run` to preview.

2. **Write the CHANGELOG entry and commit, by hand.** Use the same PEP 440 string as
   the tag, e.g. `## [0.3.0rc1] - 2026-07-27`, then:
   ```bash
   git commit -am "chore: bump version to v0.3.0rc1"
   ```

3. **Build, tag, and push.**
   ```bash
   uv run release.py
   ```
   Reads the version from `packages/pow-cli/pyproject.toml`, builds into `dist/`,
   creates the annotated tag, and pushes the branch and the tag. `--dry-run` to
   preview, `--no-push` to stop with the tag local.

4. Watch the run in **Actions**. Once TestPyPI succeeds, optionally verify the upload
   (`--no-deps` because `isaacsim` is not on TestPyPI):
   ```bash
   uv pip install --no-deps -i https://test.pypi.org/simple/ pow-cli==0.3.0rc1
   ```
5. Approve the waiting `publish-pypi` job to release to PyPI.

Cancelling the run at step 5 leaves only a TestPyPI upload, which is throwaway.

Both scripts carry [PEP 723](https://peps.python.org/pep-0723/) inline metadata and no
dependencies, so uv supplies its own Python 3.11 — they never touch the project
environment and do not care what `python3` is on your `PATH`. Both are executable
(`#!/usr/bin/env -S uv run --script`), so `./bump.py …` and `./release.py …` work
identically.

### What the scripts check

`bump.py` rejects a version the publish workflow would not accept (`.post`/`.dev`),
resolves the target with `uv version --dry-run` before writing anything, verifies both
`pyproject.toml` files really hold the new version afterwards, and warns when the
CHANGELOG has no matching heading. It deliberately does *not* require a clean tree —
bumping on top of an in-progress CHANGELOG edit is the normal case.

`release.py` refuses to run on a dirty tree (that is what proves the bump is
committed), re-checks the version is canonical PEP 440, refuses a tag that already
exists locally or on `origin`, prompts if you are not on `main`, and warns if the root
`pyproject.toml` or the CHANGELOG disagrees. It never edits a `pyproject.toml`.

### Doing it by hand

The scripts are a convenience, not a requirement — the workflow only reacts to the tag.
The equivalent manual sequence is `uv version --package pow-cli --bump <part>`, the
same version into the root `pyproject.toml`, `uv lock`, commit, then
`git tag vX.Y.Z && git push origin vX.Y.Z`.

### Undoing a release

After `bump.py`, before committing:
`git checkout -- pyproject.toml packages/pow-cli/pyproject.toml uv.lock`.

After `release.py` tagged but before the push: `git tag -d vX.Y.Z`. Once pushed, the
TestPyPI upload has already happened; delete the remote tag
(`git push origin :refs/tags/vX.Y.Z`) and cancel the run before approving PyPI. A
version that reached PyPI cannot be reused — bump to a new one.

## One-time setup

Already configured, but recorded here in case the project or repo moves:

- **PyPI** → project `pow-cli` → Settings → Publishing: trusted publisher for owner
  `isaac-powerpack`, repo `pow`, workflow `publish.yml`, environment `pypi`.
- **TestPyPI** → same values, environment `testpypi` (as a *pending* publisher if the
  project does not exist there yet).
- **GitHub** → Settings → Environments: `testpypi` with no protection, `pypi` with
  **Required reviewers** set to `bemunin` only. Leave *Prevent self-review* **off** —
  with it on, the sole reviewer cannot approve their own release and the job blocks
  forever.
- **GitHub** → Settings → Rules → Rulesets (optional, recommended): a tag ruleset
  targeting `v*` that restricts creation to `bemunin`. This is server-side enforced, so
  it blocks unauthorized releases even if someone edits the workflow's actor guard.

No API tokens are stored — both indexes authenticate via Trusted Publishing (OIDC),
which is why the environment names above must match the workflow exactly.
