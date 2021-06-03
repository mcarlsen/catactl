import random
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
import psutil
from urllib.request import urlretrieve
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from .config import current_env as env


def chunked(lst, n):
    """Generator that yields n-sized chunks of the specified list"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_running_process() -> Optional[psutil.Process]:
    """
    Check if an instance of Cataclysm: Dark Days Ahead is already running.
    Will not detect instances that are not managed by catactl.

    :return: an object representing the running game; None if no game is running.
    """
    # for pid in psutil.pids():
    #     proc = psutil.Process(pid)
    for proc in psutil.process_iter():
        if 'cataclysm' in proc.name():
            if env.app_root in Path(proc.exe()).parents:
                return proc


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
        return env.download_folder / self.file_name

    @property
    def install_target(self):
        """Path to the install folder"""
        return env.install_folder / self.tag_name

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
    def load(target: Path) -> 'Release':
        with open(target, 'rb') as pkl:
            return pickle.load(pkl)

    def download(self, force=False):
        if self.download_target.exists() and not force:
            print(f"already downloaded {self.file_name}")
            return

        print(f"downloading {self.file_name}")
        urlretrieve(self.download_url, self.download_target)

    def install(self, force=False):
        """Install the release. Must be downloaded first"""
        if self.install_target.exists() and not force:
            print(f"already installed {self.tag_name}")
            return

        if not self.download_target.exists():
            print(f"ERROR: cannot install {self.tag_name}: not downloaded")
            sys.exit(1)

        if Path(self.file_name).suffix == ".zip":
            self.install_target.mkdir(exist_ok=True, parents=True)
            print(f"installing {self.file_name} to {self.install_target}")
            with zipfile.ZipFile(env.download_folder / self.file_name, 'r') as f:
                self.install_target.mkdir(exist_ok=True)
                f.extractall(self.install_target)
            self.dump(self.manifest_target)
        else:
            raise RuntimeError(f"don't know what to do with {self.file_name}")

    def run(self):
        """
        Launch the release. Must be downloaded and installed first.
        """
        if not self.install_target.exists():
            print(f"ERROR: Not installed: {self.tag_name}")
            sys.exit(1)

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
    """Context manager that chdirs to path on entry and chdirs back to the previous working directory on exit"""
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
    """
    Backup and restore.

    Uses multiprocessing to improve backup speed, especially
    on systems where storage read speed outstrips the compression speed of a single CPU core.
    The resulting archive is a plain TAR formatted file containing a number of .tgz files,
    each .tgz containing parts of the save.

    May keep all of the .tgz files in memory while compressing,
    so please don't let your saves approach 8-10x your available RAM in size :)

    Restores are single-threaded to prevent hypothetical race conditions involving directory creation,
    so they may be slower than backups.
    """
    @staticmethod
    def backup(build: Release, label: str = None) -> str:
        """
        Backs up the save of the given build.

        :param build: which installed build to back up from.
        :param label: a label for the backup. Default is to label it with the build tag.
        :return: the backup id (timestamp + label)
        """
        if label is None:
            label = build.tag_name
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        backup_id = f'{timestamp}-{label}'
        file_name = f'{backup_id}.{env.backup_suffix}'
        backup_target = env.backup_folder / file_name
        print(f"INFO: backing up {build.tag_name} to {timestamp}-{label}", end='', flush=True)

        t0 = time.monotonic()

        with chdir(build.install_target):
            files = [str(file) for file in Path("save").glob('**/*') if file.is_file()]

            # Try to send a similar amount of data to each process.
            # We could do a real algorithm but random shuffle should be good enough.
            cpu_count = multiprocessing.cpu_count() * 2
            chunk_size = 1 + int(len(files) / cpu_count)
            random.seed(2)  # fixed seed for deterministic output
            random.shuffle(files)
            chunks = chunked(files, chunk_size)

            part = 1
            errors = []
            in_bytes_sum = 0
            out_bytes_sum = 0

            # open a plain tar file for writing each compressed chunk
            with tarfile.open(backup_target, mode='w') as tar:

                def on_result(r):
                    """Writes a chunk of .tgz compressed files to the output tar"""
                    buffer, in_bytes, out_bytes = r
                    nonlocal tar, part, out_bytes_sum, in_bytes_sum

                    # output the compressed chunk
                    tarinfo = tarfile.TarInfo(name=f"part-{part}.tgz")
                    tarinfo.size = out_bytes
                    tarinfo.mtime = time.time()
                    tar.addfile(tarinfo, buffer)

                    # bean-counting
                    part += 1
                    in_bytes_sum += in_bytes
                    out_bytes_sum += out_bytes
                    print('.', end='', flush=True)

                def on_error(e):
                    """Records the failure to compress a chunk"""
                    nonlocal errors
                    traceback.print_exception(type(e), e, e.__traceback__)
                    errors.append(e)
                    print('X', end='', flush=True)

                # Compress one chunk of files per cpu
                with multiprocessing.Pool(cpu_count) as pool:
                    for chunk in chunks:
                        pool.apply_async(process_chunk, (chunk,), callback=on_result, error_callback=on_error)
                    pool.close()
                    pool.join()
                    print()

            if errors:
                print(f'ERROR: backup failed {len(errors)} errors: {errors}')
                backup_target.unlink(missing_ok=True)
                sys.exit(1)

            compression_rate = 1.0 - out_bytes_sum / in_bytes_sum
            print(
                f'INFO: compressed {in_bytes_sum / (1024*1024) :.1f} MiB '
                f'in {len(files)} files '
                f'to {out_bytes_sum / (1024*1024) :.1f} MiB '
                f'at {compression_rate*100 :.1f}% compression rate')

            t1 = time.monotonic()
            t = t1 - t0
            mib_per_second = in_bytes_sum / (1024*1024) / t
            files_per_second = len(files) / t
            print(f"INFO: backup took {t:.2f} seconds at {mib_per_second :.2f} MiB/s ({files_per_second :.0f} files/s)")

        return backup_id

    @staticmethod
    def restore(build: Release, backup: str):
        with chdir(env.backup_folder):
            save_dir = Path('save')
            tmp_dir = Path('save.tmp')
            with tarfile.open(f"{backup}.{env.backup_suffix}", mode='r|*') as tar:
                with chdir(build.install_target):
                    if tmp_dir.exists():
                        print("ERROR: Refusing to touch the mess that the previous restore left. "
                              "Maybe there was a power outage or you interrupted the process or something?")
                        print("INFO: You can try to manually salvage the situation by "
                              f"moving the 'save' folder out of the way and renaming the '{tmp_dir}' folder to 'save'.")
                        print("`catactl show directory` should open the location for you.")
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
                            print(f'INFO: the existing save should still exist')
                        sys.exit(1)

    @staticmethod
    def get_list():
        """
        Get list of backups, in chronologically ascending order
        """
        with chdir(env.backup_folder):
            return [backup.stem for backup in sorted(Path(".").glob(f'*.{env.backup_suffix}'))]


class DataclassEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "__json__"):
            return o.__json__()
        elif isinstance(o, pathlib.PurePath):
            return str(o)

        return super().default(o)


json_opts = {"indent": 4, "cls": DataclassEncoder}


class ReleaseList:
    @staticmethod
    def download() -> List[Release]:
        print('downloading release list')
        url = f'{env.repo_url}/releases'
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
        with open(env.builds_data_file, 'wb') as f:
            pickle.dump(releases, f)

    @staticmethod
    def load() -> List[Release]:
        with open(env.builds_data_file, 'rb') as f:
            return pickle.load(f)

    @staticmethod
    def exists() -> bool:
        return env.builds_data_file.exists()


def switch_install(release: Release):
    print(f"switching to {release.tag_name}")
    release.dump(env.current_install_data_file)
