# pow

CLI tool (`pow`) for managing Isaac Sim projects with ROS 2 integration.
Main package: `packages/pow-cli`.

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
