"""Runner core logic."""

import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

from .models.pow_config import PowConfig
from .ros_manager import RosManager

console = Console()

CPU_DEVICES_PATH = Path("/sys/devices/system/cpu")

class Runner:
    """Handles execution of Isaac Sim and related tools."""

    @staticmethod
    def _cpu_governors() -> set[str]:
        """Scaling governor of every CPU; empty when cpufreq is unavailable.

        The sysfs entries are world-readable, so this needs no privileges.
        """
        governors: set[str] = set()
        for path in CPU_DEVICES_PATH.glob("cpu*/cpufreq/scaling_governor"):
            try:
                governors.add(path.read_text().strip())
            except OSError:
                continue
        return governors

    @staticmethod
    def ensure_cpu_performance_mode() -> None:
        """Put the CPU governor into performance mode, asking for sudo only if needed.

        Every early return here is a password prompt avoided: the governor may
        already be set from a previous run, cpufreq may not exist at all, or
        ``cpupower`` may not be installed.  When the change really is needed the
        prompt behaves exactly as it always has.
        """
        governors = Runner._cpu_governors()

        if governors == {"performance"}:
            console.print("[dim]CPU already in performance mode.[/dim]")
            return

        if not governors:
            console.print(
                "[dim]CPU frequency scaling not available, skipping performance mode.[/dim]"
            )
            return

        if shutil.which("cpupower") is None:
            console.print(
                "[red]cpupower not found, skipping performance mode.[/red]\n"
                "[dim]Install it with: sudo apt install linux-tools-common "
                'linux-tools-$(uname -r)[/dim]'
            )
            return

        # `sudo -v` only validates cached credentials - it runs no command and is
        # silent on success - and `-n` keeps it from ever prompting.  A non-zero
        # exit means the password has not been entered recently, so that is the
        # only case where the notice below is worth printing.
        cached = subprocess.run(["sudo", "-n", "-v"], capture_output=True).returncode == 0
        if not cached:
            console.print("[yellow]Setting CPU to performance mode (requires sudo)...[/yellow]")

        try:
            subprocess.run(["sudo", "cpupower", "frequency-set", "-g", "performance"], check=True)
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to set CPU performance mode: {e}[/red]")

    @staticmethod
    def build_launch_command(
        config: PowConfig,
        profile_name: str = "default",
        extra_args: list[str] | None = None,
        open_path: str | None = None,
    ) -> list[str]:
        """Build the Isaac Sim launch command from configuration."""
        isaacsim_version = config.get("version", PowConfig.ISAACSIM_VERSION)
        isaacsim_dir = config.global_path / "isaacsim" / isaacsim_version
        
        launch_script = isaacsim_dir / "isaac-sim.sh"
        if not launch_script.exists():
            raise click.ClickException(f"Isaac Sim script not found at {launch_script}")

        cmd = [str(launch_script)]

        ext_folders = config.get("ext_folders", [], profile=profile_name)
        project_root = config.project_root or Path.cwd()
        for folder in ext_folders:
            resolved = (project_root / folder).resolve()
            if resolved.is_dir():
                cmd.extend(["--ext-folder", str(resolved)])

        if config.get("headless", False, profile=profile_name):
            cmd.append("--no-window")

        for ext in config.get("exts", [], profile=profile_name):
            cmd.extend(["--enable", ext])

        for arg in config.get("raw_args", [], profile=profile_name):
            cmd.append(arg)

        if open_path is not None:
            project_root = config.project_root or Path.cwd()

            if open_path == ".":
                resolved_path = project_root
            else:
                resolved_path = Path(open_path).expanduser().resolve()

            cmd.extend(["--exec", f"open_stage.py file://{resolved_path}"])

        if extra_args:
            cmd.extend(extra_args)

        return cmd

    @staticmethod
    def run_isaacsim(profile: str = "default", extra_args: list[str] | None = None, open_path: str | None = None) -> None:
        """Run an Isaac Sim App based on profile."""
        config = PowConfig()
        if config.project_root is None:
            raise click.ClickException("Not initialized. Run `pow init` first.")

        if platform.machine().lower() not in ("x86_64", "amd64"):
            raise click.ClickException("Unsupported platform. Only x86_64 is supported by Isaac Sim.")

        enable_ros = config.get("enable_ros", False, profile=profile)
        source_env = RosManager.isaacsim_bridge_env(config, profile=profile) if enable_ros else os.environ.copy()

        cmd = Runner.build_launch_command(config, profile, extra_args, open_path)

        if config.get("cpu_performance_mode", False, profile=profile):
            Runner.ensure_cpu_performance_mode()

        console.print(f"[blue]Running: {' '.join(shlex.quote(c) for c in cmd)}[/blue]")
        
        try:
            subprocess.run(cmd, check=True, env=source_env)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"Isaac Sim process failed with exit code {e.returncode}")
        except KeyboardInterrupt:
            console.print("[yellow]Isaac Sim launch aborted by user.[/yellow]")

    @staticmethod
    def run_sim(
        version: str = PowConfig.ISAACSIM_VERSION,
        ros_bridge: str | None = PowConfig.ROS_BRIDGE,
        extra_args: list[str] | None = None,
    ) -> None:
        """Run Isaac Sim from any directory, independent of any project.

        Unlike :meth:`run_isaacsim` this reads no pow.toml and requires no
        pyproject.toml, so it works outside a pow project.  Only the global
        directory name is looked up (see :meth:`PowConfig.resolve_global_path`);
        every Isaac Sim argument comes from *extra_args*.

        Args:
            version: Isaac Sim version under ``<global_path>/isaacsim/``.
            ros_bridge: ROS 2 bridge distro to load, or ``None`` to launch with
                the inherited environment and no bridge.
            extra_args: Arguments forwarded verbatim to ``isaac-sim.sh``.
        """
        if platform.machine().lower() not in ("x86_64", "amd64"):
            raise click.ClickException("Unsupported platform. Only x86_64 is supported by Isaac Sim.")

        isaacsim_dir = PowConfig.resolve_global_path() / "isaacsim" / version
        launch_script = isaacsim_dir / "isaac-sim.sh"

        if not launch_script.exists():
            raise click.ClickException(
                f"Isaac Sim not found at {launch_script}\n"
                "Run 'pow init' first to install Isaac Sim."
            )

        source_env = (
            RosManager.bridge_env(isaacsim_dir, ros_bridge)
            if ros_bridge
            else os.environ.copy()
        )

        cmd = [str(launch_script)]
        if extra_args:
            cmd.extend(extra_args)

        console.print(f"[blue]Running: {' '.join(shlex.quote(c) for c in cmd)}[/blue]")

        try:
            subprocess.run(cmd, check=True, env=source_env)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"Isaac Sim process failed with exit code {e.returncode}")
        except KeyboardInterrupt:
            console.print("[yellow]Isaac Sim launch aborted by user.[/yellow]")

    @staticmethod
    def run_python(profile: str = "default", extra_args: list[str] | None = None) -> None:
        """Run the Isaac Sim bundled Python interpreter.

        Wraps ``<global_path>/isaacsim/<version>/python.sh``, forwarding
        every argument to it.
        """
        config = PowConfig()
        if config.project_root is None:
            raise click.ClickException("Not initialized. Run `pow init` first.")

        isaacsim_version = config.get("version", PowConfig.ISAACSIM_VERSION)
        python_script = config.global_path / "isaacsim" / isaacsim_version / "python.sh"

        if not python_script.exists():
            raise click.ClickException(
                f"python.sh not found at {python_script}\n"
                "Run 'pow init' first to install Isaac Sim."
            )

        enable_ros = config.get("enable_ros", False, profile=profile)
        source_env = RosManager.isaacsim_bridge_env(config, profile=profile) if enable_ros else os.environ.copy()

        if config.get("cpu_performance_mode", False, profile=profile):
            Runner.ensure_cpu_performance_mode()

        cmd = [str(python_script)]
        if extra_args:
            cmd.extend(extra_args)

        console.print(f"[blue]Running: {' '.join(shlex.quote(c) for c in cmd)}[/blue]")

        try:
            subprocess.run(cmd, check=True, env=source_env)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"python.sh exited with code {e.returncode}")
        except KeyboardInterrupt:
            console.print("[yellow]Python process stopped by user.[/yellow]")
