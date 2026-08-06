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

MODE=""
PORT=""
PAGES_PORT=""
PAGES_URL=""
ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)        MODE="$2"; shift 2 ;;
    --port)        PORT="$2"; shift 2 ;;
    --pages-port)  PAGES_PORT="$2"; shift 2 ;;
    --pages-url)   PAGES_URL="$2"; shift 2 ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    -h|--help)
      cat <<'USAGE'
sudo ./install.sh [--mode open|invited|admin] [--port N] [--pages-port N]
                  [--pages-url URL] [--yes]

Prompts for anything not given. --yes takes the defaults and skips every
confirmation, for unattended runs.

--pages-url is the public address of published pages, e.g.
https://page.example. Give it whenever a reverse proxy is in front: the
API builds every link it hands out from this value, and a server that
only ever sees loopback HTTP cannot work it out. Omit it when reaching
this machine directly.
USAGE
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }

ask() {
  # ask VARNAME "prompt" "default"
  local __var="$1" __prompt="$2" __default="$3" __reply=""

  if [ "$ASSUME_YES" = 1 ] || [ -n "${!__var}" ]; then
    [ -z "${!__var}" ] && printf -v "$__var" '%s' "$__default"

    # Explicitly zero. A bare `return` carries the status of the test
    # above, which is 1 whenever the value was already set - and under
    # `set -e` that killed the whole install, silently, the moment anyone
    # passed a flag on the command line.
    return 0
  fi

  read -r -p "$__prompt [$__default]: " __reply < /dev/tty || true
  printf -v "$__var" '%s' "${__reply:-$__default}"
}

confirm() {
  # Every step that changes the machine asks first, unless told not to.
  [ "$ASSUME_YES" = 1 ] && return 0

  local reply=""
  read -r -p "$1 [Y/n] " reply < /dev/tty || true

  case "$reply" in
    [nN]*) return 1 ;;
    *)     return 0 ;;
  esac
}

# ---------------------------------------------------------------- preflight

[ "$(id -u)" -eq 0 ] || { echo "run me with sudo" >&2; exit 1; }

# Nothing outside the standard library, so this is the only requirement -
# and it is one that has shipped with Debian for a decade.
python3 -c 'import sqlite3, http.server, hashlib' || {
  echo "this python3 is missing a standard library module" >&2
  exit 1
}

# ------------------------------------------------------------------ choices

cat <<'INTRO'

  Bootpages installs as a system service. Three questions, then it runs.

  MODE decides how accounts come into being:

    admin    (default) createAccount is refused entirely. Tokens are
             minted from a shell with `python3 -m bootpages.admin mint`.
    invited  createAccount needs a one-time invite code, also minted
             from a shell. An invite is not a credential to an account,
             so it is far safer to hand out than a token.
    open     anyone who can reach the port can create an account.

INTRO

ask MODE "mode (open/invited/admin)" "admin"

case "$MODE" in
  open|invited|admin) ;;
  *) echo "mode must be open, invited or admin" >&2; exit 1 ;;
esac

if [ "$MODE" = open ]; then
  cat <<'WARN'

  !! open mode: anyone who can reach the port can mint an account and
     publish permanent public pages. The service binds to 127.0.0.1, so
     that means anyone with access to this machine - and anything you put
     in front of it.

WARN
fi

ask PORT "editor port" "8080"
ask PAGES_PORT "published pages port" "8081"

# The one setting this process cannot work out for itself.
#
# Every API response reports where a published page lives. Behind a
# reverse proxy that address is https://something on a name nothing here
# has been told, while the server sees only loopback HTTP - so leaving
# this blank on a public instance publishes links to 127.0.0.1 and looks
# perfectly healthy doing it.
#
# Blank is correct when nothing is in front, which is why it is allowed.
cat <<'PAGESURL'

  If a reverse proxy will serve published pages under a real name, give
  that address now - e.g. https://page.example. Every link the API hands
  out is built from it.

  Leave blank if you are reaching this machine directly.

PAGESURL

ask PAGES_URL "public URL for published pages" ""

case "$PAGES_URL" in
  ""|https://*|http://*) ;;
  *) echo "pages URL must start with http:// or https://" >&2; exit 1 ;;
esac

if [ "$PORT" = "$PAGES_PORT" ]; then
  echo "the editor and pages must not share a port - that separation is" >&2
  echo "what stops a script inside a page reading stored tokens" >&2
  exit 1
fi

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
  confirm "create system user $SVC_USER?" || exit 1

  say "creating system user $SVC_USER"
  useradd --system --shell /usr/sbin/nologin --home-dir "$DST" \
          --no-create-home "$SVC_USER"
fi

# ------------------------------------------------------------------- unit

confirm "write /etc/systemd/system/bootpages.service?" || exit 1

say "installing the unit"

install -m 644 "$DST/bootpages.service" /etc/systemd/system/

# The scheduled backup. Separate units rather than a thread inside the
# server, so a backup that fails is visible as a failed unit rather than a
# line in a log nobody reads.
install -m 644 "$DST/bootpages-backup.service" /etc/systemd/system/
install -m 644 "$DST/bootpages-backup.timer" /etc/systemd/system/

install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 /var/backups/bootpages

# The choices above become a drop-in rather than edits to the unit, so a
# `git pull` never clobbers them and `systemctl cat` shows both.
mkdir -p /etc/systemd/system/bootpages.service.d
cat > /etc/systemd/system/bootpages.service.d/instance.conf <<CONF
# Written by install.sh. Safe to edit; survives an update of the unit.
[Service]
Environment=BOOTPAGES_MODE=$MODE
Environment=BOOTPAGES_PORT=$PORT
Environment=BOOTPAGES_PAGES_PORT=$PAGES_PORT
CONF

# Only written when given. An empty value here would override the sensible
# local default with nothing, which is worse than being absent.
if [ -n "$PAGES_URL" ]; then
  cat >> /etc/systemd/system/bootpages.service.d/instance.conf <<CONF
Environment=BOOTPAGES_PAGES_URL=$PAGES_URL
CONF
fi

systemctl daemon-reload

confirm "enable and start bootpages now (and at boot)?" || {
  echo "installed but not started. systemctl enable --now bootpages"
  echo "                            systemctl enable --now bootpages-backup.timer"
  exit 0
}

systemctl enable --now bootpages
systemctl enable --now bootpages-backup.timer

# ----------------------------------------------------------------- verify

say "waiting for it to answer"
sleep 3

systemctl --no-pager --lines=0 status bootpages || true

if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/"; then
  echo "    editor answers on 127.0.0.1:$PORT"
else
  echo "    !! no answer yet - journalctl -u bootpages -n 20"
fi

# In any mode but open, the first run mints one account and prints its
# token to the journal. It is shown once and never again.
if [ "$MODE" != open ]; then
  say "first account"
  journalctl -u bootpages -n 40 --no-pager | grep -A2 -i "token " || {
    echo "    not in the journal - mint one with:"
    echo "    python3 -m bootpages.admin --db /var/lib/bootpages/bootpages.db mint --short-name you"
  }
fi

say "installed"
cat <<'NOTE'

  journalctl -u bootpages -f
  ls -la /var/lib/bootpages/

  Bound to 127.0.0.1. Put a reverse proxy in front of it before giving it
  a real address, and leave the host alone. See docs/running.md.

  Change the mode later by editing:
    /etc/systemd/system/bootpages.service.d/instance.conf

NOTE
