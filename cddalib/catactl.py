import traceback
import datetime
import dataclasses
import multiprocessing
import pathlib
import shutil
import sys
import tarfile
import random
import io
import time
import requests
import json
import click
import zipfile
import pickle
import subprocess
import contextlib
import os
from urllib.request import urlretrieve
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

repo_url = 'https://api.github.com/repos/CleverRaven/Cataclysm-DDA'
work_folder = Path.home() / 'AppData' / 'Local' / 'Cataclysm'
download_folder = work_folder / 'builds'
install_folder = work_folder / 'installs'
backup_folder = work_folder / 'backups'
builds_data_file = download_folder / 'builds.pkl'
current_install_data_file = work_folder / 'current.pkl'


def chunked(lst, n):
    """Generator that yields n-sized chunks of the specified list"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


@dataclass
class Release:
    tag_name: str
    file_name: str
    download_url: str
    timestamp: str

    @staticmethod
    def parse(release, pattern='cdda-windows-tiles-x64'):
        """Parses the github release object"""
        assets = [asset for asset in release["assets"] if pattern in asset["name"]]
        try:
            asset = assets[0]
            return Release(
                tag_name=release["tag_name"],
                file_name=asset["name"],
                download_url=asset["browser_download_url"],
                timestamp=release["published_at"],
            )
        except Exception as e:
            # This release appears to be broken or useless
            print(f"WARNING: {e}")
            return None

    @property
    def download_target(self):
        """Path to the downloaded release archive"""
        return download_folder / self.file_name

    @property
    def install_target(self):
        """Path to the install folder"""
        return install_folder / self.tag_name

    @property
    def manifest_target(self):
        return self.install_target / 'catactl.manifest'

    @property
    def save_target(self):
        return self.install_target / 'save'

    def dump(self, target: Path):
        with open(target, 'wb') as pkl:
            pickle.dump(self, pkl)

    @staticmethod
    def load(target: Path):
        with open(target, 'rb') as pkl:
            return pickle.load(pkl)

    def download(self, force=False):
        if self.download_target.exists() and not force:
            print(f"already downloaded {self.file_name}")
            return

        print(f"downloading {self.file_name}")
        urlretrieve(self.download_url, self.download_target)

    def install(self, force=False):
        """Install the release. Will attempt to download the build if necessary"""
        if self.install_target.exists() and not force:
            print(f"already installed {self.tag_name}")
            return

        if not self.download_target.exists():
            print(f"ERROR: cannot install {self.tag_name}: not downloaded")
            sys.exit(1)

        if Path(self.file_name).suffix == ".zip":
            self.install_target.mkdir(exist_ok=True, parents=True)
            print(f"installing {self.file_name} to {self.install_target}")
            with zipfile.ZipFile(download_folder / self.file_name, 'r') as f:
                self.install_target.mkdir(exist_ok=True)
                f.extractall(self.install_target)
            self.dump(self.manifest_target)
        else:
            raise RuntimeError(f"don't know what to do with {self.file_name}")

    def run(self):
        """
        Launch the release. Will download and install if necessary.
        """
        self.install()

        cwd = str(self.install_target)
        exe = "cataclysm-tiles"
        print(f"running {exe} from {cwd}")
        p = subprocess.Popen([exe], shell=True, cwd=str(cwd))
        sys.exit(0)

    def __json__(self):
        n = {"__dataclass__": self.__class__.__name__}
        d = dataclasses.asdict(self)
        return {**n, **d}


@contextlib.contextmanager
def chdir(path: Path = None):
    cwd = os.getcwd()
    try:
        if path is not None:
            os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


def process_chunk(files: List[str]):
    in_bytes = 0
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for path in files:
            tarinfo = tar.gettarinfo(path)
            in_bytes += tarinfo.size
            with open(path, 'rb') as f:
                tar.addfile(tarinfo, f)
    out_bytes = buffer.tell()
    buffer.seek(0)
    return buffer, in_bytes, out_bytes


class Backup:
    @staticmethod
    def backup(build: Release):
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        file_name = f'{timestamp}-{build.tag_name}.tgz'
        backup_target = backup_folder / file_name
        print(f"backing up {build.install_target / 'save'} to {backup_target}")

        t0 = time.monotonic()

        with chdir(build.install_target):
            files = [str(file) for file in Path("save").glob('**/*') if file.is_file()]

            # random.shuffle(files)
            cpu_count = multiprocessing.cpu_count() * 2
            chunk_size = 1 + int(len(files) / cpu_count)
            chunks = chunked(files, chunk_size)

            t1 = time.monotonic()

            part = 1
            errors = []
            in_bytes_sum = 0
            out_bytes_sum = 0

            with tarfile.open(backup_target, mode='w') as tar:
                def on_result(r):
                    buffer, in_bytes, out_bytes = r
                    nonlocal tar, part, out_bytes_sum, in_bytes_sum

                    # output
                    tarinfo = tarfile.TarInfo(name=f"part-{part}.tgz")
                    tarinfo.size = out_bytes
                    tarinfo.mtime = time.time()
                    tar.addfile(tarinfo, buffer)

                    # bean-counting
                    part += 1
                    in_bytes_sum += in_bytes
                    out_bytes_sum += out_bytes

                def on_error(e):
                    nonlocal errors
                    traceback.print_exception(type(e), e, e.__traceback__)
                    errors.append(e)

                with multiprocessing.Pool(cpu_count) as pool:
                    for chunk in chunks:
                        pool.apply_async(process_chunk, (chunk,), callback=on_result, error_callback=on_error)
                    pool.close()
                    pool.join()

                if errors:
                    print(f'ERROR: backup failed {len(errors)} errors: {errors}')
                    backup_target.unlink(missing_ok=True)
                    sys.exit(1)

                compression_rate = 1.0 - out_bytes_sum / in_bytes_sum
                print(
                    f'INFO: compressed {in_bytes_sum} bytes '
                    f'in {len(files)} files '
                    f'to {out_bytes_sum} bytes '
                    f'at {compression_rate*100:.1f}% compression rate')

            t2 = time.monotonic()

        print(f"backup took {t2-t0:.2f} seconds")

    @staticmethod
    def restore(build: Release, backup: str):
        with chdir(backup_folder):
            save_dir = Path('save')
            tmp_dir = Path('save.tmp')
            with tarfile.open(f"{backup}.tgz", mode='r|*') as tar:
                with chdir(build.install_target):
                    if tmp_dir.exists():
                        print("ERROR: Refusing to touch the mess that the previous restore left. Yikes!")
                        print(f"ERROR: You can try to manually salvage the situation by renaming the '{tmp_dir}' folder to 'save'")
                        sys.exit(1)

                    # stash existing save
                    if save_dir.exists():
                        save_dir.rename(tmp_dir)

                    try:
                        for part in tar:
                            reader = tar.extractfile(part)
                            with tarfile.open(fileobj=reader) as parttar:
                                parttar.extractall('.')

                        # restore seems ok. we can remove the stashed save
                        if tmp_dir.exists():
                            shutil.rmtree(tmp_dir)

                    except Exception as e:
                        print(f'ERROR: {e}')
                        # try to restore the stashed save
                        if tmp_dir.exists():
                            if save_dir.exists():
                                shutil.rmtree(save_dir)
                            tmp_dir.rename(save_dir)
                        sys.exit(1)

    @staticmethod
    def list():
        with chdir(backup_folder):
            for backup in sorted(Path(".").glob('*.tgz')):
                print(backup.stem, backup.stat().st_size)


class DataclassEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "__json__"):
            return o.__json__()
        elif isinstance(o, pathlib.PurePath):
            return str(o)

        return super().default(o)


json_opts = {"indent": 4, "cls": DataclassEncoder}


def init():
    download_folder.mkdir(exist_ok=True, parents=True)
    install_folder.mkdir(exist_ok=True, parents=True)
    backup_folder.mkdir(exist_ok=True, parents=True)


class ReleaseList:
    @staticmethod
    def download() -> List[Release]:
        print('downloading release list')
        url = f'{repo_url}/releases'
        releases = requests.get(url).json()
        releases = [Release.parse(r) for r in releases]
        releases = [r for r in releases if r]
        return releases

    @staticmethod
    def update():
        releases = ReleaseList.download()
        ReleaseList.dump(releases)

    @staticmethod
    def dump(releases: List[Release]):
        with open(builds_data_file, 'wb') as f:
            pickle.dump(releases, f)

    @staticmethod
    def load() -> List[Release]:
        with open(builds_data_file, 'rb') as f:
            return pickle.load(f)

    @staticmethod
    def exists() -> bool:
        return builds_data_file.exists()


def switch_install(release: Release):
    print(f"switching to {release.tag_name}")
    release.dump(current_install_data_file)


@click.group()
def catactl():
    init()


@catactl.group()
def show():
    """
    Show the current state of affairs
    """
    pass


@show.command()
@click.option('--cached', is_flag=True, help='Use the cached list. Do not download.')
def builds(cached):
    """
    Downloads and shows most recent build tags (most recent last)
    """
    if not cached:
        ReleaseList.update()

    for build in reversed(ReleaseList.load()):
        print(f"{build.tag_name} (timestamp = {build.timestamp})")


@catactl.command()
@click.argument('tag')
@click.option('--cached', is_flag=True, help='Use only cached data. Do not download.')
@click.option('--force', is_flag=True, help='Reinstall if build is already installed (will keep the save).')
def install(tag, cached, force):
    """
    Downloads and installs the experimental build with the given TAG.

    It will become the version that `catactl run` starts.

    Use 'latest' as the TAG to install the most recent experimental build.

    Try `catactl builds` to show the list of release tags.
    """
    if not cached:
        ReleaseList.update()
    builds = ReleaseList.load()

    if tag != 'latest':
        builds = [b for b in builds if b.tag_name == tag]

    if not builds:
        print(f"ERROR: No such build: {tag}")
        sys.exit(1)

    build = builds[0]
    if cached and not build.download_target.exists():
        print(f"ERROR: Build not cached. Cannot install.")
        sys.exit(1)
    else:
        build.install(force=force)

    switch_install(build)


@catactl.command()
@click.option('--backup', is_flag=True, help='Backup the save before running')
def run(backup):
    """
    Run the most recently installed build.

    Use `catactl install TAG` to switch to another build
    """
    build = Release.load(current_install_data_file)

    if backup:
        Backup.backup(build)

    build.run()


@catactl.command()
def backup():
    """
    Backup the save of the most recently installed build.
    """
    build = Release.load(current_install_data_file)
    Backup.backup(build)


@show.command()
def backups():
    """
    Shows the list of backups.
    """
    Backup.list()


@catactl.command()
@click.argument('backup')
def restore(backup):
    """
    Restores the BACKUP into the most recently installed build.

    Use 'latest' as the BACKUP to restore the most recent backup.

    Try `catactl show backups` to see the list of backups.
    """
    build = Release.load(current_install_data_file)
    Backup.restore(build, backup)


@show.command()
def directory():
    """
    Open a window with the current install directory.
    """
    build = Release.load(current_install_data_file)
    subprocess.Popen(['start', str(build.install_target)], shell=True)


if __name__ == '__main__':
    catactl()