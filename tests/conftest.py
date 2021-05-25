import pytest
from pathlib import Path
from catactl.config import Env, init_app, current_env


@pytest.fixture
def env(tmpdir) -> Env:
    """the 'env' fixture provides an environment rooted in a temporary folder"""
    init_app(app_root=Path(tmpdir))
    return current_env
