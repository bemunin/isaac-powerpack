import pytest
import tomlkit
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


    def test_reports_only_keys_that_moved(self, tmp_path):
        pow_toml = tmp_path / "pow.toml"
        pow_toml.write_text(
            '[sim]\nversion = "6.0.1"\nenable_ros = false\n'
            'isaacsim_ros_ws = "~/ws"\n'
        )

        changed = Initializer()._patch_pow_toml(
            pow_toml, enable_ros=True, isaacsim_ros_ws="~/ws", sim_version="6.0.1",
        )

        assert changed == {"enable_ros": (False, True)}

    def test_absent_key_reports_no_previous_value(self, tmp_path):
        pow_toml = tmp_path / "pow.toml"
        pow_toml.write_text('[sim]\nexts = ["mine"]\n')

        changed = Initializer()._patch_pow_toml(
            pow_toml, enable_ros=False, isaacsim_ros_ws="~/ws", sim_version="6.0.1",
        )

        assert changed["version"] == (None, "6.0.1")
        assert changed["enable_ros"] == (None, False)

    def test_no_write_when_nothing_changed(self, tmp_path):
        pow_toml = tmp_path / "pow.toml"
        original = (
            '# hand written\n[sim]\nversion   =   "6.0.1"\n'
            'enable_ros = true\nisaacsim_ros_ws = "~/ws"\n'
        )
        pow_toml.write_text(original)

        changed = Initializer()._patch_pow_toml(
            pow_toml, enable_ros=True, isaacsim_ros_ws="~/ws", sim_version="6.0.1",
        )

        assert changed == {}
        # Untouched down to the odd spacing: a re-run of init is a true no-op.
        assert pow_toml.read_text() == original

    def test_adds_sim_table_without_disturbing_the_rest(self, tmp_path):
        pow_toml = tmp_path / "pow.toml"
        pow_toml.write_text('[[profiles]]\nname = "mine"\ncpu_performance_mode = true\n')

        Initializer()._patch_pow_toml(
            pow_toml, enable_ros=True, isaacsim_ros_ws="~/ws", sim_version="5.1.0",
        )

        content = pow_toml.read_text()
        assert '[[profiles]]' in content
        assert 'name = "mine"' in content
        assert 'version = "5.1.0"' in content

    def test_invalid_toml_raises_and_leaves_file_alone(self, tmp_path):
        pow_toml = tmp_path / "pow.toml"
        broken = '[sim]\nversion = "6.0.1"\nbad = [\n'
        pow_toml.write_text(broken)

        with pytest.raises(tomlkit.exceptions.ParseError):
            Initializer()._patch_pow_toml(
                pow_toml, enable_ros=True, isaacsim_ros_ws="~/ws", sim_version="5.1.0",
            )

        assert pow_toml.read_text() == broken


class TestCreatePowToml:
    """`pow init` must update settings in pow.toml, never replace the file."""

    @pytest.fixture(autouse=True)
    def _no_git(self, mocker, tmp_path, monkeypatch):
        mocker.patch.object(Initializer, "init_git", return_value={"status": "Existed"})
        monkeypatch.chdir(tmp_path)
        self.pow_toml = tmp_path / "pow.toml"

    CUSTOM = """\
# my own notes
[sim]
version = "5.1.0"
enable_ros = false
exts = ["my.custom.ext"]
raw_args = ["--/renderer/x=1"]
ros_docker_image = "mine"

[[profiles]]
name = "mine"
extends = "default"
cpu_performance_mode = true
"""

    def test_override_keeps_every_other_setting(self):
        self.pow_toml.write_text(self.CUSTOM)

        result = Initializer().create_pow_toml(
            override=True, enable_ros=True, isaacsim_ros_ws="~/ws",
            sim_version="6.0.1",
        )

        assert result["status"] == "Updated"
        content = self.pow_toml.read_text()
        # The three settings init collected are the only ones that moved.
        assert 'version = "6.0.1"' in content
        assert "enable_ros = true" in content
        assert 'isaacsim_ros_ws = "~/ws"' in content
        # Everything the user wrote is still there, comment included.
        assert "# my own notes" in content
        assert 'exts = ["my.custom.ext"]' in content
        assert 'raw_args = ["--/renderer/x=1"]' in content
        assert 'ros_docker_image = "mine"' in content
        assert "[[profiles]]" in content
        assert 'name = "mine"' in content
        assert "cpu_performance_mode = true" in content

    def test_override_reports_what_changed(self):
        self.pow_toml.write_text(self.CUSTOM)

        result = Initializer().create_pow_toml(
            override=True, enable_ros=True, isaacsim_ros_ws="~/ws",
            sim_version="6.0.1",
        )

        assert result["changed"]["version"] == ("5.1.0", "6.0.1")
        assert result["changed"]["enable_ros"] == (False, True)

    def test_second_identical_run_changes_nothing(self):
        self.pow_toml.write_text(self.CUSTOM)
        kwargs = dict(
            override=True, enable_ros=True, isaacsim_ros_ws="~/ws",
            sim_version="6.0.1",
        )
        Initializer().create_pow_toml(**kwargs)
        after_first = self.pow_toml.read_text()

        result = Initializer().create_pow_toml(**kwargs)

        assert result["changed"] == {}
        assert self.pow_toml.read_text() == after_first

    def test_keep_leaves_the_file_byte_identical(self):
        self.pow_toml.write_text(self.CUSTOM)

        result = Initializer().create_pow_toml(
            override=False, enable_ros=True, isaacsim_ros_ws="~/ws",
            sim_version="6.0.1",
        )

        assert result["status"] == "Existed"
        assert self.pow_toml.read_text() == self.CUSTOM

    def test_creates_from_template_when_absent(self):
        result = Initializer().create_pow_toml(
            override=True, enable_ros=True, isaacsim_ros_ws="~/ws",
            sim_version="5.1.0",
        )

        assert result["status"] == "Created"
        content = self.pow_toml.read_text()
        assert 'version = "5.1.0"' in content
        assert "enable_ros = true" in content
        # Template defaults the user never saw a prompt for come along.
        assert 'ros_bridge = "jazzy"' in content

    def test_unparseable_file_is_reported_not_rewritten(self):
        broken = self.CUSTOM + "\nbad = [\n"
        self.pow_toml.write_text(broken)

        result = Initializer().create_pow_toml(
            override=True, enable_ros=True, isaacsim_ros_ws="~/ws",
            sim_version="6.0.1",
        )

        assert result["status"] == "Error"
        assert result["message"]
        assert self.pow_toml.read_text() == broken


class TestSetupVscodeConfigs:
    """The step copies the Isaac Sim configs but merges settings.json."""

    @pytest.fixture(autouse=True)
    def _project(self, tmp_path, monkeypatch):
        src = tmp_path / "isaacsim" / ".vscode"
        src.mkdir(parents=True)
        (src / "launch.json").write_text('{"configurations": [{"cwd": "${workspaceFolder}"}]}')
        (src / "tasks.json").write_text('{"tasks": []}')
        (src / "settings.json").write_text(
            '{"python.analysis.extraPaths": ["exts/isaacsim.core.api"]}'
        )

        project = tmp_path / "project"
        project.mkdir()
        (project / "_isaacsim").symlink_to(src.parent, target_is_directory=True)
        monkeypatch.chdir(project)
        self.settings = project / ".vscode" / "settings.json"

    @staticmethod
    def _statuses(result):
        return {res["file"]: res["status"] for res in result["results"]}

    def test_errors_without_a_linked_isaacsim(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert Initializer().setup_vscode_configs()["status"] == "Error"

    def test_copies_the_other_configs_and_creates_settings(self):
        result = Initializer().setup_vscode_configs()

        assert self._statuses(result) == {
            "launch.json": "Copied and patched",
            "tasks.json": "Copied and patched",
            "c_cpp_properties.json": "Not found in source",   # absent in Isaac Sim 6.0.1
            "settings.json": "Created",
        }
        assert "${workspaceFolder}" not in Path(".vscode/launch.json").read_text()
        assert '"_isaacsim/exts/isaacsim.core.api"' in self.settings.read_text()

    def test_a_users_settings_survive_a_re_run(self):
        Initializer().setup_vscode_configs()
        self.settings.write_text(
            self.settings.read_text().replace("{", '{\n    "files.autoSave": "afterDelay",', 1)
        )

        result = Initializer().setup_vscode_configs()

        assert self._statuses(result)["settings.json"] == "Already up to date"
        assert '"files.autoSave": "afterDelay"' in self.settings.read_text()
