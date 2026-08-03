#!/usr/bin/env bash
#
# Install bootpages as a system service.
#
#   sudo git clone https://github.com/babbworks/bootpages.git /opt/bootpages
#   cd /opt/bootpages
#   sudo ./install.sh
#
# Considerably simpler than it would be for most services, because there is
# nothing to configure: no dependencies to install, no venv to build, no
# .env to fill in, and no secret to place. The whole install is a user, a
# copy, and a unit file.
#
# Safe to re-run.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DST="${BOOTPAGES_DIR:-/opt/bootpages}"
SVC_USER="${BOOTPAGES_USER:-bootpages}"

say() { printf '\n==> %s\n' "$*"; }

# ---------------------------------------------------------------- preflight

[ "$(id -u)" -eq 0 ] || { echo "run me with sudo" >&2; exit 1; }

# Nothing outside the standard library, so this is the only requirement -
# and it is one that has shipped with Debian for a decade.
python3 -c 'import sqlite3, http.server, hashlib' || {
  echo "this python3 is missing a standard library module" >&2
  exit 1
}

# ------------------------------------------------------------------- code

if [ "$HERE" != "$DST" ]; then
  say "copying $HERE -> $DST"

  mkdir -p "$DST"
  rsync -a --exclude '.venv/' --exclude '__pycache__/' \
           --exclude '.pytest_cache/' --exclude 'data/' \
           "$HERE"/ "$DST"/
else
  say "installing in place at $DST"
fi

chown -R root:root "$DST"
chmod 755 "$DST"

# ------------------------------------------------------------------- user

if id -u "$SVC_USER" >/dev/null 2>&1; then
  say "service user $SVC_USER already exists"
else
  say "creating system user $SVC_USER"
  useradd --system --shell /usr/sbin/nologin --home-dir "$DST" \
          --no-create-home "$SVC_USER"
fi

# ------------------------------------------------------------------- unit

say "installing the unit"

install -m 644 "$DST/bootpages.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bootpages

# ----------------------------------------------------------------- verify

say "waiting for it to answer"
sleep 3

systemctl --no-pager --lines=0 status bootpages || true

if curl -fsS -o /dev/null http://127.0.0.1:8080/; then
  echo "    editor answers on 127.0.0.1:8080"
else
  echo "    !! no answer yet - journalctl -u bootpages -n 20"
fi

say "installed"
cat <<'NOTE'

  journalctl -u bootpages -f
  ls -la /var/lib/bootpages/

  Bound to 127.0.0.1. createAccount is open, so the loopback bind is the
  whole of the gate - put a reverse proxy in front of it before giving it
  a real address, and leave the --host alone. See docs/running.md.

NOTE
