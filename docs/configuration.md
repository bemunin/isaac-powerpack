# Configuration

After running `pow init`, a `pow.toml` file is generated in your project root. This file controls how Isaac Sim is launched, which extensions are loaded, and how profiles customize runtime behavior.

## Default Configuration

The `[sim]` section defines the base (default) settings used by `pow run`:

```toml
[sim]
version = "5.1.0"
ext_folders = ["./exts"]
cpu_performance_mode = false
headless = false
enable_ros = false
isaacsim_ros_ws = "~/IsaacSim-ros_workspaces"
ros_dockerfile = ""
ros_container_name = "pow_simros"
exts = ["isaacsim.code_editor.vscode"]
raw_args = ["--/renderer/raytracingMotion/enabled=false"]
```

### Settings Reference

| Key                    | Type       | Default                              | Description |
|:-----------------------|:-----------|:-------------------------------------|:------------|
| `version`              | `string`   | `"5.1.0"`                            | Isaac Sim version to use. |
| `ext_folders`          | `string[]` | `["./exts"]`                         | Directories to search for custom extensions. |
| `cpu_performance_mode` | `bool`     | `false`                              | Enable CPU performance governor via `cpupower` (requires `sudo`). |
| `headless`             | `bool`     | `false`                              | Run Isaac Sim without the GUI window. |
| `enable_ros`           | `bool`     | `false`                              | Source the ROS 2 workspace environment before launching. |
| `isaacsim_ros_ws`      | `string`   | `"~/IsaacSim-ros_workspaces"`        | Path to the cloned IsaacSim-ros_workspaces directory. |
| `ros_dockerfile`       | `string`   | `""`                                 | Path (relative to project root) to a custom ROS Dockerfile built on top of the bundled `pow_simros_<distro>` base image. Empty = use the base image only. |
| `ros_container_name`   | `string`   | `"pow_simros"`                       | Name for the ROS container launched by `pow ros` (and the custom image tag when `ros_dockerfile` is set). |
| `exts`                 | `string[]` | `["isaacsim.code_editor.vscode"]`    | Extensions to enable on launch. |
| `raw_args`             | `string[]` | `["--/renderer/raytracingMotion/enabled=false"]` | Extra CLI arguments passed directly to Isaac Sim. |

---

## Custom ROS Image

By default, `pow init` builds a bundled ROS image tagged `pow_simros_<distro>`
(e.g. `pow_simros_humble`), and `pow ros` runs it in a container named
`pow_simros`.

To add your own ROS packages or tooling, point `ros_dockerfile` at a Dockerfile
in your project that extends the bundled base image:

```toml
[sim]
enable_ros = true
ros_dockerfile = "docker/Dockerfile.simros"
ros_container_name = "my_robot_sim"
```

Your custom Dockerfile **must** start with `FROM pow_simros_humble` (Ubuntu
22.04) or `FROM pow_simros_jazzy` (Ubuntu 24.04) so it inherits the base image's
workspace and entrypoint:

```dockerfile
FROM pow_simros_humble

RUN apt-get update && apt-get install -y ros-humble-my-pkg
# ... your customizations
```

When `ros_dockerfile` is set, `pow init` first builds the base image, then builds
your Dockerfile and tags it with `ros_container_name`. `pow ros` then runs that
custom image in a container named `ros_container_name`.

> [!NOTE]
> `pow.toml` is written at the end of `pow init`. After setting `ros_dockerfile`
> and creating your Dockerfile, re-run `pow init` to build the custom image.

---

## Profiles

Profiles let you define named sets of overrides that you can switch between at runtime:

```bash
pow run                  # Uses the default [sim] settings
pow run -p perf          # Uses the "perf" profile
pow run -p my_profile    # Uses a custom profile you defined
```

### Defining a Profile

Add a `[[profiles]]` entry in `pow.toml`. Each profile requires a `name` and can optionally `extends` another profile:

```toml
[[profiles]]
name = "perf"
extends = "default"
cpu_performance_mode = true
headless = false
```

- **`name`** — The identifier you pass to `pow run -p <name>`.
- **`extends`** — Which profile to inherit settings from. Use `"default"` (or omit) to inherit from `[sim]`. You can also point to another profile name for multi-level inheritance.

### Override vs Append

There are two ways a profile can modify list values from its base:

#### Override (replace the entire list)

Assigning a key directly **replaces** the base value completely:

```toml
[[profiles]]
name = "minimal"
extends = "default"
# This REPLACES the default exts list entirely
exts = ["your.custom.extension"]
```

#### Append (extend the base list)

Using the `.add` suffix **appends** items to the inherited list:

```toml
[[profiles]]
name = "perf"
extends = "default"
# This APPENDS to the default raw_args list
raw_args.add = [
    "--/rtx-transient/dlssg/enabled=true",
    "--/rtx/reflections/enabled=false",
]
```

The `.add` keyword works with any list-type setting (`exts`, `raw_args`, `ext_folders`, etc.).

> [!NOTE]
> The `.add` suffix only works with list values. Using it on a non-list setting (e.g., `headless.add`) will produce an error.

### Profile Inheritance Chain

Profiles can extend other profiles, not just `"default"`:

```toml
[sim]
exts = ["isaacsim.code_editor.vscode"]
raw_args = ["--/renderer/raytracingMotion/enabled=false"]

[[profiles]]
name = "perf"
extends = "default"
cpu_performance_mode = true

[[profiles]]
name = "perf-headless"
extends = "perf"
headless = true
```

In this example:
- `pow run -p perf` → inherits `[sim]` + enables `cpu_performance_mode`
- `pow run -p perf-headless` → inherits `perf` (which inherits `[sim]`) + enables `headless`

> [!WARNING]
> Circular inheritance (e.g., profile A extends B, B extends A) is detected and will produce an error.

---

## Full Example

```toml
[sim]
version = "5.1.0"
ext_folders = ["./exts"]
cpu_performance_mode = false
headless = false
enable_ros = false
isaacsim_ros_ws = "~/IsaacSim-ros_workspaces"
ros_dockerfile = ""
ros_container_name = "pow_simros"
exts = ["isaacsim.code_editor.vscode"]
raw_args = ["--/renderer/raytracingMotion/enabled=false"]

[[profiles]]
name = "perf"
extends = "default"
cpu_performance_mode = true
# Override exts entirely
exts = ["your.custom.extension"]
# Append additional raw_args
raw_args.add = [
    # Enable framegen 2x (support only for RTX 50 series)
    "--/rtx-transient/dlssg/enabled=true",
    "--/rtx-transient/internal/dlssg/interpolatedFrameCount=1",
    # Disable rtx features for performance
    "--/rtx/reflections/enabled=false",
    "--/rtx/translucency/enabled=false",
]

[[profiles]]
name = "headless"
extends = "default"
headless = true
```
