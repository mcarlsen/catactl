# catactl

`catactl` is a command line tool (currently for Windows) for playing experimental builds
of [Cataclysm: Dark Days Ahead](https://cataclysmdda.org/) - 
a turn-based survival game set in a post-apocalyptic world.

It can also backup and restore your save game for you. 
Backups are very fast due to multi-threaded compression - 
even when reaching 10000+ files in the save directory.

## Requirements

Windows 10 and a Python 3.9 environment.

## Installation

```shell
pip install git+https://github.com/mcarlsen/catactl.git
```

## Recipes

### Install the latest experimental build and play it

```shell
catactl install latest
catactl run
```

### Backup your current save

> ⚠️
> Do a *Quicksave* or *Save and Quit* from the game before doing a backup.

```shell
catactl backup
```

> Example output
> ```
> INFO: backing up cdda-experimental-2021-05-15-1507 to 2021-05-28-201148-cdda-experimental-2021-05-15-1507............
> INFO: compressed 118.9 MiB in 10108 files to 12.9 MiB at 89.1% compression rate
> INFO: backup took 3.95 seconds at 30.07 MiB/s (2557 files/s)
> ```

### Restore backups

> ⚠️
> Always *Quit* the game before restoring a backup

#### Restore your most recent backup

```shell
catactl restore latest
catactl run
```

#### Restore an earlier backup

List your backups (they are timestamped and by default they are labelled with the version of the game you were playing)

```shell
catactl show backups
```

> Example output:
> ```
> 2021-05-24-173950-cdda-experimental-2021-05-15-1507
> 2021-05-24-182747-cdda-experimental-2021-05-15-1507
> 2021-05-24-205205-cdda-experimental-2021-05-15-1507
> ```

Then select one of them to restore

```shell
catactl restore 2021-05-24-182747-cdda-experimental-2021-05-15-1507
catactl run
```


### Upgrade (or downgrade) the game

> ⚠️
> *Quit* the game before upgrading, of course

#### Install the latest experimental version and continue playing

This will backup your game, switch you to the latest version, then restore the backup into the new version of the game

```shell
catactl backup
catactl install latest
catactl restore latest
catactl run
```

### Play some version other than the latest

If the latest version is too buggy, you can install some other version.

First, get the latest versions available:

```shell
catactl show builds
```


> Example output:
> ```
> cdda-experimental-2021-05-23-0732
> cdda-experimental-2021-05-23-0814
> cdda-experimental-2021-05-23-0527
> cdda-experimental-2021-05-24-0603
> cdda-experimental-2021-05-25-1559
> cdda-experimental-2021-05-26-0607
> ```

Then select and play one of them:

```shell
catactl backup
catactl install cdda-experimental-2021-05-23-0527
catactl restore latest
catactl run
```

### Explore what other commands and options are available

```shell
catactl --help
```


