"""
Copies of the store, and proof that they are copies.

The test that matters most is the WAL one. A backup taken with `cp` looks
correct in every way until the day it is restored and the last hour of
writes is missing - so the suite proves the copy sees rows that are still
in the sidecar.
"""

import os
import sqlite3

import pytest

from bootpages import backup, store


@pytest.fixture
def live(tmp_path):
    """
    A store with content, left with commits still in the -wal sidecar.

    The connection is held open for the duration of the test rather than
    returned and forgotten, so what is being backed up is a database with a
    live writer attached - which is the situation on a running server, and
    the only one worth testing.
    """

    path = str(tmp_path / "live.db")
    db = store.connect(path)
    store.create_account(db, "author", mode="open")

    yield path

    db.close()


def test_backup_captures_rows_still_in_the_wal(live, tmp_path):
    """
    The whole reason this is not a `cp`. store.py runs WAL, so a committed
    row lives in the sidecar until a checkpoint - and a file copy misses it.
    """

    assert os.path.exists(live + "-wal"), "fixture should leave a sidecar"

    copy = backup.create(live, str(tmp_path / "backups"))

    checked = sqlite3.connect(copy)
    assert checked.execute("SELECT count(*) FROM accounts").fetchone()[0] == 1
    checked.close()


def test_backup_is_named_for_the_moment_it_was_taken(live, tmp_path):
    copy = backup.create(live, str(tmp_path / "backups"), now=1780000000)

    assert os.path.basename(copy) == "bootpages-20260528T202640Z.db"


def test_verify_rejects_a_truncated_copy(live, tmp_path):
    copy = backup.create(live, str(tmp_path / "backups"))

    with open(copy, "r+b") as handle:
        handle.truncate(os.path.getsize(copy) // 2)

    with pytest.raises(backup.BackupError):
        backup.verify(copy)


def test_verify_rejects_something_that_is_not_a_database(tmp_path):
    path = tmp_path / "bootpages-20260101T000000Z.db"
    path.write_bytes(b"not a database")

    with pytest.raises(backup.BackupError):
        backup.verify(str(path))


def test_backup_of_an_empty_store_is_valid(tmp_path):
    """
    A fresh instance has no pages. That is a normal state, not a failure -
    the invariant is that the copy matches the source, not that it is
    non-empty.
    """

    path = str(tmp_path / "empty.db")
    db = store.connect(path)

    try:
        copy = backup.create(path, str(tmp_path / "backups"))

        assert backup.verify(copy) == {"pages": 0, "accounts": 0}

    finally:
        db.close()


def test_refuses_when_the_drive_is_not_mounted(live, tmp_path):
    """
    A path under a mountpoint exists whether or not anything is mounted on
    it. Writing there quietly fills the internal disk while looking like an
    external backup.
    """

    dest = tmp_path / "mnt" / "external"

    with pytest.raises(backup.BackupError, match="not mounted"):
        backup.create(live, str(dest), require_mount=True)

    assert not dest.exists(), "must not create the directory it refused"


# ------------------------------------------------------------------ pruning


def _stamped(dest, *stamps):
    dest.mkdir(parents=True, exist_ok=True)

    for stamp in stamps:
        (dest / f"bootpages-{stamp}.db").write_bytes(b"")


def test_existing_lists_newest_first(tmp_path):
    dest = tmp_path / "backups"
    _stamped(dest, "20260101T000000Z", "20260103T000000Z", "20260102T000000Z")

    names = [os.path.basename(p) for p in backup.existing(str(dest))]

    assert names == [
        "bootpages-20260103T000000Z.db",
        "bootpages-20260102T000000Z.db",
        "bootpages-20260101T000000Z.db",
    ]


def test_existing_ignores_files_it_did_not_write(tmp_path):
    dest = tmp_path / "backups"
    _stamped(dest, "20260101T000000Z")
    (dest / "notes.txt").write_bytes(b"")
    (dest / "bootpages.db").write_bytes(b"")

    assert len(backup.existing(str(dest))) == 1


def test_prune_keeps_the_newest(tmp_path):
    dest = tmp_path / "backups"
    _stamped(dest, "20260101T000000Z", "20260102T000000Z", "20260103T000000Z")

    removed = backup.prune(str(dest), keep=2)

    remaining = sorted(p.name for p in dest.iterdir())
    assert remaining == [
        "bootpages-20260102T000000Z.db",
        "bootpages-20260103T000000Z.db",
    ]
    assert len(removed) == 1


def test_prune_never_removes_the_copy_just_written(live, tmp_path):
    dest = str(tmp_path / "backups")

    for moment in range(1780000000, 1780000005):
        newest = backup.create(live, dest, keep=2, now=moment)

    assert os.path.exists(newest)
    assert len(backup.existing(dest)) == 2


def test_prune_on_an_empty_directory_is_quiet(tmp_path):
    dest = tmp_path / "backups"
    dest.mkdir()

    assert backup.prune(str(dest), keep=30) == []
