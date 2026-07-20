"""Init command implementation."""

import time
from pathlib import Path

import click
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

from ..common.utils import console
from ..core.initializer import Initializer
from ..core.ros_manager import RosManager



# ── Logo ──────────────────────────────────────────────────────────────────────
def draw_logo():
# A brighter, punchier neon green
    NEON_GREEN = "#76ff7a" 
    
    # Refined font with better curves and proportions
    font = {
        'P': ["█████▄", "██▄▄██", "██▀▀▀ ", "██    "],
        'O': ["▄████▄", "██  ██", "██  ██", "▀████▀"],
        'W': ["██    ██", "██ ▄▄ ██", "████████", "▀██  ██▀"],
        'E': ["██████", "██▄▄▄ ", "██▀▀▀ ", "██████"],
        'R': ["█████▄", "██▄▄██", "██▀██ ", "██  ██"],
        'A': ["▄████▄", "██▄▄██", "██▀▀██", "██  ██"],
        'C': ["▄█████", "██    ", "██    ", "▀█████"],
        'K': ["██  ██", "██▄██ ", "██▀██ ", "██  ██"],
    }

    text = "POWERPACK"
    
    console.print("\n")
    
    # 1. Top UI framing line
    console.print("[dim white]" + "─" * 66 + "[/]\n")

    # 2. Perfectly Centered ISAAC Badge
    # (64 total width of text - 13 width of badge) / 2 = 25 spaces of padding
    console.print("                         [bold black on white]  I S A A C  [/]\n")

    # 3. The POWERPACK Text
    for i in range(4):
        line_content = ""
        for char in text:
            if char in font:
                # Add 1 space between each letter for breathability
                line_content += font[char][i] + " " 
        
        console.print(f"[{NEON_GREEN}]{line_content}[/]")

    # 4. Bottom UI framing and prompt
    console.print("\n[dim white]" + "─" * 66 + "[/]")

# ── Step helpers ──────────────────────────────────────────────────────────────

def _step1_check_config(global_dir_name: str) -> bool:
    """Print config header and verify pyproject.toml exists. Return False to abort."""
    if not Path("pyproject.toml").exists():
        console.print(
            "\n[bold red][1/10] ❌ Error:[/bold red] pyproject.toml not found. "
            "Please run this command in a valid project directory."
        )
        return False
    console.print(
        f"\n[bold blue][1/10] 🔧 Config:[/bold blue] "
        f"Using global directory [bold green]'{global_dir_name}'[/bold green]"
    )
    return True


def _step2_check_existing_config(initializer: Initializer) -> bool:
    """Ask whether to override an existing pow.toml. Returns override flag."""
    if not Path("pow.toml").exists():
        console.print(
            "[bold blue][2/10] 🔍 Check Existing Config [/bold blue] "
            "No existing pow.toml found. Proceeding..."
        )
        return True  # nothing to preserve, will create fresh

    console.print(
        "[bold blue][2/10] 🔍 Check Existing Config: [/bold blue] "
        "[yellow]Found existing pow.toml[/yellow]"
    )
    override = Confirm.ask(
        "   Do you want to override existing pow.toml?",
        default=False,
    )
    if override:
        console.print("   [green]Proceeding and will override pow.toml.[/green]")
    else:
        console.print("   [yellow]Proceeding with existing pow.toml.[/yellow]")
        initializer.read_config()
        console.print("   [green]✔ Read existing pow.toml configuration.[/green]")
    return override


def _step3_global_folder(initializer: Initializer, global_path):
    """Create the .pow global folder and print the result."""
    console.print(
        f"[bold blue][3/10] 📂 Global Folder:[/bold blue] Preparing [dim]{global_path}[/dim]..."
    )
    init_data = initializer.create_global_folder()

    if init_data["global_existed"]:
        console.print(
            f"   [yellow]✔[/yellow] Global directory [dim]{global_path}[/dim] already exists."
        )
    else:
        console.print(
            f"   [green]✔[/green] Global directory [dim]{global_path}[/dim] prepared successfully."
        )

    system_toml_result = initializer.create_system_toml()
    if system_toml_result["status"] == "Created":
        console.print(
            f"   [green]✔[/green] Created system.toml: [dim]{system_toml_result['path']}[/dim]"
        )
    else:
        console.print(
            f"   [yellow]✔[/yellow] system.toml already exists: [dim]{system_toml_result['path']}[/dim]"
        )


def _step4_download_isaacsim(initializer: Initializer) -> dict | None:
    """Download Isaac Sim with a Rich progress bar. Returns result dict or None on error."""
    console.print("[bold blue][4/10] 📦 Isaac Sim App:[/bold blue] Installing Isaac Sim 5.1.0...")

    result = None
    error = None

    last_completed = 0
    last_time = time.time()
    current_phase = "download"

    with Progress(
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=40),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        TextColumn("[bold cyan]{task.fields[speed]}"),
        console=console,
        refresh_per_second=10,
    ) as progress:
        download_task = progress.add_task(
            "download", filename="isaac-sim-5.1.0.zip", total=None, speed="0 MB/s"
        )
        extract_task = progress.add_task(
            "extract", filename="", total=None, speed=" ", visible=False
        )

        def progress_callback(completed, total):
            nonlocal last_completed, last_time, current_phase
            if not total:
                return
            now = time.time()
            if current_phase == "download":
                progress.update(download_task, total=total, completed=completed)
                elapsed = now - last_time
                if elapsed >= 0.5:
                    speed_mb = ((completed - last_completed) / (1024 * 1024)) / elapsed
                    progress.update(download_task, speed=f"{speed_mb:.1f} MB/s")
                    last_completed = completed
                    last_time = now
            elif current_phase == "extract":
                progress.update(extract_task, total=total, completed=completed)

        def status_callback(status):
            nonlocal current_phase, last_completed, last_time
            if status == "Downloading":
                current_phase = "download"
            elif status == "Extracting":
                current_phase = "extract"
                progress.update(download_task, visible=False)
                progress.update(
                    extract_task,
                    filename="isaac-sim-5.1.0 [yellow](Extracting...)[/yellow]",
                    speed=" ",
                    completed=0,
                    total=None,
                    visible=True,
                )
                last_completed = 0
                last_time = time.time()
            elif status == "Extracted":
                progress.update(
                    extract_task,
                    filename="isaac-sim-5.1.0 [green](Extracted → 5.1.0)[/green]",
                )
                time.sleep(1)

        try:
            result = initializer.download_isaacsim(
                progress_callback=progress_callback,
                status_callback=status_callback,
            )
        except Exception as e:
            error = e

    # Print outside the progress context so lines don't get consumed
    if error:
        console.print(f"   [bold red]❌ Error:[/bold red] {error}")
        return None
    if result["status"] == "Already installed":
        console.print(
            f"   [yellow]✔[/yellow] Isaac Sim 5.1.0 is already installed at [dim]{result['path']}[/dim]"
        )
    else:
        console.print(
            f"   [green]✔[/green] Downloaded and extracted to [dim]{result['path']}[/dim]"
        )
    return result


def _step5_optimization(initializer: Initializer, isaacsim_path: str):
    """Apply Isaac Sim post-install fixes."""
    console.print("[bold blue][5/10] ⚡ Optimization:[/bold blue] Applying Isaac Sim fixes...")
    with console.status("Fixing isaacsim.asset.browser cache file missing..."):
        fixed = initializer.fix_asset_browser_cache(isaacsim_path)
    if fixed:
        console.print("   [green]✔[/green] Created missing cache file.")
    else:
        console.print("   [yellow]✔[/yellow] Cache file already exists.")


def _step6_ros_integration(
    initializer: Initializer,
    global_dir_name: str,
    forced_value: bool | None = None,
    forced_ws: str | None = None,
) -> tuple[bool, str]:
    """Prompt for ROS integration and set it up.

    Returns:
        (ros_enabled, isaacsim_ros_ws)  –  whether ROS was enabled and the
        tilde-relative path chosen for IsaacSim-ros_workspaces.
    """
    default_ws = "~/IsaacSim-ros_workspaces"
    ros_mgr = RosManager(config=initializer.config)
    console.print("[bold blue][6/10] 🤖 ROS Integration:[/bold blue]")
    
    if forced_value is not None:
        enabled = forced_value
        status_text = "[bold green]enabled[/bold green]" if enabled else "[bold yellow]disabled[/bold yellow]"
        console.print(f"   Using existing ROS setting from pow.toml: {status_text}")
    else:
        enabled = Confirm.ask("   Enable ROS integration?", default=True)

    if not enabled:
        console.print("   [yellow]⊖[/yellow] Skipping ROS integration.")
        return False, default_ws

    # Use existing workspace path from config, or ask the user
    if forced_ws is not None:
        ws_path = forced_ws
        console.print(f"   Using existing workspace path from pow.toml: [bold green]{ws_path}[/bold green]")
    else:
        ws_path = Prompt.ask(
            "   Path to clone IsaacSim-ros_workspaces",
            default=default_ws,
        )
    # Normalise: keep tilde-relative for storage, but resolve for display
    if ws_path.startswith("~"):
        display_path = ws_path
    else:
        # Convert absolute paths back to tilde form when possible
        home = str(Path.home())
        if ws_path.startswith(home):
            display_path = "~" + ws_path[len(home):]
        else:
            display_path = ws_path
    console.print(f"   [dim]Workspace path:[/dim] {display_path}")

    ros_cloned = False

    def ros_status_callback(state):
        nonlocal ros_cloned
        if state == "cloning":
            ros_cloned = True
            status.update("[bold green]Cloning Isaac Sim ROS workspace...")
        elif state == "existed":
            status.update("[bold yellow]Isaac Sim ROS workspace already exists.")

    # Resolve the tilde path for actual filesystem operations
    resolved_ws = Path(ws_path).expanduser()

    ros_setup_failed = False

    with console.status("Preparing ROS workspace...") as status:
        try:
            ros_res = ros_mgr.setup_ros_workspace(
                status_callback=ros_status_callback,
                ws_path=resolved_ws,
            )
        except Exception as e:
            ros_setup_failed = True
            console.print(f"   [bold red]❌ ROS Setup Error:[/bold red] {e}")

    if ros_setup_failed:
        console.print("   [yellow]⊖[/yellow] Skipping remaining steps due to ROS setup error.")
        raise SystemExit(1)

    if ros_cloned:
        console.print(f"   [green]✔[/green] Cloned IsaacSim-ros_workspaces to [dim]{display_path}[/dim]")
    else:
        console.print(f"   [yellow]✔[/yellow] IsaacSim-ros_workspaces already available in [dim]{display_path}[/dim]")

    bridge_distro = ros_mgr.config.ros_bridge_distro
    console.print(
        f"   [green]✔[/green] ROS bridge: [bold]{bridge_distro}[/bold] "
        f"(Ubuntu {ros_res['ubuntu_version']}) via Isaac Sim internal libs."
    )

    # Build pow_simros Docker image
    simros_already_built = False

    def simros_status_callback(state):
        nonlocal simros_already_built
        if state == "simros_built":
            simros_already_built = True
            simros_status.update("[bold yellow]pow_simros image already exists.")
        elif state == "simros_building":
            simros_status.update("[bold green]Building pow_simros image...")
        elif state.startswith("simros_building:"):
            line = state[len("simros_building:"):]
            simros_status.update(f"[bold green]pow_simros build:[/bold green] [dim]{line[:80]}[/dim]")

    with console.status("Building pow_simros image...") as simros_status:
        try:
            ros_mgr.build_simros_image(
                status_callback=simros_status_callback,
                ws_path=resolved_ws,
            )
        except Exception as e:
            console.print(f"   [bold red]❌ pow_simros Build Error:[/bold red] {e}")
            console.print("   [yellow]⊖[/yellow] Skipping remaining steps due to build error.")
            raise SystemExit(1)

    simros_label = f"pow_simros_[bold]{ros_res['ros_distro']}[/bold]"
    if simros_already_built:
        console.print(f"   [yellow]✔[/yellow] Docker image {simros_label} already exists.")
    else:
        console.print(f"   [green]✔[/green] Docker image {simros_label} built successfully.")

    # Build custom ROS image layered on top of pow_simros_<distro>
    custom_dockerfile = ros_mgr.config.ros_dockerfile
    if custom_dockerfile:
        custom_image = ros_mgr.config.ros_docker_image

        def custom_status_callback(state):
            if state == "custom_building":
                custom_status.update(f"[bold green]Building custom image '{custom_image}'...")
            elif state.startswith("custom_building:"):
                line = state[len("custom_building:"):]
                custom_status.update(f"[bold green]custom build:[/bold green] [dim]{line[:80]}[/dim]")

        with console.status(f"Building custom image '{custom_image}'...") as custom_status:
            try:
                ros_mgr.build_custom_ros_image(status_callback=custom_status_callback)
            except Exception as e:
                console.print(f"   [bold red]❌ Custom ROS Build Error:[/bold red] {e}")
                console.print("   [yellow]⊖[/yellow] Skipping remaining steps due to build error.")
                raise SystemExit(1)

        console.print(
            f"   [green]✔[/green] Custom Docker image [bold]{custom_image}[/bold] "
            f"built from [dim]{custom_dockerfile}[/dim]."
        )

    return True, display_path


def _step7_project_structure(initializer: Initializer):
    """Create local project folders and .gitignore."""
    console.print("[bold blue][7/10] 🏗️ Project Structure:[/bold blue] Creating local folders...")
    local_folders = ["exts", ".modules", "usda"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(
            description="Setting up project folders...", total=len(local_folders) + 1
        )
        struct_data = initializer.setup_project_structure(local_folders)
        for res in struct_data["results"]:
            progress.update(task, advance=1, description=f"Setting up {res['path']}...")
            time.sleep(0.1)

    console.print("   [green]✔[/green] Local folders created.")

    gitignore_res = next((r for r in struct_data["results"] if r["path"] == ".gitignore"), None)
    if gitignore_res and gitignore_res["status"] == "Created from template":
        console.print("   [green]✔[/green] Created .gitignore (from template)")
    elif gitignore_res and gitignore_res["status"] == "Template not found":
        console.print("   [yellow]⚠[/yellow] .gitignore template not found. [dim]Skipped.[/dim]")
    else:
        console.print("   [yellow]✔[/yellow] .gitignore already exists. [dim]Kept existing.[/dim]")


def _step8_project_link(initializer: Initializer):
    """Symlink managed Isaac Sim to local project."""
    console.print("[bold blue][8/10] 🔗 Project Link:[/bold blue] Linking Isaac Sim to project...")
    result = initializer.link_managed_isaacsim()
    if result["status"] == "Created":
        console.print(f"   [green]✔[/green] Created symlink: [dim]{result['path']}[/dim]")
    elif result["status"] == "Existed":
        console.print(f"   [yellow]✔[/yellow] Symlink already exists: [dim]{result['path']}[/dim]")
    elif result["status"] == "Error":
        console.print(f"   [bold red]❌ Error:[/bold red] {result['message']}")


def _step9_vscode_setup(initializer: Initializer):
    """Setup VSCode configuration for the project."""
    console.print("[bold blue][9/10] 💻 VSCode Config:[/bold blue] Setting up VSCode configs...")
    result = initializer.setup_vscode_configs()
    if result["status"] == "Success":
        for res in result["results"]:
            status_symbol = "[green]✔[/green]" if "patched" in res["status"] or res["status"] == "Copied" else "[yellow]⚠[/yellow]"
            console.print(f"   {status_symbol} {res['file']}: [dim]{res['status']}[/dim]")
    else:
        console.print(f"   [bold red]❌ Error:[/bold red] {result['message']}")


def _step10_finalize(
    initializer: Initializer,
    override_pow_toml: bool,
    ros_enabled: bool,
    isaacsim_ros_ws: str = "~/IsaacSim-ros_workspaces",
):
    """Generate pow.toml configuration."""

    
    console.print("[bold blue][10/10] ✅ Finalizing:[/bold blue] Generating configuration...")
    
    # Ensure user-home alias in Omniverse config
    alias_result = initializer.setup_omniverse_user_home_alias()
    if alias_result["status"] == "created":
        console.print(f"   [green]✔[/green] Added user-home alias in [dim]{alias_result['path']}[/dim]")
    elif alias_result["status"] == "updated":
        console.print(f"   [green]✔[/green] Updated user-home alias in [dim]{alias_result['path']}[/dim]")
    else:
        console.print(f"   [yellow]✔[/yellow] user-home alias already set in [dim]{alias_result['path']}[/dim]")

    # Create pow.toml
    result = initializer.create_pow_toml(
        override=override_pow_toml,
        enable_ros=ros_enabled,
        isaacsim_ros_ws=isaacsim_ros_ws,
    )
    if result["status"] == "Created":
        console.print("   [green]✔[/green] Created pow.toml (from template)")
    elif result["status"] == "Existed":
        console.print("   [yellow]✔[/yellow] Kept existing pow.toml")
    else:
        console.print("   [yellow]⚠[/yellow] pow.toml template not found. [dim]Skipped.[/dim]")


# ── Command entry point ───────────────────────────────────────────────────────

@click.command(name="init")
def init_cmd():
    """Initialize Isaac Sim project."""
    initializer = Initializer()
    config = initializer.get_config_path()
    global_dir_name = config["global_dir_name"]
    global_path = config["global_path"]

    # draw_logo()

    console.print(
            "\n"
            "[bold cyan]🚀 Initialization Pow Project[/bold cyan]",
    )

    if not _step1_check_config(global_dir_name):
        return

    override_pow_toml = _step2_check_existing_config(initializer)
    _step3_global_folder(initializer, global_path)

    download_result = _step4_download_isaacsim(initializer)
    if download_result is None:
        return

    _step5_optimization(initializer, download_result["path"])
    
    # Use existing ROS setting if not overriding pow.toml
    ros_forced = None
    ros_ws_forced = None
    if not override_pow_toml:
        try:
            ros_forced = initializer.config.get("enable_ros", False)
            ros_ws_forced = initializer.config.get("isaacsim_ros_ws", None)
        except Exception:
            pass

    ros_enabled, isaacsim_ros_ws = _step6_ros_integration(
        initializer, global_dir_name, forced_value=ros_forced, forced_ws=ros_ws_forced,
    )
    _step7_project_structure(initializer)
    _step8_project_link(initializer)
    _step9_vscode_setup(initializer)

    _step10_finalize(initializer, override_pow_toml, ros_enabled, isaacsim_ros_ws)

    console.print(
        Panel(
            "[bold green]✨ Project initialized successfully! ✨[/bold green]",
            border_style="green",
        )
    )
