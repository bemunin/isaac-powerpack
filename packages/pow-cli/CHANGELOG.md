# Changelog

All notable changes to the `pow-cli` package will be documented in this file.

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
