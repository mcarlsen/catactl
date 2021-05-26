import click
import sys
import subprocess
from pathlib import Path
from . import ReleaseList, Release, switch_install, Backup
from .config import init_app, current_env as env


@click.group()
def catactl():
    app_root = Path.home() / 'AppData' / 'Local' / 'Cataclysm'
    init_app(app_root)


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
    for backup in Backup.get_list():
        print(backup)


@catactl.command()
@click.argument('backup')
def restore(backup):
    """
    Restores the BACKUP into the most recently installed build.

    Use 'latest' as the BACKUP name to restore the most recent backup.

    Try `catactl show backups` to see the list of backups.
    """
    backups = Backup.get_list()
    if not backups:
        print("No backups found")
        sys.exit(1)

    if backup == 'latest':
        backup = Backup.get_list()[-1]

    build = Release.load(env.current_install_data_file)
    Backup.restore(build, backup)


@show.command()
def directory():
    """
    Opens the catactl application folder in a window
    """
    subprocess.Popen(['start', str(env.app_root)], shell=True)


if __name__ == '__main__':
    catactl()
