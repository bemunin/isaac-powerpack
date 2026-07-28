# pow

CLI tool (`pow`) for managing Isaac Sim projects with ROS 2 integration.
Main package: `packages/pow-cli`.

## Releasing

When the user asks to release a version, do these steps in order from the repo
root (details in `docs/releasing.md`):

1. **Bump** to the version the user specified:
   `uv run bump.py <version>` (exact, e.g. `0.3.0rc1`) or
   `uv run bump.py --bump <part>` (major/minor/patch/stable/alpha/beta/rc;
   repeatable, e.g. `--bump minor --bump rc`). Updates both `pyproject.toml`
   files and `uv.lock`; commits nothing.
2. **Changelog**: add a `## [<version>] - YYYY-MM-DD` entry at the top of
   `packages/pow-cli/CHANGELOG.md` summarizing changes since the last release
   (from git log). Use the exact PEP 440 string in the heading
   (`[0.3.0rc1]`, not `[0.3.0-rc.1]`) — bump.py warns otherwise.
3. **Commit**: `git commit -m "chore: bump to <version>"`
4. **Tag & push**: `git tag -a v<version> -m "pow-cli <version>"`, then push
   the branch and the tag to origin.

Pushing the tag publishes nothing. The user then creates the GitHub release
from the tag manually in the web UI; publishing the release triggers
`.github/workflows/publish.yml` (TestPyPI automatically, PyPI after the user
approves the `pypi` environment).

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
