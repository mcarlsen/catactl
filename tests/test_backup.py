import pytest
import tarfile
from cddalib import Backup, process_chunk, Env, chdir
from pathlib import Path
from typing import Tuple, List

num_subdirs_in_save = 11
num_files_per_subdir = 13


def generate_content(n) -> bytes:
    return f'file {n} 😃'.encode('utf-8')


def test_finds_backups_returns_no_suffix(env: Env):
    # don't find these
    (env.backup_folder / f'test0.bogus').touch()
    (env.app_root / f'test0.{env.backup_suffix}').touch()

    # find these
    (env.backup_folder / f'test1.{env.backup_suffix}').touch()
    (env.backup_folder / f'test2.{env.backup_suffix}').touch()

    # the backup ids must have no file suffix
    assert Backup.get_list() == ['test1', 'test2']


def test_sorts_backups_asciibetically(env: Env):
    """TODO: this would require monkeypatching Path.glob or something"""


@pytest.fixture
def build_folder(env: Env):
    """fixture with a fake installed game with fake save files"""
    build_folder = env.install_folder / 'fake_build'
    build_folder.mkdir()

    # the save folder structure
    save_folder = build_folder / 'save'
    save_folder.mkdir()
    byte_count = 0
    files = []
    for i in range(num_subdirs_in_save):
        subdir = save_folder / str(i)
        subdir.mkdir()
        for j in range(num_files_per_subdir):
            path = subdir / str(j)
            with open(path, 'wb') as f:
                f.write(generate_content(len(files)))
                byte_count += f.tell()
            files.append(path)

    return build_folder, files, byte_count


def test_processes_files_and_returns_buffer(build_folder):
    build_folder, files_in_save, expect_in_bytes = build_folder
    buffer, in_bytes_count, out_bytes_count = process_chunk(files_in_save)

    assert buffer.tell() == 0  # buffer must be ready for reading from start
    assert len(buffer.getbuffer()) == out_bytes_count  # must count output bytes
    assert in_bytes_count == expect_in_bytes  # must count input bytes


def test_targzs_the_input_files(build_folder):
    build_folder, files_in_save, expect_in_bytes = build_folder
    buffer, in_bytes_count, out_bytes_count = process_chunk(files_in_save)

    # verify content
    fs_root = build_folder.parts[0]
    with tarfile.open(fileobj=buffer, mode='r:gz') as tar:
        for file, tarinfo, i in zip(files_in_save, tar.getmembers(), range(len(files_in_save))):
            assert Path(tarinfo.name) == file.relative_to(fs_root)
            assert tar.extractfile(tarinfo).read() == generate_content(i)
