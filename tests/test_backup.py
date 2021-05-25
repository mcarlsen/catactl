import pytest
import tarfile
import shutil
from cddalib import Backup, process_chunk, Env, chdir, Release, ReleaseList, switch_install
from pathlib import Path
from typing import Tuple, List

num_subdirs_in_save = 7
num_files_per_subdir = 11


def generate_content(n) -> bytes:
    """contents of a savefile named n"""
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

    # mark the fake build as the build currently being played
    build = Release(
        tag_name='fake_build',
        file_name='fake.zip',
        download_url='fake',
        timestamp='1970-01-01T00:00:00Z',
    )
    switch_install(build)

    # the save folder structure
    save_folder = build_folder / 'save'
    save_folder.mkdir()
    byte_count = 0
    files = []
    for i in range(num_subdirs_in_save):
        subdir = save_folder / str(i)
        subdir.mkdir()
        for j in range(num_files_per_subdir):
            path = subdir / str(len(files))
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


@pytest.fixture
def release(env, build_folder) -> Release:
    """fixture with a Release object for the fake installed build"""
    return Release.load(env.current_install_data_file)


@pytest.fixture
def backup_id(env, release):
    """fixture with a backup of the release's save"""
    backup_id = Backup.backup(release)
    assert backup_id
    assert (env.backup_folder / f'{backup_id}.{env.backup_suffix}').exists()
    return backup_id


def assert_save_contents(release: Release):
    files = [f for f in release.save_target.glob('**/*') if f.is_file()]
    assert len(files) == num_subdirs_in_save * num_files_per_subdir

    for file in files:
        filename = str(file.parts[-1])
        dirname = str(file.parts[-2])

        expected_subdir = str(int(int(filename) / num_files_per_subdir))
        assert dirname == expected_subdir, f'file={dirname}/{filename}'

        expected_content = generate_content(filename)
        with open(file, 'rb') as f:
            assert f.read() == expected_content


def test_restore_with_no_save(backup_id, release: Release):
    shutil.rmtree(release.save_target)
    assert not release.save_target.exists()

    Backup.restore(release, backup_id)
    assert release.save_target.is_dir()
    assert_save_contents(release)


def test_restore_with_existing_save(backup_id, release: Release):
    # this extra file in the save must not exist after the restore
    extra_file = (release.save_target / 'extra')
    extra_file.touch()

    # this deleted file must exist after the restore
    deleted_file = (release.save_target / '0' / '0')
    deleted_file.unlink()

    # this changed file must have its content restored
    changed_file = (release.save_target / '0' / '1')
    with open(changed_file, 'w') as f:
        f.write('changed')

    # this moved file must be restored
    moved_file = (release.save_target / '0' / '2')
    moved_file.rename(release.save_target / '1' / '2')

    with pytest.raises(Exception):
        assert_save_contents(release)

    Backup.restore(release, backup_id)

    assert release.save_target.is_dir()
    assert not extra_file.exists()
    assert deleted_file.is_file()
    assert_save_contents(release)


def test_restore_with_error(backup_id, release: Release):
    # put save_target in a state where it provokes an error during restore
    # (the state being that current save_target is a file instead of a folder)
    shutil.rmtree(release.save_target)
    release.save_target.touch()

    # restore must bail out with not-ok system exit
    with pytest.raises(SystemExit) as e:
        Backup.restore(release, backup_id)
    assert e.value.code != 0

    # it leaves the horribly broken save in its horribly broken state
    assert release.save_target.is_file()

    # it does not leave a save.tmp folder
    assert not (release.install_target / 'save.tmp').exists()


def test_restore_with_previously_broken_restore_attempt(backup_id, release: Release):
    # place a save.tmp to indicate the previous restore went horribly wrong
    # (like a power outage or a kill -9 or something)
    (release.install_target / 'save.tmp').touch()

    # restore must bail out with not-ok system exit
    with pytest.raises(SystemExit) as e:
        Backup.restore(release, backup_id)
    assert e.value.code != 0

    # it leaves everything untouched
    assert (release.install_target / 'save.tmp').is_file()
    assert_save_contents(release)
