import dataclasses
import multiprocessing
import pathlib
import tarfile
import random
import io
import time
import requests
import json
from urllib.request import urlretrieve
from dataclasses import dataclass
from pathlib import Path

repo_url = 'https://api.github.com/repos/CleverRaven/Cataclysm-DDA'


def process_chunk(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for path in files:
            tarinfo = tar.gettarinfo(path)
            with open(path, 'rb') as f:
                tar.addfile(tarinfo, f)
    return buffer


def backup():
    t0 = time.monotonic()

    bytes_sum = 0
    cpu_count = multiprocessing.cpu_count() * 1
    files = [file for file in root_dir.glob('**/*') if file.is_file()]
    random.shuffle(files)

    def chunked(lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    chunk_size = 1 + int(len(files) / cpu_count)
    chunks = list(chunked(files, chunk_size))

    t1 = time.monotonic()

    with multiprocessing.Pool(cpu_count) as pool:
        r = pool.map(process_chunk, chunks)
        print([len(buf.getvalue()) for buf in r])

    t2 = time.monotonic()

    print(t2-t0, t1-t0, t2-t1)


@dataclass
class Release:
    tag_name: str
    file_name: Path
    download_url: str
    timestamp: str

    @staticmethod
    def parse(release, pattern='cdda-windows-tiles-x64'):
        assets = [asset for asset in release["assets"] if pattern in asset["name"]]
        try:
            asset = assets[0]
            return Release(
                tag_name=release["tag_name"],
                file_name=Path(asset["name"]),
                download_url=asset["browser_download_url"],
                timestamp=release["published_at"],
            )
        except Exception as e:
            print(e)
            return None

    def download(self, download_folder=Path("downloads")):
        print(f"downloading {self.file_name}")
        urlretrieve(self.download_url, download_folder / self.file_name)

    def unpack(self, download_folder=Path("downloads"), install_folder=Path("installs")):
        if self.file_name.suffix == ".zip":
            print(f"unpacking {self.file_name}")
            import zipfile
            with zipfile.ZipFile(download_folder / self.file_name, 'r') as f:
                target_folder = install_folder / self.tag_name
                target_folder.mkdir(exist_ok=True)
                f.extractall(target_folder)
        else:
            raise RuntimeError(f"don't know what to do with {self.file_name}")

    def run(self, install_folder=Path("installs")):
        import subprocess
        import sys

        cwd = (install_folder / self.tag_name).absolute()
        exe = "cataclysm-tiles"
        print(f"running {exe} in {cwd}")
        p = subprocess.Popen([str(exe)], shell=True, cwd=str(cwd))
        print("done")
        sys.exit(0)

    def __json__(self):
        n = {"__dataclass__": self.__class__.__name__}
        d = dataclasses.asdict(self)
        return {**n, **d}


class DataclassEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "__json__"):
            return o.__json__()
        elif isinstance(o, pathlib.PurePath):
            return str(o)

        return super().default(o)


json_opts = {"indent": 4, "cls": DataclassEncoder}


def main():

    url = f'{repo_url}/releases'
    releases = requests.get(url).json()
    releases = [Release.parse(r) for r in releases]
    releases = [r for r in releases if r]
    print(json.dumps(releases, **json_opts))

    releases[0].download()
    releases[0].unpack()
    releases[0].run()


if __name__ == '__main__':
    main()
