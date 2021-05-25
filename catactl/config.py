from pathlib import Path
from typing import Optional
__all__ = ['Env', 'current_env', 'init_app']


class Env:
    current_global: Optional['Env'] = None

    def __init__(self, app_root: Path):
        self.repo_url = 'https://api.github.com/repos/CleverRaven/Cataclysm-DDA'
        self.app_root = app_root
        self.download_folder = self.app_root / 'builds'
        self.install_folder = self.app_root / 'installs'
        self.backup_folder = self.app_root / 'backups'
        self.builds_data_file = self.download_folder / 'builds.pkl'
        self.current_install_data_file = self.app_root / 'current.pkl'
        self.backup_suffix = 'zar'

    def create_folders(self):
        """Ensures that the expected directory structure exists"""
        self.download_folder.mkdir(exist_ok=True, parents=True)
        self.install_folder.mkdir(exist_ok=True, parents=True)
        self.backup_folder.mkdir(exist_ok=True, parents=True)


class _EnvProxy:
    def __getattr__(self, attr):
        if Env.current_global is None:
            raise AttributeError("Environment not configured. Must call init_app before.")
        return getattr(Env.current_global, attr)


# Proxy object that forwards all attribute accesses to the Env.current_global object
current_env: Env = _EnvProxy()


def init_app(app_root: Path):
    """
    You must call this before you can access the global current_env object.

    Initializes the global configuration object and causes app_root and expected subdirectories to exist.
    """
    Env.current_global = Env(app_root)
    current_env.create_folders()
