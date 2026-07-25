# CLI Reference

## `pow init`

Initialize an Isaac Sim project. All projects are isolated from each other. Only file and isaacsim app in global `~/.pow` are shared between projects.

<img src="./public/pow_architecture_outline.jpeg" alt="pow_architecture" width="600" />

This interactive command walks through a 10-step setup:

1. Validates the project directory (requires `pyproject.toml`)
2. Checks for existing `pow.toml` configuration
3. Creates the `.pow` global folder if it's not exists
4. Downloads and installs your specified Isaac Sim version in `.pow/isaacsim/<version>` folder
5. Applies post-install optimizations
6. Sets up ROS integration (optional — builds Docker images). The workspace path prompt supports shell-style <kbd>Tab</kbd> completion: unique directories complete inline, ambiguous prefixes list candidates, and `~` is preserved
7. Creates project structure (`exts/`, `.modules/`, `usda/`)
8. Symlinks the managed Isaac Sim installation into the project for intellisense/code completion
9. Configures VS Code settings
10. Generates `pow.toml` configuration

```bash
pow init
```

---

## `pow run`

Run Isaac Sim with the configured profile and extensions from `pow.toml`. See more detail for `pow.toml` configuration in [Configuration Guide](docs/configuration.md).

```bash
# Run with default profile
pow run

# Run with a named profile
pow run -p perf

# Open a specific USD file
pow run -o /path/to/scene.usd

# Pass extra arguments directly to Isaac Sim
pow run -- --/renderer/enabled=gpu
```

| Option              | Description                                        |
| :------------------ | :------------------------------------------------- |
| `-p`, `--profile`   | Profile name from `pow.toml` (default: `default`)  |
| `-o`, `--open`      | Path to a USD file to open on launch               |

> [!WARNING]
> `-o` or `--open` is still in experiment. We have found bug that cause **missing assets** issue when opening scenes using this flag. Suggestion to avoid this problem is by opening the scene via GUI or load scene with `isaacsim api` in your custom extension.

---

## `pow sim`

Run Isaac Sim from **any** directory. Unlike `pow run`, this command needs no project: it does not require a `pyproject.toml` and never reads `pow.toml`, so there is no profile, no `ext_folders`, and no `exts`. It simply launches `.pow/isaacsim/<version>/isaac-sim.sh` and forwards every unrecognized argument straight to it.

Use it to open Isaac Sim outside a project — inspecting a stray USD file, or sanity-checking the installation.

```bash
# Launch the default version (5.1.0) with the jazzy ROS 2 bridge
pow sim

# Launch without the ROS 2 bridge environment
pow sim --no-ros

# Use the humble bridge instead
pow sim --ros humble

# Launch a different installed version
pow sim -v 5.0.0

# Pass raw arguments directly to Isaac Sim
pow sim -- --no-window --/renderer/enabled=gpu
```

| Option              | Description                                                  |
| :------------------ | :----------------------------------------------------------- |
| `-v`, `--version`   | Isaac Sim version to run (default: `5.1.0`)                  |
| `--ros`             | ROS 2 bridge distro: `jazzy` (default) or `humble`           |
| `--no-ros`          | Launch without the ROS 2 bridge environment; wins over `--ros` |

> [!NOTE]
> Because the ROS 2 bridge is enabled by default, `pow sim` clears the host ROS environment and points `LD_LIBRARY_PATH` at Isaac Sim's bundled bridge libs — the same environment `pow run` builds when `enable_ros = true`. Pass `--no-ros` to inherit your shell environment untouched.
>
> `-v` on this subcommand selects the Isaac Sim version; `pow -v` (on the root command) still prints the pow CLI version.

---

## `pow python`

Run Isaac Sim's bundled Python interpreter (`.pow/isaacsim/<version>/python.sh`)for running standalone isaac sim application.

```bash
# Run a standalone script
pow python my_script.py

# Run inline Python
pow python -c "import omni; print(omni.__version__)"

# Use a specific profile
pow python -p perf my_script.py
```

| Option              | Description                                        |
| :------------------ | :------------------------------------------------- |
| `-p`, `--profile`   | Profile name from `pow.toml` (default: `default`)  |

---

## `pow ros`

Launch the ROS Docker container for ROS development. Requires ROS integration to be enabled during `pow init`. By default this runs the bundled `pow_simros_jazzy` image (ROS 2 Jazzy is the only supported distribution); when `ros_dockerfile` / `ros_docker_image` are set in `pow.toml`, it runs your custom image instead. The container is named after the image (characters like `/` and `:` replaced with `_`). See more about the ROS 2 enable flag and custom images in the [Configuration Guide](docs/configuration.md).

```bash
# Start an interactive ROS bash session
pow ros

# Show detailed container launch feedback
pow ros -v

# Pass a custom command to the container
pow ros -- ros2 topic list

# Same as bare `pow ros`; use when a forwarded arg collides with a subcommand name
pow ros launch <args>
```

| Option              | Description                              |
| :------------------ | :--------------------------------------- |
| `-v`, `--verbose`   | Show detailed feedback during launch     |

### `pow ros build`

Build the custom ROS image from the Dockerfile referenced by `ros_dockerfile` in `pow.toml`, tagging it with `ros_docker_image`. If the base `pow_simros_jazzy` image is missing, it is built first (this requires the ROS workspace set up by `pow init`).

```bash
pow ros build

# Bypass the Docker layer cache
pow ros build --no-cache
```

| Option              | Description                                    |
| :------------------ | :--------------------------------------------- |
| `--no-cache`        | Build without using the Docker layer cache     |

---

## `pow check`

Run the Isaac Sim compatibility check to verify your system meets requirements.

```bash
pow check
```

---

## `pow asset`

Group of commands to manage Isaac Sim local assets.

### `pow asset set <PATH>`

Set the local asset path. Creates a symlink, registers aliases in `omniverse.toml`, and patches Isaac Sim configs.

```bash
# Set asset path with all alias support (default)
pow asset set /path/to/assets

# Set with specific alias support
pow asset set /path/to/assets -a isaacsim
pow asset set /path/to/assets -a simready

# Set without any alias patching
pow asset set /path/to/assets -a none
```

| Option                    | Description                                                |
| :------------------------ | :--------------------------------------------------------- |
| `-a`, `--alias-support`   | Alias target: `isaacsim`, `simready`, or `none` (repeatable) |


> [!NOTE]
> Currently, we only support `isaacsim` assets and `none` alias. We will add `simready` assets download support and others in the future.

### `pow asset unset`

Remove the local asset configuration — clears symlink, config, and alias patches.

```bash
pow asset unset
```

### `pow asset info`

Show the current local asset configuration status.

```bash
pow asset info
```

### `pow asset list`

List all supported assets in the registry.

```bash
pow asset list
```

### `pow asset add <TARGET>`

Install assets by group or name.

```bash
# Install by group (default)
pow asset add local-assets

# Install by name
pow asset add -n nova_carter_sensors

# Keep downloaded files or use assets to install from this path
pow asset add local-assets -k /path/to/keep
```

| Option          | Description                                      |
| :-------------- | :----------------------------------------------- |
| `-n`, `--name`  | Install asset by name                            |
| `-g`, `--group` | Install asset by group (default behavior)          |
| `-k`, `--keep`  | Keep downloaded files or use assets to install from this path |

---

## `pow lint`

Check `.usda` files for asset path compatibility issues. Defaults to `dry-run` when no subcommand is given.

### `pow lint [dry-run] [PATH]`

Report lint issues without modifying files.

```bash
# Lint current directory
pow lint

# Lint a specific path
pow lint ./usda

# Short output (file + line only)
pow lint -s
```

### `pow lint fix [PATH]`

Automatically fix lint issues in `.usda` files.

```bash
pow lint fix
pow lint fix ./usda
pow lint fix -s
```

| Option          | Description                          |
| :-------------- | :----------------------------------- |
| `-s`, `--short` | Show feedback with file path and line number only |

For a detailed explanation of each rule, patterns, and examples, see the [Lint Rules Guide](lint-rules.md).

---

## `pow --version`

Print the installed Pow CLI version.

```bash
pow --version
# or
pow -v
```
