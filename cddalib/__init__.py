import traceback
import datetime
import dataclasses
import multiprocessing
import pathlib
import shutil
import sys
import tarfile
import io
import time
import requests
import json
import zipfile
import pickle
import subprocess
import contextlib
import os
from urllib.request import urlretrieve
from dataclasses import dataclass
from pathlib import Path
from typing import List
from .config import *


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
    def backup(build: Release, label: str = None):
        if label is None:
            label = build.tag_name
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        file_name = f'{timestamp}-{label}.tgz'
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
    def get_list():
        """
        Get list of backups, in chronologically ascending order
        """
        with chdir(backup_folder):
            return [backup.stem for backup in sorted(Path(".").glob('*.tgz'))]

    @staticmethod
    def show_list():
        """
        Print backups, in chronologically ascending order
        """
        for backup in Backup.get_list():
            print(backup)


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
