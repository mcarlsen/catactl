from pathlib import Path as _Path


repo_url = 'https://api.github.com/repos/CleverRaven/Cataclysm-DDA'
work_folder = _Path.home() / 'AppData' / 'Local' / 'Cataclysm'
download_folder = work_folder / 'builds'
install_folder = work_folder / 'installs'
backup_folder = work_folder / 'backups'
builds_data_file = download_folder / 'builds.pkl'
current_install_data_file = work_folder / 'current.pkl'
backup_suffix = 'zar'
