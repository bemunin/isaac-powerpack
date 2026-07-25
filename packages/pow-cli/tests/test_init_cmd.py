import pytest
from click.testing import CliRunner

from pow_cli.cli.init import init_cmd

@pytest.mark.cli
class TestInitCmd:
    @pytest.fixture(autouse=True)
    def mock_manager_methods(self, mocker):
        """Mock common Initializer methods used by init_cmd to avoid side effects."""
        self.mock_create_global = mocker.patch(
            "pow_cli.core.initializer.Initializer.create_global_folder",
            return_value={"global_existed": False, "results": []}
        )
        self.mock_download = mocker.patch(
            "pow_cli.core.initializer.Initializer.download_isaacsim",
            return_value={"status": "Already installed", "path": "/tmp/isaacsim"}
        )
        self.mock_fix_cache = mocker.patch(
            "pow_cli.core.initializer.Initializer.fix_asset_browser_cache",
            return_value=True
        )
        self.mock_setup_ros = mocker.patch(
            "pow_cli.core.ros_manager.RosManager.setup_ros_workspace",
            return_value={
                "status": "success",
                "ros_distro": "jazzy",
                "ubuntu_version": "24.04",
                "path": "/tmp/.pow/sim-ros"
            }
        )
        self.mock_setup_project = mocker.patch(
            "pow_cli.core.initializer.Initializer.setup_project_structure",
            return_value={"results": []}
        )
        self.mock_read_config = mocker.patch("pow_cli.core.initializer.Initializer.read_config")
        self.mock_create_pow_toml = mocker.patch(
            "pow_cli.core.initializer.Initializer.create_pow_toml",
            return_value={"status": "Created", "path": "pow.toml"}
        )
        self.mock_sleep = mocker.patch("time.sleep")
        self.runner = CliRunner()


    def test_init_cmd_step_1_output(self):
        result = self.runner.invoke(init_cmd, input="n\nn\n", env={"NO_COLOR": "1", "TERM": "dumb"}) 
        assert result.exit_code == 0
        assert "[1/10] 🔧 Config:" in result.output
        assert "Using global directory" in result.output

    def test_init_cmd_missing_pyproject_toml(self, mocker):
        mocker.patch("pathlib.Path.exists", return_value=False)
        result = self.runner.invoke(init_cmd, env={"NO_COLOR": "1", "TERM": "dumb"})
        assert "pyproject.toml not found" in result.output
        assert result.exit_code == 0

    def test_init_cmd_accepts_existing_global_folder(self):
        self.mock_create_global.return_value = {
            "global_existed": True,
            "results": [{"path": ".pow/isaacsim", "status": "Existed"}]
        }
        result = self.runner.invoke(init_cmd, input="n\nn\n", env={"NO_COLOR": "1", "TERM": "dumb"})
        assert result.exit_code == 0
        assert "already exists" in result.output

    def test_init_cmd_asset_browser_fix_output(self):
        self.mock_create_global.return_value = {"global_existed": True, "results": []}
        result = self.runner.invoke(init_cmd, input="n\nn\n", env={"NO_COLOR": "1", "TERM": "dumb"})
        assert "Created missing cache file." in result.output

    def test_init_cmd_asset_browser_already_fixed_output(self):
        self.mock_create_global.return_value = {"global_existed": True, "results": []}
        self.mock_fix_cache.return_value = False
        result = self.runner.invoke(init_cmd, input="n\nn\n", env={"NO_COLOR": "1", "TERM": "dumb"})
        assert "Cache file already exists." in result.output

    def test_init_cmd_ros_integration_output(self, mocker):
        self.mock_create_global.return_value = {"global_existed": True, "results": []}
        mocker.patch("pow_cli.cli.init.Confirm.ask", return_value=True)
        mocker.patch(
            "pow_cli.cli.init.ask_path", return_value="~/IsaacSim-ros_workspaces"
        )
        mocker.patch(
            "pow_cli.core.ros_manager.RosManager.build_simros_image",
            return_value={"status": "existed", "image": "pow_simros_jazzy"},
        )
        mocker.patch(
            "pow_cli.core.ros_manager.RosManager.build_custom_ros_image",
            return_value={"status": "skipped"},
        )
        mocker.patch(
            "pow_cli.core.initializer.Initializer.link_managed_isaacsim",
            return_value={"status": "Existed", "path": "_isaacsim"},
        )
        mocker.patch(
            "pow_cli.core.initializer.Initializer.setup_vscode_configs",
            return_value={"status": "Success", "results": []},
        )
        mocker.patch(
            "pow_cli.core.initializer.Initializer.setup_omniverse_user_home_alias",
            return_value={"status": "exists", "path": "omniverse.toml"},
        )

        # Force Path("pow.toml").exists() to be False so we skip the first Confirm.
        def mock_exists(path_obj, *args, **kwargs):
            return str(path_obj) == "pyproject.toml"
        mocker.patch("pathlib.Path.exists", side_effect=mock_exists, autospec=True)

        result = self.runner.invoke(init_cmd, env={"NO_COLOR": "1", "TERM": "dumb"})
        assert result.exit_code == 0
        assert "ROS bridge:" in result.output

    def test_init_cmd_ros_skipped_output(self):
        self.mock_create_global.return_value = {"global_existed": True, "results": []}
        # Answer 'n' to override config, 'n' to ROS integration
        result = self.runner.invoke(init_cmd, input="n\nn\n", env={"NO_COLOR": "1", "TERM": "dumb"})
        assert "Skipping ROS integration." in result.output
