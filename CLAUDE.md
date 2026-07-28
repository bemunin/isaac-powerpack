# pow

CLI tool (`pow`) for managing Isaac Sim projects with ROS 2 integration.
Main package: `packages/pow-cli`.

## Ask before committing or pushing (ALWAYS)

Never run `git commit`, `git push`, `git tag`, `gh release create`, or anything
else that writes to the repository or the remote without asking first and getting
an explicit yes — even when the task obviously ends in a commit, and even when a
procedure in this file (such as [Releasing](#releasing)) lists those steps.

Do the work, leave the changes in the working tree, then say what you changed and
what command you would run. This applies to amending, force-pushing, and deleting
or moving tags as well. Editing files, running tests, and other read-only or
local-only work needs no confirmation.

## Commit attribution

`bemunin` is the sole author of this repository. Never add a
`Co-Authored-By: Claude ...` trailer, a "Generated with Claude Code" footer, or
any other Claude/Anthropic attribution to a commit message or PR body — GitHub
counts co-author trailers toward the repo's contributor list.

## Releasing

Two spellings of the same version are in play, and mixing them up breaks the
publish workflow:

- **SemVer** (`0.3.0-rc.1`) — git tags, GitHub release title, CHANGELOG heading.
- **PEP 440 canonical** (`0.3.0rc1`) — both `pyproject.toml` files, the built
  artifact, PyPI. `uv` and PyPI normalize to this form; it is not a choice.

A stable release is identical in both (`0.3.0`). Below, `<semver>` means
`0.3.0-rc.1` and `<pep440>` means `0.3.0rc1`.

When the user asks to release a version, do these steps in order from the repo
root (details in `docs/releasing.md`). Steps 3–5 write to the repo and the
remote, so confirm each one first — see
[Ask before committing or pushing](#ask-before-committing-or-pushing-always):

1. **Bump** to the version the user specified:
   `uv run bump.py <pep440>` (exact, e.g. `0.3.0rc1`) or
   `uv run bump.py --bump <part>` (major/minor/patch/stable/alpha/beta/rc;
   repeatable, e.g. `--bump minor --bump rc`). Updates both `pyproject.toml`
   files and `uv.lock`; commits nothing.
2. **Changelog**: add a `## [<semver>] - YYYY-MM-DD` entry at the top of
   `packages/pow-cli/CHANGELOG.md` summarizing changes since the last release
   (from git log), e.g. `## [0.3.0-rc.1] - 2026-07-28`.
3. **Commit**: `git commit -m "chore: bump to <semver>"`
4. **Tag & push**: `git tag -a v<semver> -m "pow-cli <semver>"`, then push the
   branch and the tag to origin. This publishes nothing on its own.
5. **Create the GitHub release** — this is what triggers publishing:
   ```bash
   gh release create v<semver> \
     --title "pow@<semver>" \
     --prerelease \
     --notes "Please refer to [CHANGELOG.md](https://github.com/isaac-powerpack/pow/blob/v<semver>/packages/pow-cli/CHANGELOG.md) for details."
   ```
   - Pass `--prerelease` only when the version has an `a`/`b`/`rc` part; omit it
     for a stable release.
   - The `blob/v<semver>` path must be the tag just pushed, so the link resolves
     to the CHANGELOG as of that release.
   - Requires `gh` installed and authenticated as `bemunin`; otherwise create the
     release from the tag in the GitHub web UI with the same title, pre-release
     flag, and notes.

Publishing the release triggers `.github/workflows/publish.yml`: TestPyPI
uploads automatically, then PyPI waits for the user to approve the `pypi`
environment.

## Running tests

From `packages/pow-cli` (host ROS env leaks into pytest, so strip it):

```bash
env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -p pytest_mock -q
```

## Clean up test/CLI artifacts (ALWAYS)

Running the test suite or `pow` commands with cwd inside `packages/pow-cli`
can accidentally create initializer artifacts there:

- `packages/pow-cli/_isaacsim` — symlink to `~/.pow/isaacsim/<version>` (remove the
  symlink only, never its target)
- `packages/pow-cli/.vscode/` — Isaac Sim template configs copied by the initializer

Both are gitignored, so `git status` will NOT show them. After implementing and
testing code, always check for and remove them:

```bash
rm -f packages/pow-cli/_isaacsim && rm -rf packages/pow-cli/.vscode
```
