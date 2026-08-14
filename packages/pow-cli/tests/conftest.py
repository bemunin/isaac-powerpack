import pytest

from pow_cli.core.models.pow_config import PowConfig


@pytest.fixture
def reset_config_singleton():
    """Reset the PowConfig singleton before and after tests."""
    PowConfig._instance = None
    yield
    PowConfig._instance = None
