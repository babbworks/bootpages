# What is done, and what is not

Live state of the `page.babb.tel` deployment. Updated as things land.

Last updated 2026-08-05.

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

---

## Not yet done

### Tests that have never run

- [ ] **`bootpages-backup.service`** has never executed. Its systemd
      sandbox — `MemoryDenyWriteExecute`, `SystemCallFilter=@system-service`,
      `ProtectProc=invisible` — has never run on a PowerPC kernel. Most
      likely thing on this list to fail.

      ```sh
      sudo systemctl start bootpages-backup
      sudo -u bootpages python3 -m bootpages.backup list --dest /var/backups/bootpages
      ```

- [ ] **`deploy.sh` has never run end to end anywhere.** Guards are
      tested; the git update, unit reinstall, restart and verification are
      not. The SSH remote path is entirely unexercised.

      ```sh
      sudo /opt/bootpages/deploy.sh local deploy-and-backup
      ```

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
- [ ] **Merge `deploy-and-backup` into `main`** once the two untested
      pieces above pass. Then `deploy.sh` stops needing a ref argument.

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
