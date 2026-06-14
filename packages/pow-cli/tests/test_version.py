import pytest
from click.testing import CliRunner

from pow_cli.cli.main import pow_group


@pytest.mark.cli
def test_version_flag():
    result = CliRunner().invoke(pow_group, ["--version"])
    assert result.exit_code == 0
    assert "pow" in result.output
