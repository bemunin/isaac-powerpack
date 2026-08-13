import pytest
from pathlib import Path
from unittest.mock import MagicMock
from pow_cli.core.initializer import Initializer


@pytest.fixture
def mock_config(mocker):
    """Return a mock PowConfig object and inject it into every Initializer instance."""
    cfg = MagicMock()
    cfg.global_dir_name = ".pow"
    cfg.global_path = Path("/home/user/.pow")
    mocker.patch.object(Initializer, "config", new_callable=lambda: property(lambda self: cfg))
    return cfg


class TestInitializer:
    def test_get_config_path(self, mock_config):
        manager = Initializer()
        result = manager.get_config_path()
        assert result["global_dir_name"] == ".pow"
        assert result["global_path"] == Path("/home/user/.pow")

    def test_create_global_folder_new(self, mocker, mock_config):
        manager = Initializer()

        # Mock existence: global doesn't exist
        mocker.patch.object(Path, "exists", return_value=False)
        mock_mkdir = mocker.patch.object(Path, "mkdir")

        init_data = manager.create_global_folder()

        # Should call mkdir for global path and subfolders
        # global_path.mkdir + 4 subfolder.mkdir
        assert mock_mkdir.call_count == 5
        assert init_data["global_existed"] is False
        assert all(r["status"] == "Created" for r in init_data["results"])

    def test_create_global_folder_exists_skips_subfolders(self, mocker, mock_config):
        manager = Initializer()
        global_path = mock_config.global_path

        # Mock existence: global EXISTS, subfolders DON'T
        def side_effect(path_obj):
            if path_obj == global_path:
                return True
            return False

        mocker.patch.object(Path, "exists", side_effect=side_effect, autospec=True)
        mock_mkdir = mocker.patch.object(Path, "mkdir")

        init_data = manager.create_global_folder()

        # Should NOT call mkdir at all if global exists
        mock_mkdir.assert_not_called()
        assert init_data["global_existed"] is True
        assert all(r["status"] == "Skipped" for r in init_data["results"])

    def test_create_global_folder_exists_some_subfolders(self, mocker, mock_config):
        manager = Initializer()
        global_path = mock_config.global_path

        # Mock existence: global EXISTS, some subfolders EXIST
        def side_effect(path_obj):
            if path_obj == global_path:
                return True
            if "isaacsim" in str(path_obj):
                return True
            return False

        mocker.patch.object(Path, "exists", side_effect=side_effect, autospec=True)
        mock_mkdir = mocker.patch.object(Path, "mkdir")

        init_data = manager.create_global_folder()

        mock_mkdir.assert_not_called()
        assert init_data["global_existed"] is True

        isaacsim_res = next(r for r in init_data["results"] if "isaacsim" in r["path"])
        modules_res = next(r for r in init_data["results"] if "modules" in r["path"])

        assert isaacsim_res["status"] == "Existed"
        assert modules_res["status"] == "Skipped"


class TestLinkManagedIsaacsim:
    """`_isaacsim` must follow the version selected during `pow init`."""

    @pytest.fixture
    def project(self, tmp_path, mocker, monkeypatch):
        cfg = MagicMock()
        cfg.global_dir_name = ".pow"
        cfg.global_path = tmp_path / ".pow"
        mocker.patch.object(
            Initializer, "config", new_callable=lambda: property(lambda self: cfg)
        )
        for version in ("5.1.0", "6.0.1"):
            (cfg.global_path / "isaacsim" / version).mkdir(parents=True)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        return cfg, project_dir

    def test_creates_symlink_for_requested_version(self, project):
        cfg, project_dir = project

        result = Initializer().link_managed_isaacsim(version="6.0.1")

        assert result["status"] == "Created"
        assert (project_dir / "_isaacsim").resolve() == cfg.global_path / "isaacsim" / "6.0.1"

    def test_repoints_symlink_when_version_changes(self, project):
        cfg, project_dir = project
        initializer = Initializer()
        initializer.link_managed_isaacsim(version="5.1.0")

        result = initializer.link_managed_isaacsim(version="6.0.1")

        assert result["status"] == "Repointed"
        assert result["previous"].endswith("/5.1.0")
        assert (project_dir / "_isaacsim").resolve() == cfg.global_path / "isaacsim" / "6.0.1"

    def test_leaves_symlink_alone_when_already_correct(self, project):
        initializer = Initializer()
        initializer.link_managed_isaacsim(version="6.0.1")

        assert initializer.link_managed_isaacsim(version="6.0.1")["status"] == "Existed"

    def test_never_deletes_a_real_directory(self, project):
        _, project_dir = project
        real_dir = project_dir / "_isaacsim"
        real_dir.mkdir()
        (real_dir / "keep.txt").write_text("mine")

        result = Initializer().link_managed_isaacsim(version="6.0.1")

        assert result["status"] == "Error"
        assert "not a symlink" in result["message"]
        assert (real_dir / "keep.txt").read_text() == "mine"

    def test_reports_missing_install(self, project):
        result = Initializer().link_managed_isaacsim(version="5.0.0")

        assert result["status"] == "Error"
        assert "not found" in result["message"]


class TestPatchPowToml:
    def test_writes_selected_version(self, tmp_path):
        pow_toml = tmp_path / "pow.toml"
        pow_toml.write_text('[sim]\nversion = "6.0.1"\nenable_ros = false\n')

        Initializer()._patch_pow_toml(
            pow_toml, enable_ros=True, isaacsim_ros_ws="~/ws", sim_version="5.1.0",
        )

        content = pow_toml.read_text()
        assert 'version = "5.1.0"' in content
        assert "enable_ros = true" in content
        assert 'isaacsim_ros_ws = "~/ws"' in content
