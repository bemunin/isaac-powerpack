import click
import pytest
from pathlib import Path
from unittest.mock import MagicMock

import subprocess

from pow_cli.core import runner as runner_module
from pow_cli.core.runner import Runner

@pytest.fixture
def mock_config(mocker):
    cfg = MagicMock()
    cfg.global_dir_name = ".pow"
    cfg.global_path = Path("/home/user/.pow")
    cfg.project_root = Path("/home/user/myproject")
    
    def mock_get(key, default=None, profile="default"):
        data = {
            "version": "5.1.0",
            "ext_folders": ["./exts"],
            "headless": False,
            "exts": ["my.ext"],
            "raw_args": ["--arg1"],
            "enable_ros": False,
            "cpu_performance_mode": False
        }
        if profile == "perf":
            data.update({"headless": True, "cpu_performance_mode": True})
            
        return data.get(key, default)
        
    cfg.get.side_effect = mock_get
    mocker.patch("pow_cli.core.runner.PowConfig", return_value=cfg)
    return cfg

def test_build_launch_command_default(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    
    cmd = Runner.build_launch_command(mock_config, "default", ["--extra"])
    
    # Check that components correctly map to array Elements
    assert "/home/user/.pow/isaacsim/5.1.0/isaac-sim.sh" in cmd[0]
    assert "--ext-folder" in cmd
    # ext_folders are resolved to absolute paths (relative paths break when
    # pow run is invoked from a project subdirectory)
    assert str(Path("/home/user/myproject/exts")) in cmd
    assert "--enable" in cmd
    assert "my.ext" in cmd
    assert "--arg1" in cmd
    assert "--no-window" not in cmd
    assert "--extra" in cmd

def test_build_launch_command_perf(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    cmd = Runner.build_launch_command(mock_config, "perf")
    assert "--no-window" in cmd

def test_build_launch_command_skips_nonexisting_ext_folders(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.is_dir", return_value=False)
    cmd = Runner.build_launch_command(mock_config, "default")
    assert "--ext-folder" not in cmd
    assert not any("exts" in c for c in cmd)

def test_run_isaacsim_calls_subprocess(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("platform.machine", return_value="x86_64")
    mock_run = mocker.patch("subprocess.run")
    
    Runner.run_isaacsim("default")
    
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert "isaac-sim.sh" in args[0][0]
    assert kwargs.get("check") is True


# ── CPU performance mode ────────────────────────────────────────────────────────

@pytest.fixture
def fake_cpufreq(tmp_path, monkeypatch):
    """Point the governor lookup at a fake /sys tree."""
    monkeypatch.setattr(runner_module, "CPU_DEVICES_PATH", tmp_path)

    def set_governors(*governors: str) -> None:
        for index, governor in enumerate(governors):
            cpufreq = tmp_path / f"cpu{index}" / "cpufreq"
            cpufreq.mkdir(parents=True)
            (cpufreq / "scaling_governor").write_text(f"{governor}\n")

    return set_governors


@pytest.fixture
def sudo_calls(mocker):
    """Patch subprocess.run, recording argv and answering the sudo -n -v probe."""
    calls: list[list[str]] = []
    state = {"cached": False}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0 if (cmd[:3] != ["sudo", "-n", "-v"] or state["cached"]) else 1
        return result

    mocker.patch("subprocess.run", side_effect=fake_run)
    mocker.patch("shutil.which", return_value="/usr/bin/cpupower")
    return calls, state


CPUPOWER_CMD = ["sudo", "cpupower", "frequency-set", "-g", "performance"]


def test_cpu_performance_mode_skipped_when_already_set(fake_cpufreq, sudo_calls, capsys):
    """The whole point: no sudo process, so no password prompt on later runs."""
    fake_cpufreq("performance", "performance")
    calls, _ = sudo_calls

    Runner.ensure_cpu_performance_mode()

    assert calls == []
    assert "already in performance mode" in capsys.readouterr().out


def test_cpu_performance_mode_acts_when_only_some_cpus_are_set(fake_cpufreq, sudo_calls):
    fake_cpufreq("performance", "powersave")
    calls, _ = sudo_calls

    Runner.ensure_cpu_performance_mode()

    assert CPUPOWER_CMD in calls


def test_cpu_performance_mode_is_quiet_when_sudo_is_cached(fake_cpufreq, sudo_calls, capsys):
    fake_cpufreq("powersave")
    calls, state = sudo_calls
    state["cached"] = True

    Runner.ensure_cpu_performance_mode()

    assert calls == [["sudo", "-n", "-v"], CPUPOWER_CMD]
    assert "requires sudo" not in capsys.readouterr().out


def test_cpu_performance_mode_warns_before_prompting(fake_cpufreq, sudo_calls, capsys):
    fake_cpufreq("powersave")
    calls, _ = sudo_calls

    Runner.ensure_cpu_performance_mode()

    assert calls == [["sudo", "-n", "-v"], CPUPOWER_CMD]
    assert "requires sudo" in capsys.readouterr().out


def test_cpu_performance_mode_skipped_without_cpufreq(fake_cpufreq, sudo_calls, capsys):
    calls, _ = sudo_calls  # no governor files written

    Runner.ensure_cpu_performance_mode()

    assert calls == []
    assert "not available" in capsys.readouterr().out


def test_cpu_performance_mode_skipped_without_cpupower(fake_cpufreq, sudo_calls, mocker, capsys):
    fake_cpufreq("powersave")
    calls, _ = sudo_calls
    mocker.patch("shutil.which", return_value=None)

    Runner.ensure_cpu_performance_mode()

    assert calls == []
    assert "cpupower not found" in capsys.readouterr().out


def test_cpu_performance_mode_failure_does_not_raise(fake_cpufreq, mocker, capsys):
    fake_cpufreq("powersave")
    mocker.patch("shutil.which", return_value="/usr/bin/cpupower")

    def fake_run(cmd, **kwargs):
        if cmd == CPUPOWER_CMD:
            raise subprocess.CalledProcessError(1, cmd)
        result = MagicMock()
        result.returncode = 0
        return result

    mocker.patch("subprocess.run", side_effect=fake_run)

    Runner.ensure_cpu_performance_mode()

    assert "Failed to set CPU performance mode" in capsys.readouterr().out


def test_run_isaacsim_sets_performance_mode_for_perf_profile(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("platform.machine", return_value="x86_64")
    mocker.patch("subprocess.run")
    ensure = mocker.patch("pow_cli.core.runner.Runner.ensure_cpu_performance_mode")

    Runner.run_isaacsim("perf")

    ensure.assert_called_once_with()


def test_run_isaacsim_leaves_cpu_alone_by_default(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("platform.machine", return_value="x86_64")
    mocker.patch("subprocess.run")
    ensure = mocker.patch("pow_cli.core.runner.Runner.ensure_cpu_performance_mode")

    Runner.run_isaacsim("default")

    ensure.assert_not_called()


# ── run_sim (project-independent launcher) ──────────────────────────────────────
# These deliberately do NOT use the mock_config fixture: run_sim must never
# instantiate PowConfig, so patching it would hide a regression.

@pytest.fixture
def sim_env(mocker):
    """Patch everything run_sim touches, minus PowConfig."""
    mocker.patch("pathlib.Path.home", return_value=Path("/home/user"))
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("platform.machine", return_value="x86_64")
    return {
        "run": mocker.patch("subprocess.run"),
        "bridge_env": mocker.patch(
            "pow_cli.core.runner.RosManager.bridge_env", return_value={"ROS_DISTRO": "jazzy"}
        ),
    }


def test_run_sim_builds_command_from_defaults(sim_env):
    Runner.run_sim(extra_args=["--no-window"])

    args, kwargs = sim_env["run"].call_args
    assert args[0] == ["/home/user/.pow/isaacsim/5.1.0/isaac-sim.sh", "--no-window"]
    assert kwargs.get("check") is True


def test_run_sim_uses_jazzy_bridge_by_default(sim_env):
    Runner.run_sim()

    sim_env["bridge_env"].assert_called_once_with(
        Path("/home/user/.pow/isaacsim/5.1.0"), "jazzy"
    )
    assert sim_env["run"].call_args.kwargs["env"] == {"ROS_DISTRO": "jazzy"}


def test_run_sim_honors_requested_bridge(sim_env):
    Runner.run_sim(ros_bridge="humble")

    sim_env["bridge_env"].assert_called_once_with(
        Path("/home/user/.pow/isaacsim/5.1.0"), "humble"
    )


def test_run_sim_without_bridge_inherits_environment(sim_env, mocker):
    mocker.patch.dict("os.environ", {"MY_VAR": "1"}, clear=True)

    Runner.run_sim(ros_bridge=None)

    sim_env["bridge_env"].assert_not_called()
    assert sim_env["run"].call_args.kwargs["env"] == {"MY_VAR": "1"}


def test_run_sim_honors_version(sim_env):
    Runner.run_sim(version="5.0.0")

    assert sim_env["run"].call_args[0][0][0] == "/home/user/.pow/isaacsim/5.0.0/isaac-sim.sh"


def test_run_sim_missing_install_raises(mocker):
    mocker.patch("pathlib.Path.home", return_value=Path("/home/user"))
    mocker.patch("pathlib.Path.exists", return_value=False)
    mocker.patch("platform.machine", return_value="x86_64")
    run = mocker.patch("subprocess.run")

    with pytest.raises(click.ClickException, match="Isaac Sim not found at"):
        Runner.run_sim()

    run.assert_not_called()


def test_run_python_calls_subprocess(mock_config, mocker):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mock_run = mocker.patch("subprocess.run")

    Runner.run_python(extra_args=["my_script.py", "--arg1"])

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0][0].endswith("python.sh")
    assert "my_script.py" in args[0]
    assert "--arg1" in args[0]
    assert kwargs.get("check") is True
