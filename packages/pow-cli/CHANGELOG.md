# Changelog

All notable changes to the `pow-cli` package will be documented in this file.

## [0.2.0-rc.1] - 2026-06-14

### Added

- **Custom ROS Dockerfile (`pow init`)**
  - New `ros_dockerfile` config in `pow.toml` — point to a project-local Dockerfile that layers on top of the bundled `pow_simros_jazzy` base image
  - New `ros_docker_image` config in `pow.toml` — set a custom image name/tag for the custom build (defaults to `pow_simros`)
  - `pow init` now builds the custom image automatically after the base image when `ros_dockerfile` is set
  - `pow ros` launches the custom image when configured, otherwise falls back to the base image
- **`pow ros build`** — build the custom image from `ros_dockerfile` without re-running `pow init`; builds the `pow_simros_jazzy` base image first if it is missing, and supports `--no-cache`. `pow ros` is now a command group (bare `pow ros [args...]` usage is unchanged; `pow ros launch` is the explicit form)
- **Version flag (`pow --version` / `pow -v`)** — quickly check the installed `pow-cli` version from the command line
- **`pow sim`** — run Isaac Sim from any directory, with no project required: no `pyproject.toml` check and `pow.toml` is never read. Launches the default version (`5.1.0`, override with `-v/--version`) and forwards raw arguments straight to `isaac-sim.sh` (`pow sim -- --no-window`). The ROS 2 bridge environment is loaded by default (`--ros jazzy`); pass `--no-ros` to launch with the inherited environment instead

### Changed

- Updated CLI description to *"Manage Isaac Sim projects and simplify the development workflow"*
- Renamed status messages from *"Isaac ROS workspace"* to *"Isaac Sim ROS workspace"* for clarity
- `pow init` no longer creates the `scripts/`, `.assets/`, and `standalone/` project folders (only `exts/`, `.modules/`, `usda/`). A manually created `scripts/` folder is still mounted into the ROS container when present
- **Breaking (vs earlier 0.2.0 rc):** the `ros_container_name` config key was renamed to `ros_docker_image`. The container name is no longer configured directly — it is derived from the image name (`/` and `:` replaced with `_`), so default setups now get a container named `pow_simros_jazzy` instead of `pow_simros`
- **Breaking (vs earlier 0.2.0 rc):** ROS 2 Humble support was removed — the ROS workspace and docker integration now support Jazzy only (`Dockerfile.simros_humble` deleted). Isaac Sim itself still runs on Ubuntu 22.04 and 24.04; Jazzy workspaces build on both

### Fixed

- **`ros2` tab completion inside the `pow_simros` container** — the entrypoint sourced ROS before exec'ing bash, which carried environment variables but not bash completion functions. Interactive shells now re-source `/opt/ros/jazzy/setup.bash` and the workspace overlay via `/etc/bash.bashrc`, so `ros2` / `colcon` autocomplete works without manually sourcing `setup.bash` (requires rebuilding the image)

---

## [0.1.1] - 2026-06-14

### Fixed

- **ROS Docker container: `colcon build` fails for new packages** — The container
  entrypoint now detects stale build artifacts (left from a host-path build) and
  cleans `build/`, `install/`, and `log/` automatically before rebuilding.

---

## [0.1.0] - 2026-06-05

First stable release of `pow-cli`, promoted from `0.1.0-rc.1` with documentation improvements.


### Fixed

- Installation guide referenced incorrect `pow-cli` version

### Changed

- Improved README wording, tagline, and Profiles section

---

## [0.1.0-rc.1] - 2026-05-11

### Added

- **Asset Management (`pow asset`)**
  - `pow asset list` — list available Isaac Sim & Omniverse assets
  - `pow asset add` — download and register assets into the local asset folder (only support `isaacsim_5_1_0` for now)
  - `pow asset set / unset` — set/unset target local asset folder
  - `pow asset info` — display current local asset folder information
- **Linter (`pow lint`)**
  - New `pow lint` and `pow lint --fix` commands for `.usda` files
  - Detects absolute/relative local asset paths and rewrites them with correct aliases or asset urls (`user-home`, `pow-assets`)
  - Rule for validating `simros_ws` relative paths
- **ROS Integration (`pow ros`)**
  - `pow ros` command to build, launch, and attach to ROS 2 Docker containers
  - Verbose mode (`--verbose`) for runtime diagnostics
  - Separate Dockerfiles for ROS Humble and Jazzy distributions
  - Project `scripts/` directory mounted into the container
  - PyTorch with CUDA support available inside the container
  - `isaacsim_ros_ws` working directory configurable in `pow.toml`
- **Runner Improvements**
  - (experimental) `pow run --open <file>` option to open a USD stage on launch 
  - Non-existent `ext_folders` entries are now silently skipped instead of auto-created
- **Other**
  - `pow python` command with `--profile` flag for running standalone app under specified version of Isaac Sim's Python
  - `user-home` aliases automatically configured during `pow init`
  - `usda/` folder added to default project structure
  - `extends` support in `pow.toml` for profile-based configuration

### Fixed

- ROS Jazzy container build failure on Ubuntu 24.04
- CUDA version pinned to 12.1 for deterministic ROS builds
- `.ros` / `.ros2` mount and permission issues in the SimROS container
- SimROS entrypoint no longer warns when host-user directory already exists
- `pow run` no longer calls `open_stage` when no path is provided
- `pow asset unset` no longer accidentally removes `user-home` alias
- Duplicate and deprecated keys in generated `.vscode/settings.json`
- `pow init` now respects existing `isaacsim_ros_ws` value in existing `pow.toml`
- `pow ros` correctly attaches to an already-running container

### Changed

- Rewrite and refactor all core functionality of pow-cli
- Move commands under group `pow sim` to root `pow` command instead
- Remove pow-foxglove from repository 
- ROS-related logic extracted into dedicated `ros_manager.py` module
- CLI and core layers refactored for clearer separation of concerns

## [0.1.0a3] - 2026-01-27

### Fixed

- Fixed incorrect Ubuntu base Docker image version in `pow sim init` ROS workspace setup. Now correctly uses Ubuntu 22.04 for ROS Humble and Ubuntu 24.04 for ROS Jazzy (previously hardcoded to 22.04 for both).

## [0.1.0a2] - 2025-12-25

### Fixed

- `pow sim init` now allows overwriting existing VS Code settings to resolve Pylance `reportMissingImports` errors for Isaac Sim packages.
- Fixed an issue where the `ros_enable` flag did not correctly disable ROS workspace sourcing when set to `false` in an existing `pow.toml`.

## [0.1.0a1] - 2025-12-23

### Added

- Initial alpha release of Isaac Powerpack CLI (`pow`)
- **Core CLI Structure**
  - Main entry point with Click-based command group architecture
  - Hierarchical command organization under `pow sim` namespace

- **Simulation Commands (`pow sim`)**
  - `pow sim run` - Run Isaac Sim applications with automatic environment setup
    - Auto-discovery of project root via `pow.toml` configuration
    - ROS 2 workspace sourcing support
    - Isaac Sim setup file sourcing
    - Configurable app path and extension loading
  - `pow sim init` - Initialize Isaac Sim development environment
    - VS Code settings generation for Isaac Sim development
    - Asset browser cache fix utility
    - Project configuration scaffolding
  - `pow sim check` - Run Isaac Sim compatibility checker
    - Validates system compatibility with Isaac Sim requirements
  - `pow sim info` - Display Isaac Sim configuration information
    - Show local assets path configuration (`-l, --local-assets` flag)

- **Resource Management (`pow sim add`)**
  - `pow sim add local-assets` - Configure local Isaac Sim assets
    - Updates `isaacsim.exp.base.kit` with local asset paths
    - Configures asset browser and content browser folders
    - Supports versioned asset directories

### Dependencies

- `click>=8.1.7` - Command line interface framework
- `toml>=0.10.2` - TOML configuration file parsing
- Python 3.10+ required
