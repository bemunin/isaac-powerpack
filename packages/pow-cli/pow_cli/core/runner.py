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

class Runner:
    """Handles execution of Isaac Sim and related tools."""

    @staticmethod
    def check_compatibility() -> dict:
        """Run the Isaac Sim built-in compatibility check.

        Uses the ``isaacsim`` CLI entry point installed via pip.
        Streams output to the terminal, waits for the process to finish,
        then reports passed/failed based on ``System checking result:``.

        Returns a dict with keys:
            status  – "passed" | "failed" | "aborted" | "not_found"
        """
        isaacsim_cmd = shutil.which("isaacsim")
        if isaacsim_cmd is None:
            return {
                "status": "not_found",
                "message": (
                    "The `isaacsim` command was not found. "
                    'Install it with: uv add "isaacsim[compatibility-check]" --index https://pypi.nvidia.com'
                ),
            }

        try:
            process = subprocess.Popen(
                [isaacsim_cmd, "isaacsim.exp.compatibility_check"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as e:
            return {"status": "failed", "message": f"Failed to launch compatibility check: {e}"}

        output_lines: list[str] = []
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
                output_lines.append(line)
            process.wait()
        except KeyboardInterrupt:
            process.kill()
            process.wait()
            return {"status": "aborted"}

        full_output = "".join(output_lines)
        if "System checking result: PASSED" in full_output:
            return {"status": "passed"}
        return {"status": "failed"}

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
            console.print("[yellow]Setting CPU to performance mode (requires sudo)...[/yellow]")
            try:
                subprocess.run(["sudo", "cpupower", "frequency-set", "-g", "performance"], check=True)
            except subprocess.CalledProcessError as e:
                console.print(f"[red]Failed to set CPU performance mode: {e}[/red]")

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
            console.print("[yellow]Setting CPU to performance mode (requires sudo)...[/yellow]")
            try:
                subprocess.run(["sudo", "cpupower", "frequency-set", "-g", "performance"], check=True)
            except subprocess.CalledProcessError as e:
                console.print(f"[red]Failed to set CPU performance mode: {e}[/red]")

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
