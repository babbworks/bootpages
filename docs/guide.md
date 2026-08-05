# How bootpages works, and why it is shaped this way

This is one document doing two jobs: an explanation of the system and a
guide to running it. The two are interleaved on purpose. Almost every
operational rule here follows from a design decision, and an operator who
knows only the rule will eventually break the decision without noticing.

---

## The problem

Publishing a document to the web means choosing, early and permanently,
what it will look like. HTML is markup: it encodes presentation. A page
carries its own layout, its own assumptions about screen size, its own
decisions about what to show a reader who lacks permission to see part of
it. Every site that wants to display your document must either accept
those decisions or parse them out again.

That is fine for a website. It is wrong for a document that many different
sites want to present, each to its own readers, each in its own idiom.

A bootpage is not a web page. It is a description of an experience: what
parts it has, what each part requires, where its data comes from, and what
its author would prefer it to look like. It carries no code, no secrets,
and no per-viewer state. A site that receives one decides what to do with
it, for whoever is asking.

The point is that you publish once, and every site that consumes the page
changes with it, without anyone touching server code, redeploying, or
shipping a file.

---

## Three fields, and nothing else

Underneath, a page is a list of nodes. Every node has the same three
fields.

```
{"tag": "gallery",
 "attrs": {"source": "#photos", "prefer-layout": "grid, list"},
 "children": [{"tag": "p", "children": ["Twelve photographs."]}]}
```

`tag` says what it is. `attrs` say how it is configured. `children` are
what a consumer shows if it does not understand the tag.

A node may also be a bare string, which is text. That is the whole format.

The narrowness is the feature. There is no attribute that means *style*,
no field that carries markup, no escape hatch into HTML. A format with an
escape hatch is a format everyone escapes through, and within a year the
documents are HTML again with extra steps.

---

## The one law

**A consumer that does not understand a tag renders its children.**

That single rule is what makes the format extensible without a
committee. Anyone may invent a tag. A site that implements it shows the
rich version; a site that does not shows whatever the author put inside as
a fallback. Neither has to know about the other.

So the fallback is not an error path. It is the normal path, taken by most
consumers for most novel tags, and it is where an author does their real
work: deciding what someone should see when the clever version is
unavailable.

An author who would rather show nothing than an approximation says so:

```
{"tag": "gallery", "attrs": {"on-unsupported": "omit"}, "children": [...]}
```

and gets nothing. That is the only way to suppress the law, and it must be
asked for.

The reference renderer in this repository implements **no** modules at
all. That is deliberate rather than unfinished. It makes this a Level 0
consumer, it exercises the fallback path on every non-core tag, and it is
the honest starting point for a registry that should be discovered from
use rather than declared in advance.

---

## Core tags

The tags every consumer must understand:

```
a  aside  b  blockquote  br  code  em  figcaption  figure
h3  h4  hr  i  iframe  img  li  ol  p  pre  s  strong  u  ul  video
```

Note what is missing. There is no `h1` and no `h2`. The renderer emits the
`h1` for the page title itself, so content headings begin below it at
`h3`. A document that uses `h2` is not rejected; `h2` is simply an unknown
tag, and the one law applies, so its children render as bare text. This
surprises people once.

Tags outside this set are modules. Anyone may define one. `x-` is reserved
for everyone outside the specification, on the reasoning that led HTML to
demand a hyphen in custom element names: reserve the plain space early and
the two never collide.

---

## Attributes say what a consumer owes

Attributes are grouped into families by prefix, and the family decides
what a consumer is obliged to do when it cannot honour one.

**`require-`** is a condition. `require-role: finance` means this node is
for readers with that role. A consumer that cannot evaluate the condition
must not show the node. Failing closed is the only safe direction: a
consumer that shows a section it could not check has leaked it.

**`prefer-`** is advice. `prefer-layout: table, list` is a ranked list of
what the author would like. A consumer picks the first it can do and
ignores the rest. Ignoring a preference entirely is always legal.

**`on-`** is behaviour at the boundary, like `on-unsupported: omit`.

**`meta-`** is information for machines that is not for display.

The families exist so that a consumer meeting an attribute it has never
seen still knows what to do with it. `require-anything` fails closed;
`prefer-anything` is advisory. Forward compatibility comes from the prefix,
not from a lookup table that has to be kept current.

---

## Identity: canonical bytes and digests

A page is a value. Its identity is a digest of its canonical form.

Canonicalisation is the single transformation the store performs on write.
It preserves meaning exactly and produces one byte sequence for what would
otherwise be many equivalent encodings: key order, whitespace, unicode
form. Without it a digest would be a fact about a serialiser rather than
about a document.

The canonical bytes are **stored**, not recomputed on read. Libraries and
languages change over the decades this is meant to survive; a digest that
drifts is not an identity.

This was verified across architectures rather than assumed. The same
content, canonicalised on 32-bit big-endian PowerPC and on x86_64,
produces byte-identical output and the same digest. Page identity does not
depend on the machine that computed it, which is what makes a digest worth
citing.

---

## Permanence, and what it costs

Three promises, each with a cost paid somewhere else in the system.

**A path is permanent.** A page's address is what consumers pin, embed and
cite, so it can never be reassigned or reused, not even after the page is
hidden. There is no rename. A short vanity URL is a redirect in the
webserver, never a second identity for the document.

**An edit replaces the page wholesale.** There is no partial edit and no
undo. This is what makes republishing safe to retry: writing the same
content twice is the same as writing it once, so a status page or a
generated manifest can be republished on a timer without risk.

**Nothing is deleted.** Hiding removes a page from listings; the path stays
spent.

The cost of wholesale replacement with no undo is that backups stop being
operational hygiene and become a product requirement. If a client is
promised permanence and a single mistaken `editPage` can overwrite a
document irrecoverably, then the backup *is* the promise. That is why the
backup machinery in this repository is more careful than the size of the
project would suggest.

---

## The store

SQLite, one file, no server alongside this one.

```
/var/lib/bootpages/bootpages.db
```

Backing this service up is one file, and restoring it is that file back.
For a store whose entire promise is that the bytes come back, that shape is
worth more than any amount of operational cleverness.

With one caveat that is not small: **you cannot copy that file with `cp`
while the service is running.** The database runs in WAL mode, so a
committed row lives in a `-wal` sidecar until a checkpoint. A plain copy
captures a torn database that looks fine until the day it is needed. Use
the tooling, which takes an online snapshot through SQLite's own backup
API and verifies it against the source as it writes.

Pages are written with `synchronous=FULL`. Every commit waits for a
physical flush to the disk. That is expensive and it is correct: a page
acknowledged and then lost to a crash is a broken promise, not a
performance question.

---

## Why page views used to be slow

The counter is the interesting exception, and the story is worth telling
because the fix was not the obvious one.

Every page view incremented a view counter, which is a write, which under
`synchronous=FULL` meant a physical fsync on the read path. Measured on an
SSD: 9.099 ms for the counter against 0.506 ms for the entire read,
lookup, parse and render included. Sixteen times the cost of the work the
reader actually asked for. On a spinning disk the counter costs a full
platter rotation and, worse, serialises, because SQLite takes one writer at
a time.

The obvious fix is faster hardware. It does not work: fsync is bound by
rotational latency and flush behaviour, not by the processor, and the
machine that produced those numbers already had an SSD.

The actual fix is that `synchronous` is a per-connection setting. Views are
counted on a second connection at `NORMAL`, which in WAL mode does not
flush on every commit. Same write, 0.027 ms, a 337-fold difference. This is
not the corruption risk it sounds like: WAL plus `NORMAL` cannot corrupt
the database, it can only lose the last few commits to a power cut. Losing
three view counts is nothing. Pages keep `FULL` on the other connection,
because losing a page is not nothing.

Two more changes followed from the same principle of not doing work on the
read path:

**Rendered documents are cached by path and revision.** A page is a value
and cannot change without its revision changing, so the cache is correct by
construction rather than by invalidation logic anyone has to remember to
write. Rendering falls from 0.42 ms to 0.0004 ms.

**Pages carry an ETag**, so a reader whose copy is still current gets a 304
with no body: zero bytes instead of fourteen kilobytes, and no render at
all.

The ETag is keyed on the **revision**, not the digest, and the reason is a
trap worth naming. The digest covers content only. A title-only edit
leaves it unchanged, so an ETag built from the digest would serve a stale
title to every cached reader indefinitely, invisibly. The revision moves on
every edit including that one.

---

## Two origins, and the one thing that can break it

The editor and published pages are served on **different ports**, and that
is not cosmetic.

The editor keeps author tokens in browser storage. Published pages are
untrusted content. Same-origin policy is what stops a script inside a page
reading that storage, and it is enforced by the browser, keyed on origin,
which is scheme plus host plus port. So a different port is enough, and one
process serves both.

Behind a reverse proxy this changes in a way that is easy to miss. Once TLS
is terminated the browser cannot see the ports at all, so **the separation
comes to live entirely in the two hostnames**. Serve the editor and the
pages under one name on different paths and you have merged two origins the
whole design keeps apart.

Nothing in the application can detect this. Its configuration check
compares the addresses it binds, which stay distinct on 8080 and 8081
whatever the proxy does in front. It will report a healthy two-origin
configuration and be wrong. This is one of the few places in the system
where correctness lives in a config file that the software cannot
validate, so it is worth testing directly: fetch the pages hostname and
confirm you do not get the editor.

Layered underneath, the pages origin is served with a content security
policy of `default-src 'none'`, and the renderer emits no script under any
circumstance: attributes come from a fixed allowlist per tag, URLs are
checked against a scheme allowlist, and `javascript:` and `data:` are
refused. Because the page is data rather than markup, there is no
sanitiser to get wrong. There is simply no path by which author-supplied
text becomes markup.

---

## Accounts, tokens and invites

Three modes decide how an account comes into being. The mode is enforced
in the store, not by a client choosing not to show a button, so a request
that skips the first-run screen gets exactly the same answer as one that
does not.

**`admin`** is the default and the tightest. Account creation is refused
outright; the operator mints tokens from a shell.

**`invited`** accepts a one-time invite code.

**`open`** lets anyone who can reach the port mint an account.

The distinction between a token and an invite is the reason the middle
mode exists. A token is a permanent publishing credential with no expiry:
intercepted in transit, it lets someone publish as you, forever. An invite
is not a credential to an account, it is a one-time right to create one.
Intercepted, the worst that happens is a stranger creates their own
account, once, and only until it is used or expires. It is the difference
between handing over your keys and handing over a visitor's pass.

A fresh instance in `admin` mode would otherwise be one where nobody can
write anything, so the server mints exactly one account on first run
against an empty store and prints its token. Anyone able to start the
server already has shell access and could mint a token anyway, so this
removes friction without opening a hole. It never happens again once any
account exists.

The token is shown **once**. A page whose token is lost is orphaned
permanently.

---

## Running it

```
python3 -m bootpages.server
```

No dependencies. Standard library only. There is nothing to install and
nothing to activate, which is the property that makes it reasonable to run
this on unusual hardware.

As a service, the install is a user, a copy, and a unit file. No venv, no
`.env`, no configuration file, and no secret to place.

One setting cannot be worked out by the process and must be given:

```
BOOTPAGES_PAGES_URL=https://page.babb.tel
```

Every API response reports where a published page lives, and those links
are built from this value. Behind a proxy the server sees only loopback
HTTP while the world sees HTTPS on a name it has never been told. Leave it
unset on a public instance and the API hands out links to `127.0.0.1`
while looking perfectly healthy.

The service binds to loopback and refuses a public bind unless told
explicitly. That flag is not a security control; it is a speed bump placed
where an accident would otherwise be silent. Put a reverse proxy in front
and leave the bind alone.

---

## Updating, and why the deploy script is fussy

The naive update is a pull and a restart. That is fine until the pull
brings something that will not start and there is no copy of the database
from before it.

The deploy script gates each step on the last: tests, then a verified
backup, then a free-space check, then the code, then a byte-compile check,
then the unit, then the restart, then a check that the service actually
answers. Anything that fails aborts and prints what was and was not
changed, along with the backup to roll back to. Nothing falls back,
because a deploy that half worked is worse than one that refused: the
second tells you where you are.

Given a hostname it copies itself to that machine and runs there, so the
tests run on the architecture being deployed to. It also runs them locally
first, and the reason is specific: the editor's test harness needs Node,
Node has no 32-bit PowerPC build, so on that target the test guarding the
largest file in the project silently skips while the suite still reports
success. One machine covers the editor, the other covers the
architecture. Neither alone is the suite.

The script reinstalls the unit but never the drop-in that holds the mode
and ports, because the install script was told those and the deploy script
was not.

---

## Backups

Daily on a timer, plus one before every deploy, thirty kept, each verified
against the source as it is written. A backup that has never been read is
a hypothesis, and checking costs milliseconds.

Deploy-triggered backups alone are not enough, and the reason is about
where the risk actually accrues. `editPage` replaces a page wholesale with
no undo, and that danger grows with *authoring*, not with deploying. On an
instance published to daily and deployed to monthly, a deploy-only backup
is a month stale on its worst day.

The timer sets `Persistent=true`, which is load-bearing on a laptop.
Without it, a backup scheduled while the lid is shut does not run late, it
does not run at all, silently, and the first evidence is a gap in the
directory on the day one is needed.

Restoring refuses while the service is running, because SQLite will
happily let two processes disagree about what a file contains, and it
moves the replaced database aside rather than overwriting it. A restore is
usually done under pressure, and the wrong backup is a live possibility.

An external drive is configured by pointing the destination at its mount
and requiring that the mount is real. With the drive absent a backup
**fails** rather than falling back to the internal disk. A path under a
mountpoint exists whether or not anything is mounted on it, so falling
back is how you come to believe you have months of external backups that
were never written.

One gap is recorded honestly rather than left implicit: there is no copy
off the machine. The tiers described here survive a bad edit and a dead
disk. They do not survive the building.

---

## Running it on very old hardware

The reference deployment is a PowerBook G4: a 1.5GHz 7447A with AltiVec,
2GB of memory, 32-bit and big-endian, running current Debian. The whole
suite passes there in three seconds.

Some of what this teaches generalises to any weak machine.

**The Go ecosystem is unavailable.** Go has never targeted 32-bit
`powerpc`. That rules out Caddy, and also cloudflared, Tailscale and frp
if a tunnel was the plan. nginx is C and fine.

**Cipher order should be set by the server, against the usual advice.**
The modern default is to let the client choose, which assumes the server
has AES-NI. This one has AltiVec, which OpenSSL uses far less effectively,
so ChaCha20-Poly1305 is materially cheaper here than AES-GCM. ECDSA
certificates rather than RSA, for the same reason: handshakes are the most
expensive thing the machine does.

**Let the proxy do the boring work.** Static files never reach Python.
Compression runs at a low level, which gets most of the ratio for a
fraction of the processor. Proxy buffering is on, so a reader on a bad
connection occupies the proxy's memory rather than one of the server's
threads.

**Rate limits matter more than usual.** The upstream serves a thread per
connection and SQLite takes one writer at a time; neither degrades
gracefully.

None of this required changing the application. It required knowing which
of its costs were bound by the processor, which by the disk, and which by
neither.
