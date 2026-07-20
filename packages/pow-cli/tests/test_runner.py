import pytest
from pathlib import Path
from unittest.mock import MagicMock

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
