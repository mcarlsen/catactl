from pathlib import Path


class Env:
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
