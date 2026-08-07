# What is done, and what is not

Live state of the `page.babb.tel` deployment. Updated as things land.

Last updated 2026-08-06.

---

## The deployment

| | |
|---|---|
| Machine | PowerBook G4, 7447A @ 1.5GHz, AltiVec, 2GB |
| OS | Debian forky/sid, 32-bit big-endian PowerPC |
| Python | 3.14.6 |
| nginx | 1.30.4 |
| Address | `192.168.2.55` on wifi (`00:0d:93:85:3e:54`) |
| Public | `76.64.226.39`, Bell, ports 80 and 443 forwarded |
| Names | `page.babb.tel` (pages), `edit.page.babb.tel` (editor) |
| Certificate | ECDSA, both names, one lineage, expires 2026-11-03 |

---

## Done and verified

- [x] Cloned to `/opt/bootpages`, branch `deploy-and-backup`
- [x] **Suite passes on PowerPC** — 59 passed, 1 skipped, 3.0s
- [x] **Digest is architecture-independent** — a digest computed on
      big-endian ppc is byte-identical to one computed on x86_64. This is
      the property page identity rests on, and the one worth re-checking
      on any new architecture.
- [x] `install.sh` run; service active and enabled at boot
- [x] `BOOTPAGES_PAGES_URL` reaches the API — `getInstanceInfo` reports
      `https://page.babb.tel`, not a loopback address
- [x] Certificate issued with renewal hooks that stop and start nginx
- [x] nginx serving both origins over HTTP/2
- [x] **Origin separation holds through the proxy** — `page.babb.tel`
      returns bootpages' own 404 rather than the editor. This is the
      property the two-name design exists to protect, and nothing in the
      application can detect its absence.
- [x] CSP differs per origin through nginx: `default-src 'none'` on
      pages, `frame-ancestors 'none'` on the editor
- [x] `/static/` served by nginx, never by Python
- [x] A page published, rendered, and revalidated with a 304
- [x] Backup timer armed and scheduled
- [x] **Landing page served at `/`** by nginx `proxy_pass`, with a
      canonical `Link` header naming the page's permanent address
- [x] **`?ref=<id>` subscription live** — `getPage` on the pages origin
      with CORS, returning a subtree with an ETag scoped to that block, so
      a watcher is not woken by edits elsewhere on the page
- [x] **Both lenses live** — `?lens=tree` and `?lens=json`, server
      rendered, no script
- [x] **Lens bar live** on the HTML and tree lenses; three links, no
      script, `default-src 'none'` untouched
- [x] **Second deploy through `deploy.sh`**, this time off `main` with no
      ref argument

---

## Not yet done

### Tests that have never run

- [x] **`bootpages-backup.service` ran unattended and succeeded**,
      2026-08-06 00:11 EDT, `Result: success`, exit 0, one second:
      `bootpages-20260806T041117Z.db — 4 pages, 2 accounts`.

      This was the item flagged as most likely to fail. The unit runs as
      the `bootpages` user under `MemoryDenyWriteExecute`,
      `SystemCallFilter=@system-service` and `ProtectProc=invisible` — a
      seccomp sandbox on a 32-bit big-endian PowerPC kernel, which is not
      a combination anyone tests upstream. It also proved the parts only
      waiting can prove: the timer fired on its own, `RandomizedDelaySec`
      jittered it to 00:11 rather than midnight, and `ReadWritePaths` held.

- [x] **backup.py backed up a real database on PowerPC** — 4 pages, 2
      accounts, verified against the source as it was written. Taken by
      deploy.sh rather than by the timer.

- [x] **`deploy.sh` ran end to end**, 2026-08-06, first attempt, clean.
      Every gate passed: 112 tests on PowerPC, a verified backup, the git
      update `103b37c..ad28f52`, compileall, unit reinstall, restart and
      verification. The SSH remote path is still unexercised.

- [ ] **A restore on the target.** Proven on x86; roadmap.md is right that
      a backup never restored is a hypothesis, and the hypothesis is
      per-machine.

- [ ] **The public path.** Everything has been verified either from the
      LAN or via `/etc/hosts` overrides. Let's Encrypt reached port 80
      from outside, so inbound works — but 443 has never been exercised
      from the internet. Load `https://page.babb.tel/` on a phone with
      wifi off.

### Configuration owed

- [ ] **DHCP reservation** for `192.168.2.55`. A lease change silently
      breaks both port forwards and DNS. Note the ethernet move will
      change the MAC and require redoing this.
- [ ] **Ethernet**, planned. Wireless ARP is unreliable enough that
      remote sessions drop mid-command.
- [ ] **Identify what listens on 44322 and 44323** — both bound to
      `0.0.0.0` on a machine facing the internet. `sudo ss -ltnp`.
- [ ] **Narrow the 9090 ufw rule** to the LAN. Cockpit is a root-capable
      console and currently has an ALLOW from Anywhere; only the absence
      of a port forward keeps it private.
- [x] **Merged into `main`** and deployed, 2026-08-06. Deploys are now
      plain `sudo /opt/bootpages/deploy.sh`.

### Known gaps, deliberately

- [ ] **No off-machine backup.** Both tiers live on one machine behind one
      power supply. They survive a bad edit and a dead disk; they do not
      survive the building. See
      `docs/superpowers/specs/2026-08-05-deploy-and-backup-design.md`.
- [ ] **No external drive yet.** `BOOTPAGES_BACKUP_DIR` and
      `BOOTPAGES_BACKUP_REQUIRE_MOUNT=1` are built and waiting; the
      SATA SSD is the right device for the system disk and the NVMe
      enclosure the right one for backups.
- [ ] **Dynamic IP.** `76.64.226.39` is residential and will move. When it
      does, `page.babb.tel` breaks until the GoDaddy record is updated. A
      small DDNS updater is owed.
- [ ] **No monitoring.** The service has a systemd watchdog; nothing
      watches the certificate, the disk, or whether pages still render.

---

## Backlog

### `inspect.babb.tel` — the interactive consumer

A static single-page app that fetches a page's JSON and renders it with
the things the on-page bar cannot do: split view with live hover-tracking,
click-to-copy node addresses, and a "watch this block" control that polls
`?ref=<id>` with `If-None-Match` and shows a 304 turning into a 200.

```
page.babb.tel  ── getPage/<path> + CORS ──▶  inspect.babb.tel
(PowerBook)         public JSON, no token       (GitHub Pages)
```

Separate for one reason: **it needs script, and published pages run under
`default-src 'none'`.** Keeping that policy is a product decision rather
than only a security one — "this document contains no code" is a claim a
consuming site can check in a header, and downgrading it to "only code the
store shipped" to gain a copy button is a bad trade.

Three properties make it cheap. It costs the PowerBook nothing beyond the
JSON it already serves; `babb.tel` already resolves to GitHub Pages, so
hosting is free; and it has no privileged access, so **anyone could write
a different one** — which is the claim the format makes about itself.

Everything it needs already exists: `getPage` on the pages origin with
CORS, `?ref=` returning a subtree with its own ETag, and capability pages
for declaring what a consumer implements. Nothing in the store has to
change.

### Smaller things

- **A DDNS updater** for the GoDaddy record, so a residential IP change
  does not take `page.babb.tel` down until somebody notices.
- **Author signatures.** `format.md` notes a digest proves two observers
  see the same bytes but not that the store is honest; signatures would
  close that, and the label scheme leaves room for them.
- **The memo lens**, which `format.md` describes and nothing parses yet.
  `tools/publish.py` converts a Markdown subset instead.

---

## Performance, as measured

On x86 during development. The read path was rebuilt around what these
numbers showed.

| | Before | After |
|---|--------|-------|
| View counter | 9.099 ms | 0.027 ms |
| Render | 0.421 ms | 0.0004 ms cached |
| Revalidated page on the wire | 14,366 bytes | 0 bytes |

The counter was the whole problem: under `synchronous=FULL` every page
view paid a physical fsync, sixteen times the cost of the entire read
path. Not measured on the G4 yet, where the spinning disk makes the
before-figure considerably worse and the after-figure identical.
