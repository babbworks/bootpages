# Putting this on the internet

Bootpages binds to loopback and stays there. Everything below is about the
thing in front of it.

The target this was written against is a PowerBook G4 running Debian ports
on 32-bit PowerPC, serving `page.babb.tel`. Most of it generalises; the
parts that do not are marked.

---

## The shape

```
              443                    8080   editor      tokens live here
  internet ──────► nginx ──┬──► 127.0.0.1
                           │
                           └──► 127.0.0.1:8081   published pages
```

Two names, two origins:

| Name | Upstream | Carries |
|------|----------|---------|
| `page.babb.tel` | `127.0.0.1:8081` | published pages — untrusted |
| `edit.page.babb.tel` | `127.0.0.1:8080` | the editor — author tokens |

**The separation is load-bearing and, after TLS termination, it lives
entirely in those two names.** bootpages keeps the editor and pages on
different ports because the editor stores author tokens in the browser and
published pages are untrusted content; same-origin policy is what stops the
second reading the first. An origin is scheme + host + port, and nginx
removes the ports from the browser's view — so serving both under one name
on different paths merges two origins the design keeps apart.

Nothing will appear to break when you do. `config.py` compares the
addresses bootpages *binds*, which stay distinct on 8080 and 8081 whatever
nginx does in front, so it will report a healthy two-origin configuration
and be wrong. There is no check that catches this. Use two names.

---

## What will not run on a G4

Go has never targeted 32-bit `powerpc` — only `ppc64` and `ppc64le`. That
rules out, on this machine:

- **Caddy.** Use nginx.
- **cloudflared, Tailscale, ngrok, frp.** If you need a tunnel because the
  connection is behind CGNAT, what is left is C: WireGuard, or an SSH
  reverse tunnel to a cheap VPS that fronts the traffic.

Check whether you actually have a routable inbound address before designing
around one.

---

## Certificates

DNS-01, not HTTP-01. It needs no inbound port 80, renewal does not depend on
the service being reachable, and it can issue wildcards.

**A wildcard is single-label.** `*.babb.tel` matches `page.babb.tel` but
**not** `edit.page.babb.tel`. Either issue `*.page.babb.tel` as well, or name
both hosts explicitly on one certificate:

```sh
certbot certonly --dns-<provider> \
  -d page.babb.tel -d edit.page.babb.tel \
  --key-type ecdsa --elliptic-curve secp256r1
```

`--key-type ecdsa` is not a detail here. ECDSA handshakes are markedly
cheaper than RSA, and on this hardware handshakes are the most expensive
thing the machine does.

---

## nginx

`bootpages.nginx.conf` in the repo root. Substitute the two names, then:

```sh
sudo cp bootpages.nginx.conf /etc/nginx/sites-available/bootpages
sudo ln -s /etc/nginx/sites-available/bootpages /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

What is in it and why, beyond the two origins:

- **ChaCha20 before AES, with server cipher order enforced.** The usual
  advice is to let the client choose, which assumes the server has AES-NI.
  A G4 does not, so AES-GCM costs materially more here than
  ChaCha20-Poly1305. Hardware overrules convention.
- **Session cache and tickets on.** Resumption avoids a full handshake, and
  a full handshake is the expensive part.
- **`/static/` served by nginx.** A stylesheet has no business occupying one
  of the upstream's threads.
- **`gzip_comp_level 1`.** Most of the ratio for a fraction of the CPU.
- **`proxy_buffering on`.** Lets nginx absorb slow clients, so a reader on a
  bad connection occupies nginx memory rather than one of
  `ThreadingHTTPServer`'s threads.
- **Rate limits.** The upstream is a 2004 laptop; SQLite takes one writer at
  a time and neither degrades gracefully.
- **No `Content-Security-Policy`.** `server.py` already sets one per role.
  Two policies means the browser enforces the intersection, which is how a
  policy tightens by accident.
- **HTTP/2 as a `listen` parameter**, not `http2 on;`. That directive
  arrived in nginx 1.25.1 and bookworm ships 1.22.1, where it fails
  `nginx -t` as unknown.

---

## The setting that is easy to miss

```
BOOTPAGES_PAGES_URL=https://page.babb.tel
```

Every API response reports where a published page lives, and `api.py` builds
those links from this value. The server sees only loopback HTTP and cannot
work out the name the world uses, so if this is unset a public instance
hands out `http://127.0.0.1:8081/...` links — and looks perfectly healthy
doing it.

`install.sh` asks for it. Set it there, pass `--pages-url`, or put it in the
drop-in at `/etc/systemd/system/bootpages.service.d/instance.conf`.

---

## Order of operations

1. DNS: `page.babb.tel` and `edit.page.babb.tel` at the machine.
2. `apt-get install nginx certbot python3-pytest` — the last is needed by
   `deploy.sh`, not by the service.
3. `git clone` to `/opt/bootpages`, then `sudo ./install.sh --pages-url
   https://page.babb.tel`. Mode stays `admin` unless you mean otherwise.
4. Confirm it answers on loopback before involving nginx:
   `curl -I http://127.0.0.1:8081/`
5. Certificates, then nginx, then `nginx -t`.
6. Check the two origins are genuinely separate — open both names and
   confirm the editor is not reachable under the pages name.
7. `systemctl list-timers bootpages-backup` to confirm the backup timer
   armed.

Leave the mode at `admin` while any of this is in doubt. It refuses account
creation outright, so an instance that is reachable before you meant it to
be is embarrassing rather than permanent.
