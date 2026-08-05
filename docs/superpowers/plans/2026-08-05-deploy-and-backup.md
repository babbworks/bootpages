# Deploy and Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give bootpages a repeatable deploy that cannot land code without a verified backup beside it, plus a scheduled backup for the authoring risk deploys do not cover.

**Architecture:** Backup logic lives in `bootpages/backup.py` as a stdlib Python module, because a WAL database cannot be copied with `cp` and because Python is what this repo can test. `deploy.sh` is orchestration only — it shells out to `python3 -m bootpages.backup`. A systemd timer runs the same module on a schedule.

**Tech Stack:** Python 3.7+ standard library only (`sqlite3`, `os`, `time`, `argparse`, `subprocess`), bash, systemd.

## Global Constraints

Every task's requirements implicitly include these.

- **Python floor is 3.7.** Set by `ThreadingHTTPServer` (`bootpages/server.py:35`) and matched by `sqlite3.Connection.backup()`. No walrus, no `match`, no `X | None` annotations, no `str.removeprefix`.
- **Standard library only.** No pip installs, no venv, no `sqlite3` CLI dependency. `install.sh:11` advertises "no dependencies to install, no venv to build" and that must stay true.
- **Target is 32-bit big-endian PowerPC** running Debian ports with systemd. Never assume x86 or 64-bit.
- **Never touch `/etc/systemd/system/bootpages.service.d/instance.conf`.** It holds mode and ports, written by `install.sh` so updates cannot clobber them.
- **Fail loudly, never fall back.** Every failure aborts with a message naming what failed and what was left unchanged. No silent fallback to a different destination.
- **Retention is 30** on every tier.
- **Shell is `set -euo pipefail`.**
- **House style:** module docstrings explain *why* the thing is shaped as it is, not what it does. Comments explain reasoning. Read `bootpages/store.py:1-12` for the register.

---

### Task 1: WAL-safe backup with verification

**Files:**
- Create: `bootpages/backup.py`
- Test: `tests/test_backup.py`

**Interfaces:**
- Consumes: `bootpages.store.connect(path)` — returns a `sqlite3.Connection` with `row_factory = sqlite3.Row`, WAL mode, schema applied.
- Produces:
  - `class BackupError(Exception)`
  - `destination(path, require_mount=False) -> str`
  - `counts(connection) -> dict` with keys `pages`, `accounts`
  - `verify(path) -> dict` (same keys), raises `BackupError`
  - `create(db_path, dest, keep=30, require_mount=False, now=None) -> str` (path to the new copy)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backup.py`:

```python
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
    """A store with content, left with commits still in the -wal sidecar."""

    path = str(tmp_path / "live.db")
    db = store.connect(path)
    store.create_account(db, "author", mode="open")

    return path


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
    store.connect(path)

    copy = backup.create(path, str(tmp_path / "backups"))

    assert backup.verify(copy) == {"pages": 0, "accounts": 0}


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_backup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bootpages.backup'`

- [ ] **Step 3: Write the implementation**

Create `bootpages/backup.py`:

```python
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
import sqlite3
import time

PREFIX = "bootpages-"
SUFFIX = ".db"

# Sorts lexicographically in timestamp order, which is why pruning needs no
# mtime and survives a filesystem that does not preserve one.
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
    # refusing one would fail a deploy for a naming detail.
    while os.path.exists(candidate):
        attempt += 1
        candidate = os.path.join(
            dest, f"{PREFIX}{stamp}-{attempt}{SUFFIX}")

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
```

Note: `prune` is called here but defined in Task 2. Add this stub now so the module imports, and replace it in Task 2:

```python
def prune(dest, keep):
    """Replaced in Task 2."""

    return []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_backup.py -v`
Expected: PASS, 6 tests.

The expected filename was checked against this Python, not recalled:
`time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(1780000000))` is
`20260528T202640Z`. If it still fails, print the actual value and correct
the test rather than the implementation.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. Nothing in Task 1 touches existing modules.

- [ ] **Step 6: Commit**

```bash
git add bootpages/backup.py tests/test_backup.py
git commit -m "Back the store up without a cp

store.py runs WAL, so a committed row lives in the sidecar until a
checkpoint and a file copy captures a torn database. The online backup
API reads a consistent snapshot from a live writer, and it is stdlib at
the same 3.7 floor the server already sets.

Every copy is verified against the counts of the source it came from,
which works on a fresh instance where the right answer is zero."
```

---

### Task 2: Pruning and listing

**Files:**
- Modify: `bootpages/backup.py` (replace the `prune` stub)
- Modify: `tests/test_backup.py` (append)

**Interfaces:**
- Consumes: `PREFIX`, `SUFFIX`, `BackupError` from Task 1.
- Produces:
  - `existing(dest) -> list[str]` — absolute paths, newest first
  - `prune(dest, keep) -> list[str]` — paths removed

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backup.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_backup.py -k "existing or prune" -v`
Expected: FAIL — `AttributeError: module 'bootpages.backup' has no attribute 'existing'`

- [ ] **Step 3: Write the implementation**

Replace the `prune` stub in `bootpages/backup.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_backup.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add bootpages/backup.py tests/test_backup.py
git commit -m "Prune to the newest thirty, by name

Ordered by filename rather than mtime, because the stamp sorts in
timestamp order and that stays true after these are copied to an
external drive that did not preserve modification times."
```

---

### Task 3: Restore, guarded by the running service

**Files:**
- Modify: `bootpages/backup.py`
- Modify: `tests/test_backup.py` (append)

**Interfaces:**
- Consumes: `verify`, `BackupError`, `STAMP` from Task 1.
- Produces:
  - `service_active(unit="bootpages") -> bool`
  - `restore(backup_path, db_path, force=False) -> str` — path the superseded database was moved to, or `""` if there was none

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backup.py`:

```python
# ------------------------------------------------------------------ restore


def test_restore_refuses_while_the_service_is_running(live, tmp_path, monkeypatch):
    """
    Restoring underneath a live writer turns one problem into two.
    """

    copy = backup.create(live, str(tmp_path / "backups"))
    monkeypatch.setattr(backup, "service_active", lambda unit="bootpages": True)

    with pytest.raises(backup.BackupError, match="running"):
        backup.restore(copy, live)


def test_restore_puts_the_bytes_back(live, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "service_active", lambda unit="bootpages": False)

    copy = backup.create(live, str(tmp_path / "backups"))

    target = str(tmp_path / "restored.db")
    backup.restore(copy, target)

    checked = sqlite3.connect(target)
    assert checked.execute("SELECT count(*) FROM accounts").fetchone()[0] == 1
    checked.close()


def test_restore_moves_the_old_database_aside(live, tmp_path, monkeypatch):
    """
    Never overwrite in place. If the backup turns out to be the wrong one,
    the thing it replaced must still exist.
    """

    monkeypatch.setattr(backup, "service_active", lambda unit="bootpages": False)

    copy = backup.create(live, str(tmp_path / "backups"))
    superseded = backup.restore(copy, live)

    assert superseded
    assert os.path.exists(superseded)


def test_restore_refuses_a_corrupt_backup(live, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "service_active", lambda unit="bootpages": False)

    copy = backup.create(live, str(tmp_path / "backups"))

    with open(copy, "r+b") as handle:
        handle.truncate(os.path.getsize(copy) // 2)

    with pytest.raises(backup.BackupError):
        backup.restore(copy, live)


def test_force_overrides_the_service_guard(live, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "service_active", lambda unit="bootpages": True)

    copy = backup.create(live, str(tmp_path / "backups"))
    target = str(tmp_path / "forced.db")

    backup.restore(copy, target, force=True)

    assert os.path.exists(target)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_backup.py -k restore -v`
Expected: FAIL — `AttributeError: module 'bootpages.backup' has no attribute 'restore'`

- [ ] **Step 3: Write the implementation**

Add to `bootpages/backup.py` (and add `import shutil` and `import subprocess` to the imports at the top):

```python
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

    except (OSError, FileNotFoundError):
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_backup.py -v`
Expected: PASS, 16 tests.

- [ ] **Step 5: Commit**

```bash
git add bootpages/backup.py tests/test_backup.py
git commit -m "Restore, refusing while the service holds the file

Also clears the -wal and -shm sidecars, which belong to the database
being replaced. Leaving them is how a restore appears to work and then
serves the wrong bytes.

The superseded database is moved aside, never overwritten. A restore is
usually done under pressure and the wrong backup is a live possibility."
```

---

### Task 4: Command line entry point

**Files:**
- Modify: `bootpages/backup.py`
- Test: manual, per Step 4 (argparse wiring; the logic beneath it is already covered)

**Interfaces:**
- Consumes: `create`, `verify`, `restore`, `existing`, `BackupError` from Tasks 1-3; `bootpages.config.Instance` for the database default.
- Produces: `python3 -m bootpages.backup {create,verify,restore,list}`

Mirror `bootpages/admin.py:145-185` exactly — same `prog=` form, same `COMMANDS` dict dispatch, same `raise SystemExit(f"error: {problem}")`.

- [ ] **Step 1: Write the implementation**

Add to `bootpages/backup.py` (add `import argparse` and `from .config import Instance` to the imports):

```python
# ------------------------------------------------------------ command line

DEFAULT_DIR = "/var/backups/bootpages"


def cmd_create(args, instance):
    written = create(
        instance.database,
        args.dest,
        keep=args.keep,
        require_mount=args.require_mount,
    )

    found = verify(written)
    print(f"{written}  {found['pages']} pages, {found['accounts']} accounts")


def cmd_verify(args, instance):
    found = verify(args.path)
    print(f"ok  {found['pages']} pages, {found['accounts']} accounts")


def cmd_restore(args, instance):
    superseded = restore(args.path, instance.database, force=args.force)

    print(f"restored {args.path} -> {instance.database}")

    if superseded:
        print(f"previous database kept at {superseded}")


def cmd_list(args, instance):
    found = existing(args.dest)

    if not found:
        print(f"no backups in {args.dest}")
        return

    for path in found:
        size = os.path.getsize(path)
        print(f"{os.path.basename(path):<40} {size:>12} bytes")


COMMANDS = {
    "create": cmd_create,
    "verify": cmd_verify,
    "restore": cmd_restore,
    "list": cmd_list,
}


def main():
    parser = argparse.ArgumentParser(
        prog="python3 -m bootpages.backup",
        description="Copies of the store, and proof that they are copies.",
    )
    parser.add_argument("--db", default=None)

    sub = parser.add_subparsers(dest="command", required=True)

    creating = sub.add_parser("create", help="take a verified backup")
    creating.add_argument("--dest", default=os.environ.get(
        "BOOTPAGES_BACKUP_DIR", DEFAULT_DIR))
    creating.add_argument("--keep", type=int, default=int(os.environ.get(
        "BOOTPAGES_BACKUP_KEEP", 30)))
    creating.add_argument(
        "--require-mount",
        action="store_true",
        default=os.environ.get("BOOTPAGES_BACKUP_REQUIRE_MOUNT") == "1",
        help="refuse if the destination is not a mountpoint - for the "
             "external drive, where a missing disk must stop a deploy",
    )

    checking = sub.add_parser("verify", help="prove a backup is readable")
    checking.add_argument("path")

    restoring = sub.add_parser("restore", help="put a backup back")
    restoring.add_argument("path")
    restoring.add_argument(
        "--force",
        action="store_true",
        help="restore even though the service looks active",
    )

    listing = sub.add_parser("list", help="what backups exist")
    listing.add_argument("--dest", default=os.environ.get(
        "BOOTPAGES_BACKUP_DIR", DEFAULT_DIR))

    args = parser.parse_args()
    instance = Instance(database=args.db)

    try:
        COMMANDS[args.command](args, instance)

    except BackupError as problem:
        raise SystemExit(f"error: {problem}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the suite to confirm nothing regressed**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Exercise the CLI by hand**

```bash
python3 -m bootpages.admin --db /tmp/cli.db mint --short-name check
python3 -m bootpages.backup --db /tmp/cli.db create --dest /tmp/bk
python3 -m bootpages.backup list --dest /tmp/bk
python3 -m bootpages.backup verify /tmp/bk/bootpages-*.db
python3 -m bootpages.backup --db /tmp/cli.db create --dest /tmp/nope --require-mount
```

Expected: the first four succeed and print counts; the last exits non-zero with `error: /tmp/nope is not mounted.` and does **not** create `/tmp/nope`.

- [ ] **Step 4: Confirm the refusal left nothing behind**

Run: `test ! -e /tmp/nope && echo "clean"`
Expected: `clean`

- [ ] **Step 5: Commit**

```bash
git add bootpages/backup.py
git commit -m "A command line for backups, shaped like admin's

Same prog form, same COMMANDS dispatch, same SystemExit on error, so
there is one shape to learn for both tools.

Defaults read from the environment like every other knob in this
project, which is what makes pointing at the external drive a variable
rather than a change."
```

---

### Task 5: deploy.sh

**Files:**
- Create: `deploy.sh` (mode 0755)
- Modify: `docs/running.md:60-68` (the Updating section)

**Interfaces:**
- Consumes: `python3 -m bootpages.backup create` from Task 4.
- Produces: `./deploy.sh [local|user@host] [ref]`

- [ ] **Step 1: Write the script**

Create `deploy.sh`:

```bash
#!/usr/bin/env bash
#
# Update a bootpages install.
#
#   ./deploy.sh                      # this machine, main
#   ./deploy.sh local v1.2.0         # this machine, a tag
#   ./deploy.sh user@powerbook       # a server, main
#   ./deploy.sh user@powerbook v1.2  # a server, a tag
#
# install.sh CREATES an install and asks questions. This one UPDATES one
# and never asks. It reinstalls the unit but never touches the drop-in at
# bootpages.service.d/instance.conf, which holds the mode and ports that
# install.sh was told - so an update cannot silently change how the
# instance behaves.
#
# Given a host, this copies itself over and runs there. The tests then run
# on the machine being deployed to, which for a 32-bit PowerPC target is
# the only place they mean anything.
#
# Nothing here falls back. A deploy that half worked is worse than one that
# refused, because the second tells you where you are.

set -euo pipefail

HOST="${1:-local}"
REF="${2:-main}"

DIR="${BOOTPAGES_DIR:-/opt/bootpages}"
UNIT="${BOOTPAGES_UNIT:-bootpages}"
BACKUP_DIR="${BOOTPAGES_BACKUP_DIR:-/var/backups/bootpages}"
BACKUP_KEEP="${BOOTPAGES_BACKUP_KEEP:-30}"
DB="${BOOTPAGES_DB:-/var/lib/bootpages/bootpages.db}"
PORT="${BOOTPAGES_PORT:-8080}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\n!! %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------ remote

if [ "$HOST" != "local" ]; then
  say "deploying to $HOST"

  # Forward the configuration rather than assuming the remote shell has it.
  ssh "$HOST" \
    "BOOTPAGES_DIR='$DIR' BOOTPAGES_UNIT='$UNIT' \
     BOOTPAGES_BACKUP_DIR='$BACKUP_DIR' BOOTPAGES_BACKUP_KEEP='$BACKUP_KEEP' \
     BOOTPAGES_BACKUP_REQUIRE_MOUNT='${BOOTPAGES_BACKUP_REQUIRE_MOUNT:-}' \
     BOOTPAGES_DB='$DB' BOOTPAGES_PORT='$PORT' \
     sudo -E '$DIR/deploy.sh' local '$REF'"

  exit $?
fi

# ---------------------------------------------------------------- preflight

[ "$(id -u)" -eq 0 ] || die "run me with sudo"

[ -d "$DIR/.git" ] || die "$DIR is not a git checkout. Run install.sh first."

say "tests first, always"
( cd "$DIR" && python3 -m pytest -q ) || die "tests failed; nothing changed"

# ------------------------------------------------------------------- backup
#
# Before anything moves. The copy is verified against the source as it is
# written - see bootpages/backup.py.

say "backing up to $BACKUP_DIR"

MOUNT_FLAG=""
[ "${BOOTPAGES_BACKUP_REQUIRE_MOUNT:-}" = "1" ] && MOUNT_FLAG="--require-mount"

( cd "$DIR" && python3 -m bootpages.backup --db "$DB" create \
    --dest "$BACKUP_DIR" --keep "$BACKUP_KEEP" $MOUNT_FLAG ) ||
  die "backup failed; nothing changed"

NEWEST="$(cd "$DIR" && python3 -m bootpages.backup list --dest "$BACKUP_DIR" |
          head -1 | awk '{print $1}')"

# --------------------------------------------------------------------- code

if ! git -C "$DIR" diff --quiet || ! git -C "$DIR" diff --cached --quiet; then
  die "working tree at $DIR is dirty; someone edited production"
fi

WAS="$(git -C "$DIR" rev-parse --short HEAD)"

say "updating $DIR to $REF"

git -C "$DIR" fetch --tags --prune origin
git -C "$DIR" checkout --detach "origin/$REF" 2>/dev/null ||
  git -C "$DIR" checkout --detach "$REF"

# Prove the new code at least parses before it becomes the running one.
python3 -m compileall -q "$DIR/bootpages" >/dev/null ||
  die "new code does not compile; roll back with: git -C $DIR checkout $WAS"

# --------------------------------------------------------------------- unit
#
# The unit, but never the drop-in. instance.conf holds the mode and ports
# install.sh was told, and this script was told nothing.

say "refreshing the unit"

install -m 644 "$DIR/bootpages.service" /etc/systemd/system/
systemctl daemon-reload

# ------------------------------------------------------------------ restart

say "restarting"

systemctl restart "$UNIT"
sleep 3

if ! systemctl is-active --quiet "$UNIT"; then
  die "$UNIT did not come back.
    journalctl -u $UNIT -n 40
  roll back with:
    git -C $DIR checkout $WAS && systemctl restart $UNIT
  the database before this deploy is at:
    $BACKUP_DIR/$NEWEST"
fi

if ! curl -fsS -o /dev/null "http://127.0.0.1:$PORT/"; then
  die "$UNIT is active but not answering on 127.0.0.1:$PORT.
    journalctl -u $UNIT -n 40
  roll back with:
    git -C $DIR checkout $WAS && systemctl restart $UNIT
  the database before this deploy is at:
    $BACKUP_DIR/$NEWEST"
fi

say "deployed $(git -C "$DIR" rev-parse --short HEAD), was $WAS"
echo "    backup: $BACKUP_DIR/$NEWEST"
```

- [ ] **Step 2: Make it executable and check it parses**

```bash
chmod 755 deploy.sh
bash -n deploy.sh && echo "syntax ok"
```

Expected: `syntax ok`

- [ ] **Step 3: Confirm it refuses outside an install**

Run: `sudo BOOTPAGES_DIR=/tmp/not-an-install ./deploy.sh local`
Expected: exits non-zero with `!! /tmp/not-an-install is not a git checkout. Run install.sh first.`

- [ ] **Step 4: Update the docs**

In `docs/running.md`, replace the `### Updating` section (currently the two-line pull and restart) with:

```markdown
### Updating

```sh
sudo /opt/bootpages/deploy.sh          # on the machine
./deploy.sh user@powerbook             # from anywhere with ssh
```

Tests run first, then a verified backup is taken, and only then does any
code move. Given a host, deploy.sh copies the work to that machine and runs
there — so the tests run on the architecture being deployed to, which
matters when that is a 32-bit PowerPC laptop and your desk is not.

It reinstalls the unit but never the drop-in. Mode and port changes stay
with `install.sh`, which is the thing that was told what they are.

Nothing falls back. If the tests fail, the backup fails, or the service
does not answer afterwards, it stops and prints the command to roll back
and the backup to roll back to.
```

- [ ] **Step 5: Commit**

```bash
git add deploy.sh docs/running.md
git commit -m "Deploy behind a test gate and a verified backup

running.md offered a pull and a restart, which is fine right up until the
pull brings something that does not start and there is no copy of the
database from before it.

Given a host it re-executes itself there, so the suite runs on the
machine being deployed to. Passing tests on an x86 laptop say very
little about 32-bit big-endian PowerPC.

Reinstalls the unit, never the drop-in - install.sh knows the mode and
ports, and this script deliberately does not."
```

---

### Task 6: Scheduled backups

**Files:**
- Create: `bootpages-backup.service`
- Create: `bootpages-backup.timer`
- Modify: `install.sh` (install the timer alongside the unit)
- Modify: `docs/running.md` (a Backups section)

**Interfaces:**
- Consumes: `python3 -m bootpages.backup create` from Task 4.

- [ ] **Step 1: Write the service unit**

Create `bootpages-backup.service`:

```ini
# A verified copy of the store, on a schedule.
#
# Deploys already take one. This exists because the risk they cover is not
# the risk that matters: editPage replaces a page wholesale with no undo,
# and that accrues with authoring, not with deploying. On an instance that
# is published to daily and deployed to monthly, a deploy-only backup is
# a month stale on its worst day.

[Unit]
Description=Bootpages - verified backup of the store
Documentation=https://github.com/babbworks/bootpages

[Service]
Type=oneshot

User=bootpages
Group=bootpages

WorkingDirectory=/opt/bootpages
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=BOOTPAGES_BACKUP_DIR=/var/backups/bootpages
Environment=BOOTPAGES_BACKUP_KEEP=30

ExecStart=/usr/bin/python3 -m bootpages.backup \
    --db /var/lib/bootpages/bootpages.db create

# The store to read and the backups to write. ProtectSystem=strict makes
# everything else read-only, so this list is the whole of what it can
# change. Point BOOTPAGES_BACKUP_DIR at an external drive and its mount
# must be added here too.
StateDirectory=bootpages
ReadWritePaths=/var/backups/bootpages

# Same posture as the server. It holds no credential and needs no
# privilege; the copy it writes contains tokens, which is why UMask is
# tight and the directory is not world-readable.
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectProc=invisible
RestrictNamespaces=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=
UMask=0077

MemoryMax=128M
TasksMax=16
```

- [ ] **Step 2: Write the timer**

Create `bootpages-backup.timer`:

```ini
# Daily, and catching up if the machine was not awake for it.

[Unit]
Description=Bootpages - daily verified backup
Documentation=https://github.com/babbworks/bootpages

[Timer]
OnCalendar=daily

# LOAD-BEARING ON A LAPTOP.
#
# Without this, a backup scheduled while the lid is shut is not late - it
# simply never happens, silently, and the first evidence is a gap in the
# directory on the day you need one. Persistent=true runs it on the next
# boot instead.
Persistent=true

# Nothing else runs at midnight on this machine, but a fixed time across a
# fleet is how you build a thundering herd.
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Install both from install.sh**

In `install.sh`, immediately after the existing `install -m 644 "$DST/bootpages.service" /etc/systemd/system/` line, add:

```bash
# The scheduled backup. Separate units rather than a thread inside the
# server, so a backup that fails is visible as a failed unit rather than a
# line in a log nobody reads.
install -m 644 "$DST/bootpages-backup.service" /etc/systemd/system/
install -m 644 "$DST/bootpages-backup.timer" /etc/systemd/system/

install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 /var/backups/bootpages
```

Then, immediately after the existing `systemctl enable --now bootpages` line, add:

```bash
systemctl enable --now bootpages-backup.timer
```

- [ ] **Step 4: Check both units parse**

```bash
systemd-analyze verify ./bootpages-backup.service ./bootpages-backup.timer
```

Expected: no output, or only warnings about `/opt/bootpages` not existing on a machine where it does not. Any error naming a directive is a real failure — fix it.

- [ ] **Step 5: Document it**

Append to `docs/running.md`, after the `### Updating` section:

```markdown
### Backups

```sh
systemctl list-timers bootpages-backup      # when it last ran, when it runs next
python3 -m bootpages.backup list            # what exists
python3 -m bootpages.backup verify PATH     # prove one is readable
```

Daily, plus one before every deploy. Thirty are kept. Each copy is verified
against the source as it is written — a backup that has never been read is
a hypothesis, and checking costs milliseconds.

Taken with SQLite's online backup, not `cp`. The store runs in WAL mode, so
a committed row lives in a sidecar file until a checkpoint and a plain copy
captures a torn database that looks fine until the day it is needed.

Restoring:

```sh
sudo systemctl stop bootpages
sudo -u bootpages python3 -m bootpages.backup restore /var/backups/bootpages/bootpages-....db
sudo systemctl start bootpages
```

It refuses while the service is running, and moves the database it replaces
aside rather than overwriting it.

**An external drive.** Set the destination and require it to be mounted:

```
BOOTPAGES_BACKUP_DIR=/mnt/bootpages-backups
BOOTPAGES_BACKUP_REQUIRE_MOUNT=1
```

in `/etc/systemd/system/bootpages-backup.service.d/` and in the environment
deploy.sh runs with. Add the mount to `ReadWritePaths=` in the same drop-in.

With the drive absent, a backup **fails** rather than falling back to the
internal disk. A path under a mountpoint exists whether or not anything is
mounted on it, so falling back is how you come to believe you have months
of external backups that were never written.

**Still missing: a copy that is not in this room.** Both tiers live on one
machine behind one power supply. They survive a bad edit and a dead disk;
they do not survive the building. See
`docs/superpowers/specs/2026-08-05-deploy-and-backup-design.md`.
```

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bootpages-backup.service bootpages-backup.timer install.sh docs/running.md
git commit -m "Back up on a timer, not only on deploys

The risk a deploy backup covers is not the one that matters. editPage
replaces wholesale with no undo, and that accrues with authoring - on an
instance published to daily and deployed to monthly, a deploy-only
backup is a month stale on its worst day.

Persistent=true is load-bearing here. Without it a backup scheduled
while the lid is shut does not happen at all, and the first evidence is
a gap in the directory on the day one is needed.

Records the missing tier honestly: both destinations are in one room."
```

---

## Self-Review

**Spec coverage.** Every section of `2026-08-05-deploy-and-backup-design.md` maps to a task: backup.py to Tasks 1-4, deploy.sh to Task 5, the timer to Task 6, retention to Task 2, mount enforcement to Tasks 1 and 4, restore to Task 3, all five specified tests to Tasks 1-3 (expanded to sixteen), the install.sh boundary to Task 5's unit step, off-machine backup recorded as out of scope in Task 6's docs.

**One spec correction, made deliberately.** The spec's step 5 said abort on "zero pages". That is wrong: a fresh instance legitimately has none, so the rule would fail the first deploy. The plan verifies the copy's counts **match the source's** instead, which catches truncation and is correct on an empty store. `test_backup_of_an_empty_store_is_valid` pins the behaviour. The spec should be amended to match.

**One mechanism substitution.** The spec said `mountpoint -q`; the plan uses `os.path.ismount()`. Same check, no subprocess, and it keeps the decision inside the module the test suite can reach.

**Type consistency.** `create/verify/counts` all return `{"pages": int, "accounts": int}`. `existing` and `prune` both return lists of absolute paths. `restore` returns a string, `""` when there was no prior database. `service_active` is a module-level name so `monkeypatch.setattr` in Task 3's tests intercepts the call `restore` makes.

**Known soft spot.** Task 5 Step 3's failure-path check is the only unverified behaviour in `deploy.sh`; the rest is exercised only by running it. That is the accepted cost of putting the testable logic in Python and leaving shell as orchestration.
