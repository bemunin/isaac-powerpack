import pytest
from click.testing import CliRunner

from pow_cli.cli.sim import sim_cmd


@pytest.mark.cli
class TestSim:
    """`pow sim` forwards raw args and bridge selection to Runner.run_sim."""

    @pytest.fixture(autouse=True)
    def setup(self, mocker):
        self.runner = CliRunner()
        self.mock_run = mocker.patch("pow_cli.core.runner.Runner.run_sim")

    def _invoke(self, args):
        return self.runner.invoke(
            sim_cmd, args, env={"NO_COLOR": "1", "TERM": "dumb"}
        )

    def test_bare_sim_uses_defaults(self):
        result = self._invoke([])
        assert result.exit_code == 0
        self.mock_run.assert_called_once_with(
            version="5.1.0", ros_bridge="jazzy", extra_args=[]
        )

    def test_no_ros_disables_bridge(self):
        result = self._invoke(["--no-ros"])
        assert result.exit_code == 0
        assert self.mock_run.call_args.kwargs["ros_bridge"] is None

    def test_ros_selects_bridge_distro(self):
        result = self._invoke(["--ros", "humble"])
        assert result.exit_code == 0
        assert self.mock_run.call_args.kwargs["ros_bridge"] == "humble"

    def test_no_ros_wins_over_ros(self):
        result = self._invoke(["--ros", "humble", "--no-ros"])
        assert result.exit_code == 0
        assert self.mock_run.call_args.kwargs["ros_bridge"] is None

    def test_unsupported_bridge_rejected(self):
        result = self._invoke(["--ros", "iron"])
        assert result.exit_code == 2
        self.mock_run.assert_not_called()

    def test_version_option(self):
        result = self._invoke(["-v", "5.0.0"])
        assert result.exit_code == 0
        assert self.mock_run.call_args.kwargs["version"] == "5.0.0"

    def test_raw_args_after_double_dash(self):
        result = self._invoke(["--", "--no-window", "--/renderer/enabled=gpu"])
        assert result.exit_code == 0
        assert self.mock_run.call_args.kwargs["extra_args"] == [
            "--no-window",
            "--/renderer/enabled=gpu",
        ]

    def test_unknown_options_pass_through_without_double_dash(self):
        result = self._invoke(["--/renderer/enabled=gpu"])
        assert result.exit_code == 0
        assert self.mock_run.call_args.kwargs["extra_args"] == ["--/renderer/enabled=gpu"]

    def test_runs_outside_a_pow_project(self, tmp_path, monkeypatch):
        """No pow.toml above cwd must not produce a 'Not initialized' error."""
        monkeypatch.chdir(tmp_path)
        result = self._invoke([])
        assert result.exit_code == 0
        assert "Not initialized" not in result.output
