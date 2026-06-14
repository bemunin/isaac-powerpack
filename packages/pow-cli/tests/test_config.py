import pytest
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from pathlib import Path
from pow_cli.core.models.pow_config import PowConfig

@pytest.fixture
def reset_config_singleton():
    """Reset the PowConfig singleton before and after tests."""
    PowConfig._instance = None
    yield
    PowConfig._instance = None

def test_singleton(tmp_path, monkeypatch, reset_config_singleton):
    """Test that PowConfig is a singleton."""
    root = tmp_path / "project"
    root.mkdir()
    pow_toml = root / "pow.toml"
    pow_toml.write_text("[sim]\nversion='5.1.0'")
    monkeypatch.chdir(root)
    
    c1 = PowConfig()
    c2 = PowConfig()
    assert c1 is c2

def test_find_project_root(tmp_path, monkeypatch, reset_config_singleton):
    """Test finding the project root with pow.toml using template structure."""
    root = tmp_path / "project"
    root.mkdir()
    pow_toml = root / "pow.toml"
    
    # Matching pow.template.toml structure
    content = """
[sim]
version = "5.1.0"
ext_folders = ["./exts"]
"""
    pow_toml.write_text(content)
    
    subdir = root / "subdir"
    subdir.mkdir()
    
    monkeypatch.chdir(subdir)
    
    config = PowConfig()
    assert config.project_root == root
    assert config.get("version") == "5.1.0"
    assert config.get("ext_folders") == ["./exts"]

def test_config_profile_merging(tmp_path, monkeypatch, reset_config_singleton):
    """Test the profile merging logic."""
    root = tmp_path / "project"
    root.mkdir()
    pow_toml = root / "pow.toml"
    
    # Data by pow.template.toml
    content = """
[sim]
version = "5.1.0"
headless = false
enable_ros = false

[[profiles]]
name = "perf"
headless = true
custom_val = "perf_mode"
"""
    pow_toml.write_text(content)
    monkeypatch.chdir(root)
    
    config = PowConfig()
    
    # 1. Base default profile (maps to 'sim')
    assert config.get("version") == "5.1.0"
    assert config.get("headless") is False
    assert config.get("enable_ros") is False 
    
    # 2. 'perf' profile merges [sim] + 'perf' profile
    # - headless: from 'perf' (True) overrides [sim] (False)
    # - version: from [sim] (5.1.0)
    perf_profile = config.get_profile("perf")
    assert perf_profile["headless"] is True
    assert perf_profile["enable_ros"] is False
    assert perf_profile["version"] == "5.1.0"
    assert perf_profile["custom_val"] == "perf_mode"
    
    # Test through get() helper
    assert config.get("headless", profile="perf") is True
    assert config.get("enable_ros", profile="perf") is False

def test_no_config_found(tmp_path, monkeypatch, reset_config_singleton):
    """Test behavior when no pow.toml is found."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    
    config = PowConfig()
    # instantiation should succeed to allow access to global paths
    assert config.global_dir_name == ".pow"

    # but accessing project data should raise the error
    with pytest.raises(RuntimeError, match="Project not initialized: pow.toml not found"):
        _ = config.data

def test_global_dir_name_default(tmp_path, monkeypatch, reset_config_singleton):
    """Test global_dir_name defaults to .pow when no pyproject.toml exists."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    config = PowConfig()
    assert config.global_dir_name == ".pow"

def test_global_dir_name_custom(tmp_path, monkeypatch, reset_config_singleton):
    """Test global_dir_name reads from pyproject.toml."""
    root = tmp_path / "project"
    root.mkdir()
    pyproject = root / "pyproject.toml"
    pyproject.write_text('[tool.pow-cli]\nglobal_dir_name = ".custom_pow"')
    monkeypatch.chdir(root)
    config = PowConfig()
    assert config.global_dir_name == ".custom_pow"

# ── extends feature tests ──────────────────────────────────────────────────────

def _make_config(tmp_path, monkeypatch, reset_config_singleton_fixture, content: str) -> PowConfig:
    """Helper: write pow.toml, chdir, and return a fresh PowConfig."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    reset_config_singleton_fixture  # already applied via fixture
    return PowConfig()


def test_profile_extends_another_profile(tmp_path, monkeypatch, reset_config_singleton):
    """A profile can extend another named profile (yolo → centerpose)."""
    content = """
[sim]
version = "5.1.0"
headless = false
exts = ["isaacsim.code_editor.vscode"]

[[profiles]]
name = "yolo"
headless = true
exts = ["oc.proj.yolo"]

[[profiles]]
name = "centerpose"
extends = "yolo"
cpu_performance_mode = true
exts.add = ["oc.proj.centerpose"]
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    profile = config.get_profile("centerpose")
    # Inherits headless=true from yolo
    assert profile["headless"] is True
    # version comes from [sim] via yolo (yolo has no extends → extends [sim])
    assert profile["version"] == "5.1.0"
    # cpu_performance_mode set in centerpose
    assert profile["cpu_performance_mode"] is True
    # exts: yolo's list + centerpose's .add list
    assert profile["exts"] == ["oc.proj.yolo", "oc.proj.centerpose"]


def test_profile_extends_default_explicit(tmp_path, monkeypatch, reset_config_singleton):
    """extends = 'default' falls back to [sim]."""
    content = """
[sim]
headless = false
exts = ["base_ext"]

[[profiles]]
name = "myprofile"
extends = "default"
headless = true
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    profile = config.get_profile("myprofile")
    assert profile["headless"] is True
    assert profile["exts"] == ["base_ext"]


def test_profile_no_extends_defaults_to_sim(tmp_path, monkeypatch, reset_config_singleton):
    """A profile without 'extends' inherits from [sim] only."""
    content = """
[sim]
headless = false
exts = ["base_ext"]

[[profiles]]
name = "slim"
headless = true
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    profile = config.get_profile("slim")
    assert profile["headless"] is True
    assert profile["exts"] == ["base_ext"]


def test_profile_extends_add_appends_list(tmp_path, monkeypatch, reset_config_singleton):
    """exts.add appends to the inherited list from [sim]."""
    content = """
[sim]
exts = ["base_ext"]

[[profiles]]
name = "extra"
"exts.add" = ["added_ext"]
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    profile = config.get_profile("extra")
    assert profile["exts"] == ["base_ext", "added_ext"]


def test_profile_extends_add_on_non_list_raises(tmp_path, monkeypatch, reset_config_singleton):
    """exts.add targeting a non-list raises ClickException at resolution time."""
    import click as _click
    content = """
[sim]
headless = false

[[profiles]]
name = "bad"
"headless.add" = [true]
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    with pytest.raises(_click.ClickException, match="not a list"):
        config.get_profile("bad")


def test_profile_extends_unknown_target_raises(tmp_path, monkeypatch, reset_config_singleton):
    """extends pointing to a non-existent profile raises ClickException."""
    import click as _click
    content = """
[sim]
headless = false

[[profiles]]
name = "child"
extends = "ghost"
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    with pytest.raises(_click.ClickException, match="not found"):
        config.get_profile("child")


def test_profile_extends_circular_raises(tmp_path, monkeypatch, reset_config_singleton):
    """Circular extends (a→b→a) raises ClickException."""
    import click as _click
    content = """
[sim]
headless = false

[[profiles]]
name = "a"
extends = "b"

[[profiles]]
name = "b"
extends = "a"
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    with pytest.raises(_click.ClickException, match="[Cc]ircular"):
        config.get_profile("a")


# ── custom ROS image config tests ───────────────────────────────────────────────

def test_ros_defaults(tmp_path, monkeypatch, reset_config_singleton):
    """ros_dockerfile/ros_container_name fall back to defaults when unset."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text("[sim]\nenable_ros = true\n")
    monkeypatch.chdir(root)
    config = PowConfig()

    assert config.ros_dockerfile == ""
    assert config.ros_container_name == "pow_simros"
    # No custom dockerfile → base image name
    assert config.ros_image_name == f"pow_simros_{config.ros_distro}"


def test_ros_custom_values(tmp_path, monkeypatch, reset_config_singleton):
    """ros_dockerfile/ros_container_name are read from [sim]."""
    content = """
[sim]
enable_ros = true
ros_dockerfile = "docker/Dockerfile.simros"
ros_container_name = "my_robot_sim"
"""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pow.toml").write_text(content)
    monkeypatch.chdir(root)
    config = PowConfig()

    assert config.ros_dockerfile == "docker/Dockerfile.simros"
    assert config.ros_container_name == "my_robot_sim"
    # Custom dockerfile set → image name is the container name
    assert config.ros_image_name == "my_robot_sim"


def test_ros_defaults_without_pow_toml(tmp_path, monkeypatch, reset_config_singleton):
    """ROS properties return defaults (no RuntimeError) when pow.toml is absent."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    config = PowConfig()

    assert config.ros_dockerfile == ""
    assert config.ros_container_name == "pow_simros"
