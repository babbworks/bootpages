# Running bootpages

Two ways: from a terminal while you work on it, and as a system service.

---

## From a terminal

```sh
python3 -m bootpages.server
```

Editor at <http://127.0.0.1:8080>, store at `data/bootpages.db`.

```
--host          default 127.0.0.1
--port          default 8080          the editor and the API
--pages-port    default 8081          published pages
--mode          default admin         open | invited | admin
--db            default data/bootpages.db
--name --description --contact        what this instance calls itself
--allow-public                        permit a non-loopback bind
```

Every one of those also reads from the environment
(`BOOTPAGES_MODE`, `BOOTPAGES_PORT`, …), which is how the service is
configured.

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

## Two origins

The editor and published pages are served on **different ports**, and that
is not cosmetic.

The editor keeps author tokens in browser storage. Published pages are
untrusted content. Same-origin policy is what stops a script inside a page
reading that storage — and it is enforced by the browser, keyed on origin,
which is scheme + host + port. So a different port is enough, and **one
process serves both**; two processes would buy nothing against this.

```
:8080   the editor, its assets, and the API
:8081   rendered pages and their stylesheet — nothing else
```

Neither serves the other's routes. The editor returns 404 for a stored
page; the pages origin returns 404 for the API, the editor, and every
asset but its own stylesheet. The `url` in every API response points at
the pages origin regardless of which origin was asked, so the editor never
guesses where a page lives.

In production, give them two hostnames and let the reverse proxy route
both to the same process.

### Headers

Published pages carry a strict `Content-Security-Policy` with
`default-src 'none'`, so nothing executes there regardless of any bug in
the renderer — a defence at a different layer from "there is no path by
which author text becomes markup".

`frame-ancestors` is deliberately **open** on pages: bootpages are meant
to be embedded by consuming sites, and refusing to be framed would break
what they are for. The editor is the opposite — `X-Frame-Options: DENY`,
because a clickjacked token field is a real attack on a credential nobody
but its holder can revoke.

---

## Modes

How an account comes into being. Enforced in the store, so a client that
skips the first-run screen gets the same answer as one that does not.

| | |
|---|---|
| **`admin`** | *the default.* `createAccount` refused entirely. Tokens minted from a shell. |
| **`invited`** | `createAccount` needs a one-time invite code. |
| **`open`** | anyone who can reach the port can create an account. |

### Minting

```sh
python3 -m bootpages.admin mint --short-name morgen --author-name "Morgen"
python3 -m bootpages.admin invite --count 3 --note "design team"
python3 -m bootpages.admin invites --unused
python3 -m bootpages.admin accounts
```

**There is no admin account and no administration over HTTP.** The
operator's credential is shell access. That is a decision rather than an
omission: the editor keeps author tokens in the browser, and an admin
token in that same shelf would change what stealing it costs — from
"someone can publish as you" to "someone can mint unlimited accounts on
your instance".

### Why invites beat handing out tokens

An invite is a **one-time right to create an account**, not a credential
to one. Intercepted in transit, the worst outcome is a stranger creates
their own account, once. A token intercepted the same way lets someone
publish as you, forever, with nothing that expires.

### The first account

In any mode but `open`, the first run against an empty store mints one
account and prints its token. Once any account exists it never happens
again.

That exists so the tight default does not mean a fresh instance where
nobody can write anything — and it opens no hole, because anyone able to
start the server already has shell and could mint one anyway.

---

## Tokens, and losing them

A token **is** the account. No email, no password, no recovery question.

The editor therefore shows a token once, on creation, and asks the author
to confirm they have saved it. Remembering it in the browser is an opt-in
— unchecked, it lasts only until the tab closes.

`revokeAccessToken` issues a new token and moves the pages across, but it
needs the *old* token to call. It handles "this leaked", not "I lost it".

### Several accounts in one browser

The account list holds any number of tokens with **no server-side
association between them**. The store cannot tell that two of them belong
to the same person, and there is no endpoint that would let it.

That rests on one rule, which is worth stating because it is easy to break
by accident: **one token per request, ever.** Never send two together;
never build a call that accepts several. Break it once and the property is
gone retroactively, for every account already created.

---

## The gate

**Bootpages binds to `127.0.0.1`.** In `open` mode the loopback bind is
the entire gate; in `admin` or `invited` mode it is one of two. This is
what [decisions](decisions.md) calls network gating, and it is the first
phase of a deliberately staged approach to opening up.

The server therefore **refuses to bind to a non-loopback address**:

```
$ python3 -m bootpages.server --host 0.0.0.0
Refusing to bind to 0.0.0.0.
...
```

`--allow-public` overrides it. That flag is a speed bump, not a security
control: it exists so that exposing the service is a deliberate act rather
than a typo in a unit file.

**Public *and* `open` together must be said twice.** `--allow-public` on
its own is not enough to run open-mode on a reachable address — the mode
has to be stated explicitly as well. That combination is the one that
should never happen because somebody flipped a mode for local convenience
and forgot.

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
