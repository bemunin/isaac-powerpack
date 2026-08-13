<p align="center">
    <img src="https://raw.githubusercontent.com/bemunin/isaac-powerpack/main/docs/public/logo.svg" width="400"/>
</p>

> Simplify NVIDIA Isaac Sim development with *Isaac Powerpack*

**Isaac Powerpack** (or **Pow** for short) is a project management tool that aims to reduce friction of **NVIDIA Isaac Sim** application development.

Key features:

* ⚡ CLI to simplify Isaac Sim workstation installation, setup, and launching.
* 📁 Provides an organized folder structure, ready to get started.
* 📦 Keeps your Isaac Sim projects isolated from each other.
* 🛠️ Allows for configuring different Isaac Sim runtime settings via profiles.
* 🐢 Simple commands for building and running Isaac Sim ROS 2 Docker containers.
* 🎨 Local asset management and USDA linting tools.

For the full list of ready-to-use commands and options, see the [CLI Reference](docs/cli-reference.md).

## Installation

> [!IMPORTANT]
> This project is in early development. Features and APIs are still evolving and are subject to breaking changes. Please check the [Changelog](packages/pow-cli/CHANGELOG.md) for the latest updates.


Pow CLI requires uv and Docker (for ROS 2 container support). Ensure both are installed before proceeding:
- [uv Installation Guide](https://docs.astral.sh/uv/)
- [Docker Installation Guide](https://docs.docker.com/get-docker/)

### User-level install

Install `pow` once for your user and run it from any directory — no project needed:

```bash
# install pow cli as a user-level tool
uv tool install pow-cli==0.2.0

# add uv's tool directory to your PATH (once, then restart your shell)
uv tool update-shell
```

`pow` is now available everywhere — for example, run Isaac Sim from any directory
with no project required:

```bash
pow sim
```

Manage the installation with:

```bash
# show the installed version
uv tool list

# move to the latest release
uv tool install pow-cli@latest --force

# remove it
uv tool uninstall pow-cli
```

> [!NOTE]
> Installing with an exact pin (`==0.2.0`) means `uv tool upgrade pow-cli` reports
> *"Nothing to upgrade"*. Use `uv tool install pow-cli@latest --force` to move to a
> newer version.

### Project install

Project commands such as `pow init` operate on a project folder. Add Pow CLI as a
project dependency so the version is pinned in your `pyproject.toml`:

```bash
# create your project folder
mkdir sim-project && cd sim-project

# create pyproject.toml and initialize uv
uv init --bare

# Initialize project, install isaac sim, setup ROS, create config file
pow init

```

### Usages

Check the installed Pow CLI version

```bash
pow --version
# or
pow -v
```

Run Isaac Sim

```bash

# Run Isaac Sim GUI
pow run

# or Run standalone app
pow python path/to/python_standalone_app.py
```

Run ROS 2 container

```bash
# Bash into the docker container, you can run this command multiple time
# later command will attach to the running container
pow ros
```

## Profiles

After running `pow init`, a `pow.toml` configuration file is generated in your project root. This file controls Isaac Sim runtime settings and supports multiple profiles, letting you switch between them depending on your use case:

```bash
pow run -p perf        # Use the "perf" profile
pow run -p default     # Use the default profile (or just `pow run`)
```

Each profile can extend another and override specific settings such as `cpu_performance_mode` or `headless`. To extend a list instead of replacing it, use the `.add` suffix (e.g. `exts.add`, `raw_args.add`).

In the example below, the `"perf"` profile extends `"default"`, enables CPU performance mode, and appends to `raw_args` using `raw_args.add`. Note that `exts` (without `.add`) replaces the inherited value entirely.

```toml
[sim]
version = "6.0.1"
ext_folders = ["./exts"]
cpu_performance_mode = false
headless = false
enable_ros = false
isaacsim_ros_ws = "~/IsaacSim-ros_workspaces"
ros_dockerfile = ""
ros_docker_image = "pow_simros"
exts = ["isaacsim.code_editor.vscode"]
raw_args = ["--/renderer/raytracingMotion/enabled=false"]

[[profiles]]
name = "perf"
extends = "default"
cpu_performance_mode = true
exts = ["your.custom.extension"]
raw_args.add = [
    # Enable frame generation 2x (RTX 50 series only)
    "--/rtx-transient/dlssg/enabled=true",
    "--/rtx-transient/internal/dlssg/interpolatedFrameCount=1",
    # Disable RTX features for better performance
    "--/rtx/reflections/enabled=false",
    "--/rtx/translucency/enabled=false"
]
```

For the full settings reference, profile inheritance, and examples, see the [Configuration Guide](docs/configuration.md).

## Local Assets

The concept of Local assets is to download predefined assets in advanced from Nvidia Omniverse to your local machine to accelerate scene building and eliminate download bottleneck during scene creation. 

You can attach the assets directory using `pow asset set` command to `~/.pow/assets` and download provided collection using `pow asset add`. Currently, only official Isaac Sim assets are available to download with add command.

For more detail and feature about Local Assets command line, see `pow asset` command group in [CLI Reference](docs/cli-reference.md).

## Folder Structure    

After running `pow init`, your project will have the following structure:

```
sim-project/
├── .vscode/              # VSCode configuration (launch.json, settings.json, etc.)
├── .modules/             # 3rd party module that use in your project e.g. pegasus sim
├── exts/                 # Your custom Isaac Sim extensions
├── usda/                 # USD scene description files
├── _isaacsim/            # Symlink → ~/.pow/isaacsim/<version> for intellisense and autocomplete
├── .gitignore            # Pre-configured gitignore for Isaac Sim projects
├── pow.toml              # Project configuration (sim settings, profiles)
└── pyproject.toml        # Python project manifest
```

`pow init` also creates a **global directory** at `~/.pow` (shared across all projects):

```
~/.pow/
├── isaacsim/             # Downloaded Isaac Sim installations
│   ├── 5.1.0/            # Isaac Sim 5.1.0 app files
│   └── 6.0.1/            # Isaac Sim 6.0.1 app files
├── modules/              # Shared modules
├── assets/               # mounting folder for local assets
└── system.toml           # Global system configuration ([sim] default_version, [asset])
```


## Support

| Platform              | Version / Notes              |
| :-------------------- | :--------------------------- |
| OS                    | Ubuntu 22.04 / 24.04         |
| ROS2 Docker           | Jazzy                        |
| Isaac Sim             | `6.0.1` (default), `5.1.0`   |

> [!NOTE]
> Isaac Sim runs on Ubuntu 22.04 and 24.04; the ROS 2 workspace and docker integration support Jazzy only.  
> `pow init` asks which Isaac Sim version to install, or takes it from `--sim-version` / the `[sim] version` key of an existing `pow.toml`.  

<br>    

## Contribution

See [Contribution Guide](docs/contributing.md)

Maintainers publishing a new version: see the [Release Guide](docs/releasing.md).

## License

[Apache-2.0](LICENSE).
