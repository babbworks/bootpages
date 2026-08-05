# Deploy and backup

**Status:** design, approved 2026-08-05
**Scope:** `deploy.sh`, `bootpages/backup.py`, and a scheduled backup timer.

---

## Why

Bootpages is going to run as a public service from a single PowerBook G4.
That machine is the whole deployment: the store, the server, and for now
the only copy of the data.

`docs/roadmap.md` already calls backups a product requirement rather than
ops hygiene, because clients are promised permanence and `editPage`
replaces a page wholesale with no undo. Phase 5 adds the sharper version:
a backup that has never been restored is a hypothesis.

So this is not a convenience script. It is the mechanism by which the
central promise of the store stays true on hardware that will eventually
fail.

`install.sh` creates an install. Nothing yet updates one, and
`docs/running.md` currently offers only `git pull && systemctl restart` —
no test gate, no backup, no verification.

---

## Boundary with install.sh

`install.sh` **creates**. It is interactive, asks for mode and ports,
creates the system user, and writes the drop-in.

`deploy.sh` **updates**. It never prompts and never guesses.

The line that matters: deploy.sh reinstalls `bootpages.service` but
**never touches** `/etc/systemd/system/bootpages.service.d/instance.conf`.
That drop-in holds mode and ports, and `install.sh` writes them there
precisely so an update cannot clobber them. Changing mode or ports stays
an install.sh concern.

---

## Components

### 1. `bootpages/backup.py`

Backup logic lives in Python, not shell, for three reasons specific to
this project:

- A WAL database cannot be copied with `cp`. `store.py` sets
  `journal_mode=WAL`, so recent commits live in a `-wal` sidecar and a
  file copy captures a torn database. The correct mechanism is SQLite's
  online backup, exposed as `sqlite3.Connection.backup()`.
- That API is **stdlib, Python 3.7+** — the same floor `ThreadingHTTPServer`
  already sets in `server.py`. It needs no `sqlite3` CLI, which keeps the
  no-dependencies property `install.sh` depends on.
- This repo has a test suite. Python logic gets tested; shell gets hoped at.

Invoked as `python3 -m bootpages.backup`, matching `python3 -m
bootpages.admin` and `python3 -m bootpages.server`.

```
python3 -m bootpages.backup create --db PATH --dest DIR [--keep 30]
                                   [--require-mount]
python3 -m bootpages.backup verify PATH
python3 -m bootpages.backup restore PATH --db PATH
python3 -m bootpages.backup list --dest DIR
```

`create` writes `DIR/bootpages-YYYYMMDDTHHMMSSZ.db`, verifies it, then
prunes to the newest `--keep`. Verification and pruning are part of
`create` rather than separate steps, because a backup that was written but
not checked is the exact thing the roadmap warns about.

`restore` refuses while the service is active, checked with `systemctl
is-active bootpages` and overridable with `--force` for the case where
systemd is not managing the database at all. Restoring underneath a running
writer is how you turn one problem into two.

### 2. `deploy.sh`

Orchestration only. Signature matches telepatch's, so muscle memory
transfers:

```
./deploy.sh                      # on the G4, main
./deploy.sh local v1.2.0         # on the G4, a tag
./deploy.sh user@powerbook       # from the laptop, main
./deploy.sh user@powerbook v1.2  # from the laptop, a tag
```

Given a host, it SSHes in and re-executes itself there. Every privileged
step **and the test run** happen on the target. Running the suite on an
x86 laptop and shipping to 32-bit big-endian PowerPC would be testing the
wrong machine.

### 3. `bootpages-backup.service` + `.timer`

Deploy-triggered backups are not enough once strangers can publish. The
risk `editPage` creates accrues with authoring, not with deploying — deploy
only, the newest backup could be months old.

- `OnCalendar=daily`
- `Persistent=true` — **load-bearing on a laptop.** Without it, every
  backup scheduled while the machine is asleep or shut is silently skipped.
- Runs as the `bootpages` user, with `ReadWritePaths=` covering the backup
  directory.

---

## Sequence

Each step gates the next. Anything that fails aborts the deploy.

| # | Step | Aborts when |
|---|------|-------------|
| 1 | `pytest -q` on the target | any test fails |
| 2 | Preflight the backup destination | missing, unwritable, or not a mountpoint when required |
| 3 | Free-space check | less than 2× the database size available |
| 4 | `backup create` (online, WAL-safe) | copy fails |
| 5 | `integrity_check` + row counts on the **copy** | not `ok`, or counts do not match the source |
| 6 | Prune to newest 30 | — |
| 7 | Dirty-tree check, `git fetch`, checkout ref | production tree edited by hand |
| 8 | Byte-compile check on the new code | it does not parse |
| 9 | Reinstall unit, `daemon-reload` | — |
| 10 | `systemctl restart`, wait, verify | no answer on the editor port |

Tests run before the backup deliberately: they are cheap and they fail
fast, and if they fail nothing has been changed to need restoring.

Step 5 is what makes this more than hope. Verifying every copy on every run
costs milliseconds and turns each backup from a hypothesis into evidence.

The invariant is that the copy's row counts **match the source's** — not
that they are non-zero. A freshly installed instance legitimately has no
pages, and a non-zero rule would fail its very first deploy.

Rollback falls out for free: the pre-restart backup plus a git checkout of
the previous ref restores both halves of the system.

---

## Backup destinations

Configured by `BOOTPAGES_BACKUP_DIR`, matching the project's existing
convention that every knob reads from the environment.

| Tier | Path | Keep | Status |
|------|------|------|--------|
| Internal | `/var/backups/bootpages` | 30 | now |
| External | `/mnt/bootpages-backups` | 30 | when the drive arrives |
| Off-machine | — | — | **not in this spec, see below** |

**Provisioning for the external drive.** A path under `/mnt` exists whether
or not anything is mounted on it, so a naive script writes to a bare
mountpoint on the internal disk and reports success. When
`BOOTPAGES_BACKUP_REQUIRE_MOUNT=1`, the destination is checked with
`mountpoint -q` and the deploy **aborts** if the drive is absent. No
fallback to the internal disk: falling back is how you end up believing you
have months of external backups that were never written.

Default is off, since the internal disk is not a mountpoint. Attaching the
drive is then two environment variables and no code change.

### Off-machine is a known gap

Both tiers above live in the same room, on the same machine, behind the
same power supply. They protect against disk failure and bad edits. They do
not protect against theft, fire, or a PSU that takes both drives with it.

For a service promising permanence this is a real gap, recorded here
deliberately rather than left implicit. It is out of scope for this spec
because it needs a destination that does not exist yet. It should be the
next piece of durability work after this lands.

---

## Error handling

`set -euo pipefail` throughout. Every abort prints what failed, what was
and was not changed, and the command to inspect further.

The governing rule: **fail loudly, never fall back.** A deploy that half
worked is worse than one that refused, because the second tells you where
you are. This is the same reasoning as the missing-drive case — a warning
that scrolls past is not a safety mechanism.

Specific cases:

- Tests fail → abort before anything is touched.
- Backup destination missing or not a mountpoint → abort before the backup.
- `integrity_check` not `ok` → abort, keep the bad copy for inspection,
  name it in the error.
- Production tree dirty → abort. Someone edited production; that is a
  conversation, not a merge.
- Service does not answer after restart → report loudly and name the
  backup file and previous ref needed to roll back. Do not auto-roll-back;
  an automatic rollback during a partial failure can compound it.

---

## Testing

`tests/test_backup.py`, following the existing suite's style:

- **WAL consistency** — write rows, leave them in the `-wal` sidecar, back
  up, assert every row is present in the copy. This is the test that would
  catch someone "simplifying" the backup into a `cp`.
- **Verification catches corruption** — truncate a copy, assert `verify`
  fails rather than reporting success.
- **Pruning keeps the newest N** — and never removes the copy just written.
- **Mount enforcement** — with `--require-mount` and a non-mountpoint
  destination, assert it refuses and writes nothing.
- **Restore refuses while the service is active.**

`deploy.sh` itself is orchestration and is not unit tested. That is the
reason the logic worth testing was put in Python.

---

## Out of scope

- **Public exposure** — nginx, TLS, a domain, DNS. Its own spec. Note that
  Caddy is not an option: Go targets `ppc64`/`ppc64le` but never 32-bit
  `powerpc`, so nginx plus certbot is the path on a G4.
- **Off-machine backup** — see above.
- **Mode and port changes** — install.sh's job, by design.
