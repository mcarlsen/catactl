import click
import psutil
import sys
import subprocess
from pathlib import Path
from . import ReleaseList, Release, switch_install, Backup, get_running_process
from .config import init_app, current_env as env


@click.group()
def catactl():
    app_root = Path.home() / 'AppData' / 'Local' / 'Cataclysm'
    init_app(app_root)


@catactl.group()
def show():
    """
    Shows the current state of affairs.
    """
    pass


@catactl.command()
def kill():
    """Terminates a running game process."""
    p = get_running_process()
    if p:
        print(f"INFO: Smashing {p}")
        p.kill()
        try:
            p.wait(timeout=5)
            print("INFO: Corpse pulped")
        except psutil.TimeoutExpired as e:
            print("ERROR: {e}")
            sys.exit(1)
    else:
        print("INFO: No game is running")


@show.command()
@click.option('--verbose', '-v', is_flag=True, help='Dump some process info')
def process(verbose):
    """Show process info for the currently running game"""
    p = get_running_process()
    if p:
        print(f"INFO: a game is running ({p.exe()})")
        if verbose:
            print(f"DEBUG: {p}")
            print(f"DEBUG: {p.cpu_times()}")
            print(f"DEBUG: {p.memory_info()}")
            print(f"DEBUG: {p.io_counters()}")
    else:
        print("INFO: no game is running")
        sys.exit(1)


@show.command()
@click.option('--cached', is_flag=True, help='Use the cached list. Do not download.')
@click.option('--stable', is_flag=True, help='Show only the latest stable release')
def builds(cached, stable):
    """
    Downloads and shows most recent build tags (most recent last)
    """
    if not cached:
        ReleaseList.update(only_latest_stable=stable)

    for build in reversed(ReleaseList.load()):
        print(f"{build.tag_name}")


@catactl.command()
@click.argument('tag')
@click.option('--cached', is_flag=True, help='Use only cached data. Do not download.')
@click.option('--force', is_flag=True, help='Reinstall if build is already installed (will keep the save).')
def install(tag, cached, force):
    """
    Downloads and installs the experimental build with the given TAG.

    It will become the version that `catactl run` starts.

    Use 'latest' as the TAG to install the most recent experimental build.

    Use 'stable' as the TAG to install the most recent stable release build.

    Try `catactl show builds` to show the list of release tags.
    """
    if get_running_process():
        print("ERROR: quit the game before installing a new version")
        sys.exit(1)

    if not cached:
        ReleaseList.update(only_latest_stable=(tag == 'stable'))
    builds = ReleaseList.load()

    if tag != 'latest':
        builds = [b for b in builds if b.tag_name == tag]

    if not builds:
        print(f"ERROR: No such build: {tag}")
        sys.exit(1)

    build = builds[0]
    if not build.download_target.exists():
        if cached:
            print(f"ERROR: Cannot install {tag} without downloading it first.")
            sys.exit(1)
        else:
            build.download(force=force)

    build.install(force=force)
    switch_install(build)


@catactl.command()
@click.option('--backup', is_flag=True, help='Backup the save before running')
@click.option('--label', help='Label the backup to make it easier to identify')
def run(backup, label):
    """
    Runs the most recently installed build.

    Use `catactl install TAG` to switch to another build
    """
    if get_running_process():
        print("ERROR: Already playing the game. Maybe try `catactl kill` to force quit the game.")
        sys.exit(1)

    build = Release.load(env.current_install_data_file)

    if backup:
        Backup.backup(build, label=label)

    build.run()


@catactl.command()
@click.option('--label', help='Label the backup to make it easier to identify')
def backup(label):
    """
    Backs up the save of the most recently installed build.
    """
    build = Release.load(env.current_install_data_file)
    Backup.backup(build, label=label)


@show.command()
def backups():
    """
    Shows backups - latest will be last.
    """
    for backup_id in Backup.get_list():
        print(backup_id)


@catactl.command()
@click.argument('backup_id')
def restore(backup_id):
    """
    Restores a backup into the most recently installed build.

    Use 'latest' as the BACKUP_ID to restore the most recent backup.

    Try `catactl show backups` to see the list of backups.
    """
    if get_running_process():
        print("ERROR: Quit the game before restoring a backup. Maybe try `catactl kill` to force quit the game.")
        sys.exit(1)

    backups = Backup.get_list()
    if not backups:
        print("ERROR: No backups found")
        sys.exit(1)

    if backup_id == 'latest':
        backup_id = Backup.get_list()[-1]

    build = Release.load(env.current_install_data_file)
    Backup.restore(build, backup_id)


@catactl.command()
def explore():
    """
    Opens the catactl application folder in a window
    """
    subprocess.Popen(['start', str(env.app_root)], shell=True)


if __name__ == '__main__':
    catactl()
