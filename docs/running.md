# Running bootpages

Two ways: from a terminal while you work on it, and as a system service.

---

## From a terminal

```sh
python3 -m bootpages.server
```

Editor at <http://127.0.0.1:8080>, store at `data/bootpages.db`.

```
--host        default 127.0.0.1
--port        default 8080
--db          default data/bootpages.db
--allow-public   permit a non-loopback bind
```

No dependencies. Standard library only — `http.server`, `sqlite3`,
`hashlib`, `json`. There is nothing to install and nothing to activate.

---

## As a service

```sh
sudo git clone https://github.com/babbworks/bootpages.git /opt/bootpages
cd /opt/bootpages
sudo ./install.sh
```

That creates the `bootpages` system user, installs the unit, and starts it.
`journalctl -u bootpages -f` to watch.

Notably absent, compared with most services: no venv, no `.env`, no
configuration file, no secret to place. The unit runs `/usr/bin/python3`
directly, because a service that imports nothing outside the standard
library should not carry an empty virtualenv for the look of the thing.

### Where things live

```
/opt/bootpages                       the code, root:root 0755
/etc/systemd/system/bootpages.service
/var/lib/bootpages/bootpages.db      the store, created by StateDirectory=
```

The database is the only thing on disk that matters. Backing this service
up is copying one file; restoring it is copying the file back. For a store
whose entire promise is that the bytes come back, that is worth more than
any amount of operational cleverness.

### Updating

```sh
sudo git -C /opt/bootpages pull
sudo systemctl restart bootpages
```

---

## The gate

**Bootpages binds to `127.0.0.1` and `createAccount` is open.** Anyone who
can reach the port can mint an account and publish permanent public pages.
The loopback bind is the entire gate — this is what
[decisions](decisions.md) calls network gating, and it is the first phase
of a deliberately staged approach to opening up.

The server therefore **refuses to bind to a non-loopback address**:

```
$ python3 -m bootpages.server --host 0.0.0.0
Refusing to bind to 0.0.0.0.

createAccount is open on this build: anyone who can reach this port can
mint an account and publish permanent public pages. ...
```

`--allow-public` overrides it. That flag is a speed bump, not a security
control: it exists so that exposing account creation is a deliberate act
rather than a typo in a unit file.

### Giving it a real address

Terminate TLS and authenticate in a reverse proxy in front of it, and leave
the service on loopback. The proxy talks to `127.0.0.1:8080`; nothing else
does. This keeps the gate in the component designed to hold one.

Do **not** reach for `--allow-public` to put it on the open internet.
Everything that would make that safe is
[Phase 8](roadmap.md) — rate limiting, content scanning, a takedown
workflow, a stated legal posture — and none of it exists yet.

---

## The watchdog

`WatchdogSec=120` in the unit, with the server pinging at half that.

This matters more than it looks. A wedged HTTP server — one that has
stopped accepting connections but whose process is still alive — looks
perfectly healthy to `Restart=always`. The watchdog is what tells the
difference: silence is a restart.

Running from a terminal, the same code is a no-op, because `NOTIFY_SOCKET`
is only set by systemd. The service and the development run behave
identically in every other respect.

---

## What to watch

**The store file only.** `/var/lib/bootpages/bootpages.db`, plus its `-wal`
sidecar. `PRAGMA synchronous=FULL` is set: a page that was acknowledged and
then lost to a crash is a broken promise, not a performance question.

**Restarts.** `systemctl show bootpages -p NRestarts`. A service that keeps
restarting is either wedging or crashing, and the journal will say which.

**Nothing else.** There is no queue, no cache to warm, no external
dependency to be down, and no credential to expire.
