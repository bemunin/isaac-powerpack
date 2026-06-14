"""ROS-related core logic.

Centralises ROS workspace setup, Docker image building, environment
sourcing, and container launching that was previously spread across
Initializer and Runner.
"""

import os
import shlex
import subprocess
from pathlib import Path

import click
from rich.console import Console

from .models.pow_config import PowConfig

console = Console()


class RosManager:
    """Manages all ROS-related operations for Isaac Powerpack."""

    def __init__(self, config: PowConfig | None = None):
        self._config = config or PowConfig()

    @property
    def config(self) -> PowConfig:
        return self._config

    # ── Environment sourcing ─────────────────────────────────────────────────

    @staticmethod
    def source_setup_file(
        file_path: Path,
        shell_type: str,
        env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Source a shell setup file and return the resulting environment variables."""
        safe_path = shlex.quote(str(file_path))
        command = [
            shell_type,
            "-c",
            f"source {safe_path} && env",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )

            new_env = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    new_env[key] = value

            return new_env

        except subprocess.CalledProcessError as e:
            raise click.ClickException(
                click.style(
                    f"Failed to source setup file {file_path}: {e.stderr}",
                    fg="red",
                )
            )

    @staticmethod
    def source_isaacsim_ros_workspace(config: PowConfig) -> dict:
        """Check and prepare ROS workspace environment variables."""
        ros_ws_path = config.ros_ws_path
        ros_distro = config.ros_distro

        shell_path = os.environ.get("SHELL", "")
        shell_type = Path(shell_path).name if shell_path else "bash"

        distro_local_setup = (
            ros_ws_path
            / "build_ws"
            / ros_distro
            / f"{ros_distro}_ws"
            / "install"
            / f"local_setup.{shell_type}"
        )
        isaac_sim_ros_setup = (
            ros_ws_path
            / "build_ws"
            / ros_distro
            / "isaac_sim_ros_ws"
            / "install"
            / f"local_setup.{shell_type}"
        )

        if not distro_local_setup.exists() or not isaac_sim_ros_setup.exists():
            raise click.ClickException(f"ROS setup files not found. Are you sure you ran `pow init` properly?")

        distro_env = RosManager.source_setup_file(distro_local_setup, shell_type, env=os.environ.copy())
        output_env = RosManager.source_setup_file(isaac_sim_ros_setup, shell_type, env=distro_env)

        return output_env

    # ── Workspace setup (from Initializer) ───────────────────────────────────

    def setup_ros_workspace(self, status_callback=None, ws_path: "Path | None" = None) -> dict:
        """Setup ROS workspace for Isaac Sim project.

        Args:
            ws_path: Explicit workspace path override.  When ``None`` the
                     path is read from ``self.config.ros_ws_path`` (i.e.
                     the ``isaacsim_ros_ws`` key in pow.toml).
        """
        ros_distro = self.config.ros_distro
        ubuntu_version = self.config.ubuntu_version
        clone_path = ws_path or self.config.ros_ws_path

        # Clone workspace if not already cloned
        if not (clone_path / ".git").exists():
            if status_callback:
                status_callback("cloning")
            subprocess.run(
                [
                    "git", "clone", "-b", "IsaacSim-5.1.0", "--quiet",
                    "https://github.com/isaac-sim/IsaacSim-ros_workspaces.git",
                    str(clone_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            if status_callback:
                status_callback("existed")

        # Build ROS workspace (skip if already built)
        ubuntu_major = ubuntu_version.split(".")[0]
        docker_image = f"isaac_sim_ros:ubuntu_{ubuntu_major}_{ros_distro}"

        distro_install_path = clone_path / "build_ws" / ros_distro / f"{ros_distro}_ws" / "install"
        if distro_install_path.exists():
            if status_callback:
                status_callback("built")
        else:
            if status_callback:
                status_callback("building")
            process = subprocess.Popen(
                ["./build_ros.sh", "-d", ros_distro, "-v", ubuntu_version],
                cwd=clone_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            output_lines: list[str] = []
            for line in process.stdout:
                stripped = line.strip()
                if stripped:
                    output_lines.append(stripped)
                    if status_callback:
                        status_callback(f"building:{stripped}")
            process.wait()

            # Fix build_ros.sh leaving dangling containers from `docker create --rm`
            cmd = [
                "docker", "ps", "-a", "-q",
                "--filter", f"ancestor={docker_image}",
                "--filter", "status=exited",
                "--filter", "status=created"  # Include created but never started
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            container_ids = result.stdout.strip().split()

            if container_ids:
                subprocess.run(["docker", "rm"] + container_ids)

            if process.returncode != 0:
                tail = "\n".join(output_lines[-30:])
                raise RuntimeError(
                    f"ROS build failed with exit code {process.returncode}\n"
                    f"--- Last lines of build output ---\n{tail}"
                )

        return {
            "status": "success",
            "ros_distro": ros_distro,
            "ubuntu_version": ubuntu_version,
            "path": str(clone_path),
        }

    @staticmethod
    def _detect_cuda_version() -> str | None:
        """Detect the host CUDA version from nvidia-smi.

        Returns the version string (e.g. ``"12.8"``) or ``None`` if
        ``nvidia-smi`` is not available or the version cannot be parsed.
        """
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "CUDA Version" in line:
                        # Line looks like: "| ... CUDA Version: 12.8  |"
                        parts = line.split("CUDA Version:")
                        if len(parts) > 1:
                            return parts[1].strip().rstrip("|").strip()
        except FileNotFoundError:
            pass
        return None

    def build_simros_image(self, status_callback=None, ws_path: "Path | None" = None) -> dict:
        """Build pow_simros_<distro> Docker image using Dockerfile.simros_<distro>.

        Skips the build if the image already exists locally.

        Args:
            ws_path: Explicit workspace path override.  When ``None`` the
                     path is read from ``self.config.ros_ws_path``.
        """
        ros_ws = ws_path or self.config.ros_ws_path
        ros_distro = self.config.ros_distro
        docker_image = f"pow_simros_{ros_distro}"
        distro_ws = ros_ws / f"{ros_distro}_ws"
        dockerfile_path = Path(__file__).parent.parent / "docker" / f"Dockerfile.simros_{ros_distro}"

        # Check if image already exists
        image_check = subprocess.run(
            ["docker", "image", "inspect", f"{docker_image}:latest"],
            capture_output=True,
        )
        if image_check.returncode == 0:
            if status_callback:
                status_callback("simros_built")
            return {"status": "existed", "image": docker_image}

        if status_callback:
            status_callback("simros_building")

        # Detect host CUDA version for PyTorch wheel selection
        # Fix CUDA version to 12.1 for pytorch compatibility both ubuntu 22.04 and 24.04 nvidia drivers
        cuda_version = "12.1" 
        console.print(f"[dim]Using  CUDA version:[/dim] [cyan]{cuda_version or 'None'}[/cyan]")

        build_cmd = [
            "docker", "build",
            "-f", str(dockerfile_path),
            "-t", docker_image,
            "--build-context", f"ros_ws={distro_ws}",
        ]

        if cuda_version:
            build_cmd.extend(["--build-arg", f"CUDA_VERSION={cuda_version}"])
            if status_callback:
                status_callback(f"simros_building:Using host CUDA {cuda_version} for PyTorch")

        build_cmd.append(".")

        process = subprocess.Popen(
            build_cmd,
            cwd=str(ros_ws),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines: list[str] = []
        for line in process.stdout:
            stripped = line.strip()
            if stripped:
                output_lines.append(stripped)
                if status_callback:
                    status_callback(f"simros_building:{stripped}")
        process.wait()

        if process.returncode != 0:
            tail = "\n".join(output_lines[-30:])
            raise RuntimeError(
                f"Docker build for {docker_image} failed with exit code {process.returncode}\n"
                f"--- Last lines of build output ---\n{tail}"
            )

        return {"status": "built", "image": docker_image}

    def build_custom_ros_image(self, status_callback=None) -> dict:
        """Build a custom ROS image layered on top of ``pow_simros_<distro>``.

        Builds the Dockerfile referenced by ``ros_dockerfile`` in pow.toml,
        tagging the result with ``ros_container_name``.  The custom Dockerfile is
        expected to start with ``FROM pow_simros_<distro>`` so it inherits the
        base image's WORKDIR and entrypoint.

        Returns ``{"status": "skipped"}`` when ``ros_dockerfile`` is empty.
        The build always runs (Docker layer caching keeps unchanged builds fast)
        so edits to the custom Dockerfile take effect on re-init.
        """
        ros_dockerfile = self.config.ros_dockerfile
        if not ros_dockerfile:
            return {"status": "skipped"}

        project_root = self.config.project_root
        if project_root is None:
            raise RuntimeError("Not initialized: pow.toml not found.")

        dockerfile_path = project_root / ros_dockerfile
        if not dockerfile_path.exists():
            raise RuntimeError(
                f"Custom ROS Dockerfile not found: {dockerfile_path}\n"
                f"Check the 'ros_dockerfile' path in pow.toml."
            )

        image = self.config.ros_container_name

        if status_callback:
            status_callback("custom_building")

        build_cmd = [
            "docker", "build",
            "-f", str(dockerfile_path),
            "-t", image,
            str(project_root),
        ]

        process = subprocess.Popen(
            build_cmd,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines: list[str] = []
        for line in process.stdout:
            stripped = line.strip()
            if stripped:
                output_lines.append(stripped)
                if status_callback:
                    status_callback(f"custom_building:{stripped}")
        process.wait()

        if process.returncode != 0:
            tail = "\n".join(output_lines[-30:])
            raise RuntimeError(
                f"Docker build for custom image '{image}' failed with exit code "
                f"{process.returncode}\n"
                f"--- Last lines of build output ---\n{tail}"
            )

        return {"status": "built", "image": image}

    # ── Container launching (from Runner) ────────────────────────────────────

    @staticmethod
    def _load_and_validate_config() -> tuple[PowConfig, str]:
        """Load config and return (config, docker_image) or raise."""
        config = PowConfig()
        if config.project_root is None:
            raise click.ClickException("Not initialized. Run `pow init` first.")

        enable_ros = config.get("enable_ros", False)
        if not enable_ros:
            raise click.ClickException(
                "ROS integration is disabled in pow.toml.\n"
                "Set 'enable_ros = true' under [sim] and re-run 'pow init' to enable it."
            )

        docker_image = config.ros_image_name

        image_check = subprocess.run(
            ["docker", "image", "inspect", f"{docker_image}:latest"],
            capture_output=True,
        )
        if image_check.returncode != 0:
            raise click.ClickException(
                f"Docker image '{docker_image}' not found.\n"
                "Run 'pow init' first to build the image."
            )

        return config, docker_image

    @staticmethod
    def _unlock_x11(verbose: bool = False) -> None:
        """Allow X11 access via xhost."""
        try:
            subprocess.run(["xhost", "+"], check=True, capture_output=True)
            if verbose:
                console.print("[green]X11 access control unlock (xhost +)[/green]")
        except FileNotFoundError:
            if verbose:
                console.print("[yellow]Warning: xhost command not found. GUI might not work.[/yellow]")
        except subprocess.CalledProcessError:
            if verbose:
                console.print("[red]Error: Failed to set xhost permissions.[/red]")

    @staticmethod
    def _is_container_running(container_name: str) -> bool:
        """Return True if the named container is currently running."""
        result = subprocess.run(
            ["docker", "container", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    @staticmethod
    def _attach_to_container(
        container_name: str,
        docker_image: str,
        extra_args: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        """Attach to an already-running container via ``docker exec``."""
        exec_cmd: list[str] = ["docker", "exec", "-it", container_name]
        exec_cmd.extend(["/ros_config/entrypoint.sh"] + (extra_args or ["/bin/bash"]))

        console.print(f"[dim]Starting container from image:[/dim] [cyan]{docker_image}[/cyan]")
        console.print(f"[green]Container '{container_name}' is already running. Attaching...[/green]")
        
        if verbose:
            console.print(f"[blue]Running: {' '.join(shlex.quote(c) for c in exec_cmd)}[/blue]")

        try:
            subprocess.run(exec_cmd, check=True, env=os.environ)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"Docker exec exited with code {e.returncode}")
        except KeyboardInterrupt:
            if verbose:
                console.print("[yellow]Detached from container.[/yellow]")

    @staticmethod
    def _start_new_container(
        config: PowConfig,
        docker_image: str,
        extra_args: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        """Create and start a new ``pow_simros`` container."""
        ros_distro = config.ros_distro
        ros_ws_path = config.ros_ws_path
        distro_ws = ros_ws_path / f"{ros_distro}_ws"
        container_name = config.ros_container_name

        uid = os.getuid()
        gid = os.getgid()

        host_home = os.path.expanduser("~")
        ros_config_dir = os.path.join(host_home, ".ros")

        cmd = [
            "docker", "run", "-it", "--rm", "--net=host",
            "--env", f"HOST_UID={uid}",
            "--env", f"HOST_GID={gid}",
            "--env", "DISPLAY",
            "--env", "ROS_DOMAIN_ID",
            "-v", f"{distro_ws}:/{ros_distro}_ws",
        ]

        if os.path.exists(ros_config_dir):
            cmd.extend(["-v", f"{ros_config_dir}:/home/hostuser/.ros"])

        # Mount project scripts folder into the container
        if config.project_root:
            scripts_dir = config.project_root / "scripts"
            if scripts_dir.exists():
                cmd.extend(["-v", f"{scripts_dir}:/home/hostuser/scripts"])

        cmd.extend(["--name", container_name, docker_image])
        cmd.extend(extra_args or ["/bin/bash"])

        # Remove any stale stopped/exited container with the same name
        # to prevent "name already in use" conflicts.
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
        )

        console.print(f"[dim]Starting container from image:[/dim] [cyan]{docker_image}[/cyan]")
        if verbose:
            console.print(f"[blue]Running: {' '.join(shlex.quote(c) for c in cmd)}[/blue]")

        try:
            subprocess.run(cmd, check=True, env=os.environ)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"Docker container exited with code {e.returncode}")
        except KeyboardInterrupt:
            if verbose:
                console.print("[yellow]Container stopped by user.[/yellow]")

    @staticmethod
    def run_simros_container(
        extra_args: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        """Launch the pow_simros Docker container.

        Reads ``enable_ros`` and ``ros_distro`` from pow.toml.
        If ROS is disabled the user is told how to enable it.

        Args:
            extra_args: Additional arguments forwarded to the container command.
            verbose: When True, print status feedback to the console.
        """
        config, docker_image = RosManager._load_and_validate_config()

        RosManager._unlock_x11(verbose=verbose)

        container_name = config.ros_container_name

        if RosManager._is_container_running(container_name):
            RosManager._attach_to_container(container_name, docker_image, extra_args, verbose=verbose)
        else:
            RosManager._start_new_container(config, docker_image, extra_args, verbose=verbose)
