import pytest

from cddalib.config import Env, current_env, init_app
from pathlib import Path


def test_all_items_are_placed_under_the_app_root_directory(tmpdir):
    root = Path(tmpdir)
    env = Env(root)
    assert root in env.install_folder.parents
    assert root in env.download_folder.parents
    assert root in env.backup_folder.parents
    assert root in env.current_install_data_file.parents
    assert root in env.builds_data_file.parents


def test_folders_are_created(tmpdir):
    env = Env(Path(tmpdir))
    env.create_folders()

    assert env.backup_folder.is_dir()
    assert env.download_folder.is_dir()
    assert env.install_folder.is_dir()


def test_current_env_proxy(tmpdir):
    Env.current_global = Env(Path(tmpdir))
    assert current_env.app_root == Path(tmpdir)


def test_init_app(tmpdir):
    root = Path(tmpdir) / 'app_root'
    assert not root.exists()
    init_app(root)

    assert current_env.backup_folder.is_dir()
    assert current_env.download_folder.is_dir()
    assert current_env.install_folder.is_dir()


def test_error_before_init_app():
    Env.current_global = None
    with pytest.raises(AttributeError):
        path = current_env.app_root
