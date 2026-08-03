# Bootpages

**A store for portable declarative manifests — public, permanent documents
that consuming sites can treat as capability.**

A bootpage is not a web page. It is a description of an experience: what
parts it has, what each part requires, where its data comes from, and what
its author would prefer it to look like. It carries no code, no secrets and
no per-viewer state. A site that receives one decides what to do with it,
for whoever is asking.

The point is that you publish once, and every site that consumes the page
changes with it — without anyone touching server code, redeploying, or
shipping a file.

---

## What a page looks like

Underneath, a page is a list of nodes. Every node is the same three fields:

```json
{"tag": "gallery",
 "attrs": {"source": "#photos", "prefer-layout": "grid, list"},
 "children": [{"tag": "p", "children": ["Twelve photographs from the site."]}]}
```

`tag` says what it is. `attrs` say how it is configured. `children` are
what a consumer shows if it does not understand the tag.

Nobody has to write that by hand. The same page, in the lens most people
will use:

```
title: Q3 Onboarding
audience: new staff

## Welcome

Just write. Prose is prose — no markup, no keys, nothing to learn.

## Expenses
require-role: finance
source: https://finance.example.internal/q3
prefer-layout: table, list

If you have finance access, this section loads live figures.
Otherwise you are reading this sentence, which is the fallback.
```

Headings open sections. `key: value` lines beneath a heading configure it.
Everything after the blank line is content. If that looks like a memo, that
is deliberate — the structure of a business document and the structure of a
manifest are the same structure.

---

## Three parties

Most document systems have two: an author and a reader. Bootpages has
three, and almost every design question is answered by asking whose job
something is.

| Party | Owns |
|---|---|
| **Author** | meaning — what the page says and requires |
| **Store** | durability — holding and serving the page, faithfully and neutrally |
| **Consumer** | behaviour — deciding what to render, execute, fetch, and show to whom |

The store never evaluates a page. The consumer never edits one. The author
never learns who read it.

---

## The one law

> **A page is a public value. Anything that varies by viewer, time, or
> secret belongs to the consumer.**

Everything else in this project is a consequence of that sentence.

Because a page is a value, it can be cached, hashed, pinned, mirrored,
diffed, signed and served identically to everyone — which is what makes it
usable as infrastructure rather than as a feature of one website.

Because variation belongs to the consumer, a single page can drive a
permission-aware interface for an entire organisation while containing no
privileged data at all.

---

## What it is not

- **Not a runtime.** The store never executes page content. It is a
  repository, not a compute platform — the distinction between hosting a
  program and running one.
- **Not a CMS.** It has no themes, no templates, no rendering opinions.
  Appearance belongs to whoever displays the page.
- **Not a website builder.** A bootpage has no layout, only structure and
  preference. What it looks like depends on where it lands.
- **Not private.** Every page is public and permanent. Confidential
  information does not go in a page; a page points at where it lives.

---

## Telegraph compatibility

Bootpages is API-compatible with Telegraph and intends to stay that way
permanently. The node shape is the same three fields, so a Telegraph page
*is* a bootpage in which every tag happens to be an HTML tag. No conversion
layer exists because none is needed.

This is not sentiment. It means every Telegraph client already works, and
it gives the project a large, mature conformance suite it did not have to
write.

---

## Sites describe themselves

A consuming site publishes a [capability page](docs/capability.md) listing
the modules it implements and what each one takes — and that page is itself
a bootpage.

So an authoring tool needs no built-in knowledge of any site. Paste a
site's address and the editor can complete module names as you write a
heading, offer that module's declared attributes on the lines beneath, and
show you what a site *without* that module will display instead.

The descriptions in a capability page are its `children`, which means one
set of bytes is the documentation, the helper text in an editor, and the
fallback rendering all at once. They cannot drift apart.

---

## Documentation

| | |
|---|---|
| [Vision and principles](docs/vision.md) | why this exists, and the reasoning that constrains it |
| [Format](docs/format.md) | the node model, attribute families, canonical form, and lenses |
| [Capability pages](docs/capability.md) | how a site publishes what it welcomes |
| [Running it](docs/running.md) | terminal, systemd, and the gate |
| [Conformance](docs/conformance.md) | what it means to *support* bootpages |
| [Open decisions](docs/decisions.md) | what is not settled, and why |
| [Roadmap](docs/roadmap.md) | the build, in order |

---

## Status

**Early, and it runs.** A localhost instance publishes pages, renders them,
and speaks the whole API.

```sh
python3 -m bootpages.server        # http://127.0.0.1:8080
python3 -m pytest
```

As a service: `sudo ./install.sh`. No venv, no `.env`, no secret to place —
see [running it](docs/running.md).

**It binds to `127.0.0.1` and defaults to `admin` mode** — `createAccount`
is refused, and tokens are minted from a shell. `invited` and `open` are
the other two modes. The editor and published pages are served on separate
origins so that a script inside a page cannot reach the tokens the editor
stores.

No dependencies — standard library only, `http.server` and `sqlite3`. A
store whose promise is durability should be runnable in ten years by
anyone with a Python interpreter and no working package index.

| | |
|---|---|
| format, canonical form, digest | done |
| store, all eight API methods | done |
| public rendering, view counting | done |
| the editor, account shelf, first-run | done |
| account modes, invites, admin CLI | done |
| origin split and security headers | done |
| capability pages | designed, not built |

The reference renderer implements **no modules**, deliberately. That makes
it a [Level 0 consumer](docs/conformance.md), and it means every non-core
tag exercises the fallback path on every request — which is what a page
should look like on a site that has never heard of it.

See [open decisions](docs/decisions.md) for what is still unsettled; none
of it blocks building. Revision identity was the one that did, and it is
settled: a `revision` counter for ordering, a labelled `digest` for content
identity, and a canonical form so two parties anywhere can confirm they are
looking at the same page.
