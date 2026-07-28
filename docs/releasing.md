# Releasing pow-cli

Publishing is automated by [`.github/workflows/publish.yml`](../.github/workflows/publish.yml).
**Publishing a GitHub release** (done manually in the web UI, from a version tag)
builds the package once, publishes it to TestPyPI automatically, then publishes the
same artifacts to PyPI after a maintainer approves the `pypi` environment. Pushing a
tag by itself publishes nothing — the workflow only reacts to the release.

## Who can release

Only `bemunin` can publish. The build job's `if:` condition requires the repository
to be `isaac-powerpack/pow` (so forks never run it) and both `github.actor` (who
published the release) and `github.triggering_actor` (who re-ran the workflow) to be
that login. An unauthorized trigger skips the whole run silently — nothing reaches
either index. The PyPI job additionally waits on the `pypi` environment's required
reviewers.

To hand the release role to someone else, change the logins in that `if:` condition
and add them as a reviewer on the `pypi` environment. Note this guard lives in the
workflow file, so anyone with write access to the repo could edit it — see the
ruleset suggestion under [One-time setup](#one-time-setup) to close that off.

## Version format

Every release has **two spellings of the same version**, and they are not
interchangeable:

| Release      | `pyproject.toml` / PyPI (PEP 440) | Tag, release title, CHANGELOG (SemVer) |
| ------------ | --------------------------------- | -------------------------------------- |
| Stable       | `0.2.0`                           | `v0.2.0`                               |
| Release cand.| `0.2.0rc1`                        | `v0.2.0-rc.1`                          |
| Beta         | `0.2.0b1`                         | `v0.2.0-b.1`                           |
| Alpha        | `0.2.0a1`                         | `v0.2.0-a.1`                           |

Tags follow **[SemVer 2.0.0](https://semver.org/)** — pre-releases use the `-`
suffix. `pyproject.toml` cannot: `uv version` normalizes `0.2.0-rc.1` to `0.2.0rc1`
on write, and PyPI stores and serves only that canonical
[PEP 440](https://peps.python.org/pep-0440/) form, so the published artifact is
always `pow_cli-0.2.0rc1-…` no matter how the tag is spelled.

The publish workflow bridges the two: it parses the release tag and normalizes it
to PEP 440 before comparing against `packages/pow-cli/pyproject.toml`. The older
canonical tag spelling (`v0.2.0rc1`) is still accepted so tags already in this
repo keep working, but new releases should use the SemVer form.

## Steps

1. **Bump the version.**
   ```bash
   uv run bump.py --bump minor --bump rc   # 0.2.0rc1 -> 0.3.0rc1
   uv run bump.py --bump stable            # 0.2.0rc1 -> 0.2.0
   uv run bump.py 0.3.0                    # exact version
   ```
   Updates `packages/pow-cli/pyproject.toml`, the root `pyproject.toml`, and
   `uv.lock`. Nothing else. Add `--dry-run` to preview.

2. **Write the CHANGELOG entry and commit.** Use the SemVer spelling in the
   heading, e.g. `## [0.3.0-rc.1] - 2026-07-28`, then:
   ```bash
   git commit -am "chore: bump to 0.3.0-rc.1"
   ```

3. **Tag and push.**
   ```bash
   git tag -a v0.3.0-rc.1 -m "pow-cli 0.3.0-rc.1"
   git push origin main && git push origin v0.3.0-rc.1
   ```
   Nothing is published yet.

4. **Create the GitHub release** — this is what triggers the workflow:
   ```bash
   gh release create v0.3.0-rc.1 \
     --title "pow@v0.3.0-rc.1" \
     --prerelease \
     --notes "Please refer to [CHANGELOG.md](https://github.com/isaac-powerpack/pow/blob/v0.3.0-rc.1/packages/pow-cli/CHANGELOG.md) for details."
   ```
   The title keeps the `v` (`pow@v0.3.0-rc.1`), matching every existing release.
   Drop `--prerelease` for a stable release. The `blob/<tag>` path must be the tag
   being released so the link resolves to the CHANGELOG as of that release. Without
   `gh`, do the same from the web UI (Releases → *Draft a new release* → choose the
   tag → *Publish release*); a draft triggers nothing.

5. Watch the run in **Actions**. Once the `testpypi` job succeeds, optionally verify
   the upload — note the **PEP 440** version here, since that is what PyPI serves
   (`--no-deps` because `isaacsim` is not on TestPyPI):
   ```bash
   uv pip install --no-deps -i https://test.pypi.org/simple/ pow-cli==0.3.0rc1
   ```

6. Approve the waiting `pypi` job to release to PyPI.

Cancelling the run at step 6 leaves only a TestPyPI upload, which is throwaway.

`bump.py` carries [PEP 723](https://peps.python.org/pep-0723/) inline metadata and no
dependencies, so uv supplies its own Python 3.11 — it never touches the project
environment and does not care what `python3` is on your `PATH`. It is executable
(`#!/usr/bin/env -S uv run --script`), so `./bump.py …` works identically.

### What bump.py checks

It rejects a version the publish workflow would not accept (`.post`/`.dev`),
resolves the target with `uv version --dry-run` before writing anything, verifies both
`pyproject.toml` files really hold the new version afterwards, and warns when the
CHANGELOG has no matching heading. It deliberately does *not* require a clean tree —
bumping on top of an in-progress CHANGELOG edit is the normal case.

### Doing it by hand

The script is a convenience, not a requirement. The equivalent manual sequence is
`uv version --package pow-cli --bump <part>`, the same version into the root
`pyproject.toml`, `uv lock`, then the commit/tag/release steps above.

### Undoing a release

After `bump.py`, before committing:
`git checkout -- pyproject.toml packages/pow-cli/pyproject.toml uv.lock`.

After tagging but before pushing: `git tag -d vX.Y.Z`. A pushed tag uploads nothing
by itself — delete it with `git push origin :refs/tags/vX.Y.Z` before any release is
made from it. Once the GitHub release is published, TestPyPI has the files; delete
the release and tag, and cancel the run before approving PyPI. A version that
reached PyPI cannot be reused — bump to a new one.

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
