import pytest
from pathlib import Path
from cddalib import Env, init_env


@pytest.fixture
def env(tmpdir) -> Env:
    """the 'env' fixture provides an environment rooted in a temporary folder"""
    root = Path(tmpdir)
    return init_env(root)
