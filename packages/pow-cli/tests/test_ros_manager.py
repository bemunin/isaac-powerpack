import re

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from pow_cli.core.ros_manager import RosManager


def _make_config(
    *,
    ros_dockerfile="",
    ros_docker_image="pow_simros",
    ros_distro="jazzy",
    project_root=Path("/home/user/myproject"),
):
    """Build a MagicMock PowConfig with the ROS-related attributes set."""
    cfg = MagicMock()
    cfg.ros_dockerfile = ros_dockerfile
    cfg.ros_docker_image = ros_docker_image
    cfg.ros_distro = ros_distro
    cfg.project_root = project_root
    cfg.ros_ws_path = Path("/home/user/IsaacSim-ros_workspaces")
    cfg.ros_image_name = (
        ros_docker_image if ros_dockerfile else f"pow_simros_{ros_distro}"
    )
    # Mirror PowConfig.ros_container_name: image name sanitized for docker.
    cfg.ros_container_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", cfg.ros_image_name)
    return cfg


# ── build_custom_ros_image ──────────────────────────────────────────────────────

def test_build_custom_ros_image_skips_when_unset():
    """No ros_dockerfile → build is skipped and docker is never invoked."""
    cfg = _make_config(ros_dockerfile="")
    mgr = RosManager(config=cfg)

    result = mgr.build_custom_ros_image()
    assert result == {"status": "skipped"}


def test_build_custom_ros_image_missing_dockerfile_raises(mocker):
    """A configured but missing Dockerfile raises a clear error."""
    cfg = _make_config(ros_dockerfile="docker/Dockerfile.simros")
    mgr = RosManager(config=cfg)
    mocker.patch("pathlib.Path.exists", return_value=False)

    with pytest.raises(RuntimeError, match="Custom ROS Dockerfile not found"):
        mgr.build_custom_ros_image()


def test_build_custom_ros_image_builds_with_docker_image_name(mocker):
    """A configured Dockerfile builds and tags the image with ros_docker_image."""
    cfg = _make_config(
        ros_dockerfile="docker/Dockerfile.simros",
        ros_docker_image="my_robot_sim",
    )
    mgr = RosManager(config=cfg)
    mocker.patch("pathlib.Path.exists", return_value=True)

    fake_proc = MagicMock()
    fake_proc.stdout = iter(["building...\n"])
    fake_proc.returncode = 0
    popen = mocker.patch("subprocess.Popen", return_value=fake_proc)

    result = mgr.build_custom_ros_image()

    assert result == {"status": "built", "image": "my_robot_sim"}
    build_cmd = popen.call_args[0][0]
    assert build_cmd[:3] == ["docker", "build", "-f"]
    assert "-t" in build_cmd
    assert build_cmd[build_cmd.index("-t") + 1] == "my_robot_sim"
    assert "--no-cache" not in build_cmd


def test_build_custom_ros_image_no_cache(mocker):
    """no_cache=True adds --no-cache to the docker build command."""
    cfg = _make_config(
        ros_dockerfile="docker/Dockerfile.simros",
        ros_docker_image="my_robot_sim",
    )
    mgr = RosManager(config=cfg)
    mocker.patch("pathlib.Path.exists", return_value=True)

    fake_proc = MagicMock()
    fake_proc.stdout = iter(["building...\n"])
    fake_proc.returncode = 0
    popen = mocker.patch("subprocess.Popen", return_value=fake_proc)

    mgr.build_custom_ros_image(no_cache=True)

    build_cmd = popen.call_args[0][0]
    assert "--no-cache" in build_cmd
    # The build context (project root) must remain the last argument.
    assert build_cmd[-1] == str(cfg.project_root)


def test_build_custom_ros_image_nonzero_exit_raises(mocker):
    """A non-zero docker build exit code raises RuntimeError."""
    cfg = _make_config(ros_dockerfile="docker/Dockerfile.simros")
    mgr = RosManager(config=cfg)
    mocker.patch("pathlib.Path.exists", return_value=True)

    fake_proc = MagicMock()
    fake_proc.stdout = iter(["oops\n"])
    fake_proc.returncode = 1
    mocker.patch("subprocess.Popen", return_value=fake_proc)

    with pytest.raises(RuntimeError, match="failed with exit code"):
        mgr.build_custom_ros_image()


# ── image_exists ────────────────────────────────────────────────────────────────

def test_image_exists_appends_latest_for_untagged_reference(mocker):
    """An untagged image reference is inspected as <image>:latest."""
    run = mocker.patch("subprocess.run", return_value=MagicMock(returncode=0))

    assert RosManager.image_exists("pow_simros_jazzy") is True
    assert run.call_args[0][0] == [
        "docker", "image", "inspect", "pow_simros_jazzy:latest"
    ]


def test_image_exists_keeps_explicit_tag(mocker):
    """A tagged reference is inspected as-is (no extra :latest appended)."""
    run = mocker.patch("subprocess.run", return_value=MagicMock(returncode=1))

    assert RosManager.image_exists("ghcr.io/acme/robot:v1") is False
    assert run.call_args[0][0] == [
        "docker", "image", "inspect", "ghcr.io/acme/robot:v1"
    ]


# ── container launching uses ros_container_name ─────────────────────────────────

def test_start_new_container_uses_container_name(mocker):
    """_start_new_container names the container after the derived container name."""
    cfg = _make_config(
        ros_dockerfile="docker/Dockerfile.simros",
        ros_docker_image="my_robot_sim",
    )
    mocker.patch("os.getuid", return_value=1000)
    mocker.patch("os.getgid", return_value=1000)
    mocker.patch("os.path.exists", return_value=False)
    run = mocker.patch("subprocess.run")

    RosManager._start_new_container(cfg, "my_robot_sim")

    # The `docker rm -f <name>` cleanup call must target the configured name.
    rm_calls = [c for c in run.call_args_list if c[0][0][:3] == ["docker", "rm", "-f"]]
    assert rm_calls and rm_calls[0][0][0][3] == "my_robot_sim"

    # The `docker run ... --name <name>` call must use the configured name.
    run_calls = [
        c for c in run.call_args_list
        if c[0][0][:2] == ["docker", "run"] and "--name" in c[0][0]
    ]
    assert run_calls
    cmd = run_calls[0][0][0]
    assert cmd[cmd.index("--name") + 1] == "my_robot_sim"
