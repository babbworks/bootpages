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
  # Tests HERE before tests THERE, because they are not the same tests.
  #
  # tests/test_editor.py skips when node is absent, and node has no 32-bit
  # PowerPC build - so on the target that test silently vanishes while the
  # suite still reports success. editor.js is the largest file in this
  # project and its own docstring records an edit that deleted half of it
  # while every syntax check still passed.
  #
  # So this machine covers the editor, and the target covers the
  # architecture. Neither one alone is the suite.
  say "tests here first, where node exists"
  python3 -m pytest -q -rs || die "tests failed here; nothing was sent"

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

# The only thing this needs that the service does not. bootpages imports
# nothing outside the standard library at runtime and that stays true;
# deploying it is what wants a test runner.
python3 -c 'import pytest' 2>/dev/null ||
  die "pytest is not installed. On Debian:  apt-get install python3-pytest"

# -rs names what skipped. A test that quietly stopped running is not a
# passing test, and on this target test_editor.py always skips.
say "tests first, always"
( cd "$DIR" && python3 -m pytest -q -rs ) || die "tests failed; nothing changed"

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
install -m 644 "$DIR/bootpages-backup.service" /etc/systemd/system/
install -m 644 "$DIR/bootpages-backup.timer" /etc/systemd/system/
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
