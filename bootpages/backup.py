"""
Copies of the store, and proof that they are copies.

A page is a promise that the bytes come back, so a backup here is not
operational hygiene - it is the mechanism by which that promise outlives
the disk. docs/roadmap.md says the sharper version: a backup that has never
been restored is a hypothesis.

The one thing that must never be done is `cp`. store.py runs the database
in WAL mode, so a committed row lives in a -wal sidecar until a checkpoint,
and a file copy captures a torn database that looks fine until the day it
is needed. SQLite's online backup reads a consistent snapshot from a live
writer, and it is in the standard library at the same version floor the
server already sets - so this costs no dependency.

Every copy is verified as it is written, against the source it came from.
Verifying costs milliseconds and turns each backup from a hypothesis into
evidence.
"""

import os
import shutil
import sqlite3
import subprocess
import time

PREFIX = "bootpages-"
SUFFIX = ".db"

# Sorts lexicographically in timestamp order, which is why pruning needs no
# mtime and survives a copy to a filesystem that did not preserve one.
STAMP = "%Y%m%dT%H%M%SZ"


class BackupError(Exception):
    """Something that must stop a deploy. The message says what to do."""


def destination(path, require_mount=False):
    """
    The backup directory, checked and created.

    `require_mount` is for the external drive. A path under a mountpoint
    exists whether or not anything is mounted there, so without this a
    deploy silently writes to the internal disk while reporting an external
    backup. Checked BEFORE the directory is created, so refusing leaves no
    trace.
    """

    if require_mount and not os.path.ismount(path):
        raise BackupError(
            f"{path} is not mounted. Attach the drive, or unset "
            f"BOOTPAGES_BACKUP_REQUIRE_MOUNT to back up to the internal "
            f"disk for this run."
        )

    try:
        os.makedirs(path, exist_ok=True)

    except OSError as problem:
        raise BackupError(f"cannot create {path}: {problem}")

    if not os.access(path, os.W_OK):
        raise BackupError(f"{path} is not writable")

    return path


def counts(connection):
    """What a copy must match. Cheap enough to run on every backup."""

    return {
        "pages": connection.execute(
            "SELECT count(*) FROM pages").fetchone()[0],
        "accounts": connection.execute(
            "SELECT count(*) FROM accounts").fetchone()[0],
    }


def verify(path):
    """
    Open a copy and prove it is one.

    Returns its counts, so a caller can compare them with the source.
    """

    if not os.path.exists(path):
        raise BackupError(f"{path} does not exist")

    try:
        db = sqlite3.connect(path)

        try:
            state = db.execute("PRAGMA integrity_check").fetchone()[0]

            if state != "ok":
                raise BackupError(f"{path}: integrity check said {state!r}")

            return counts(db)

        finally:
            db.close()

    except sqlite3.DatabaseError as problem:
        raise BackupError(f"{path}: not a readable database ({problem})")


def _name(dest, now=None):
    """A free filename for this moment, or the next free one after it."""

    stamp = time.strftime(STAMP, time.gmtime(now))
    candidate = os.path.join(dest, PREFIX + stamp + SUFFIX)
    attempt = 1

    # Two backups in the same second is unusual but not an error, and
    # refusing one would fail a deploy over a naming detail.
    while os.path.exists(candidate):
        attempt += 1
        candidate = os.path.join(dest, f"{PREFIX}{stamp}-{attempt}{SUFFIX}")

    return candidate


def create(db_path, dest, keep=30, require_mount=False, now=None):
    """
    An online copy of the store, verified against it, with old copies
    pruned. Returns the path written.

    Verification and pruning are part of taking a backup rather than
    separate steps, because an unchecked copy is the exact thing the
    roadmap warns about.
    """

    if not os.path.exists(db_path):
        raise BackupError(f"no database at {db_path}")

    dest = destination(dest, require_mount)

    need = os.path.getsize(db_path) * 2
    space = os.statvfs(dest)

    if space.f_bavail * space.f_frsize < need:
        raise BackupError(
            f"{dest} has less than {need} bytes free, which is twice the "
            f"database. Free space or prune before deploying."
        )

    source = sqlite3.connect(db_path)
    target = _name(dest, now)

    try:
        expected = counts(source)
        copy = sqlite3.connect(target)

        try:
            source.backup(copy)

        finally:
            copy.close()

    except sqlite3.DatabaseError as problem:
        raise BackupError(f"backup of {db_path} failed: {problem}")

    finally:
        source.close()

    found = verify(target)

    if found != expected:
        # Kept deliberately. A bad copy is evidence about what went wrong,
        # and deleting it would destroy the only record.
        raise BackupError(
            f"{target} does not match the source: expected {expected}, "
            f"found {found}. The copy has been kept for inspection."
        )

    prune(dest, keep)

    return target


def existing(dest):
    """
    Every backup in a directory, newest first.

    Ordered by name rather than mtime. The stamp sorts lexicographically in
    timestamp order, so this stays correct across a copy to a filesystem
    that did not preserve modification times - which is exactly what
    happens when these move to an external drive.
    """

    if not os.path.isdir(dest):
        return []

    found = [
        os.path.join(dest, name)
        for name in os.listdir(dest)
        if name.startswith(PREFIX) and name.endswith(SUFFIX)
    ]

    return sorted(found, reverse=True)


def prune(dest, keep):
    """
    Delete all but the newest `keep`. Returns what was removed.

    Runs after the new copy is written and verified, so the newest is never
    the one at risk.
    """

    if keep < 1:
        raise BackupError("keep must be at least 1")

    doomed = existing(dest)[keep:]

    for path in doomed:
        try:
            os.remove(path)

        except OSError as problem:
            raise BackupError(f"cannot remove {path}: {problem}")

    return doomed


# ------------------------------------------------------------------ restore


def service_active(unit="bootpages"):
    """
    Whether systemd is currently running the service.

    False anywhere systemd is absent, which is the right answer for a
    developer restoring into a checkout on their laptop.
    """

    try:
        finished = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except OSError:
        return False

    return finished.returncode == 0


def restore(backup_path, db_path, force=False):
    """
    Put a backup back. Returns where the superseded database was moved.

    Refuses while the service is running: SQLite will happily let two
    processes disagree about what the file contains, and the resulting
    state is worse than whatever prompted the restore.

    The database being replaced is moved aside rather than overwritten. If
    this turns out to be the wrong backup, the thing it replaced still
    exists.
    """

    if not force and service_active():
        raise BackupError(
            "bootpages is running. Stop it first:\n"
            "    sudo systemctl stop bootpages\n"
            "or pass --force if systemd is not managing this database."
        )

    verify(backup_path)

    superseded = ""

    if os.path.exists(db_path):
        superseded = f"{db_path}.superseded-{time.strftime(STAMP, time.gmtime())}"
        os.rename(db_path, superseded)

    # The sidecars belong to the database that just moved aside. Leaving
    # them next to a restored file is how a restore appears to work and
    # then serves the wrong bytes.
    for sidecar in ("-wal", "-shm"):
        stale = db_path + sidecar

        if os.path.exists(stale):
            os.remove(stale)

    try:
        shutil.copyfile(backup_path, db_path)

    except OSError as problem:
        raise BackupError(f"cannot write {db_path}: {problem}")

    return superseded
