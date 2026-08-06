# Addressable nodes, machine access, and the curtain

**Status:** design, 2026-08-06
**Scope:** `id` uniqueness, `getPage` on the pages origin with CORS,
subtree addressing with scoped ETags, and alternate lenses.

---

## Why

The format already has node identity — `format.md:294` defines `id` and
`ref` as unprefixed structural attributes, resolved within a page. What it
does not have is a way for anything outside the page to *use* that
identity: to fetch one block, to notice when that block and only that
block changed, or to see the structure without reading the JSON by hand.

The goal is subscription to specific page elements. The realisation behind
this design is that almost none of it needs new concepts.

| Need | Mechanism | Status |
|---|---|---|
| Address a sub-part | `id` | in the format |
| Verify identity | `digest` over canonical bytes | in the store |
| Order changes | `revision` | in the store |
| Detect change cheaply | ETag → 304 | shipped 2026-08-05 |
| Discover capability | capability pages | specified |

What is missing is a **scoped** digest and a route to reach it. A subtree
is a node list, and `fmt.digest()` already takes a node list, so the
digest of one block costs nothing new.

---

## Part A — addressable nodes and machine access

### A1. `id` becomes unique within a page

There is no uniqueness validation today. None in `_attrs`, none in
`normalise`, none in the store, none in the docs. Three nodes may carry
`id: sales` and nothing complains; `ref: #sales` is then undefined.

That is tolerable for `ref` and unacceptable for subscription, and the
asymmetry is the whole argument. A broken `ref` fails visibly — a block
points at nothing and someone notices. An ambiguous subscription fails
**silently and in the wrong direction**: an agent watches `#sales`,
resolution picks the first match, the author later edits the second, and
the agent sees no change. It does not error. It stops being true.

So: `normalise` rejects a duplicate `id` anywhere in the tree, naming both
paths. Validation belongs there because that is already the moment the
store canonicalises on write.

`id` is additionally constrained to `[A-Za-z0-9_-]{1,64}`, because it has
to survive being a URL fragment and a query parameter. Anything else is
rejected at write time rather than escaped at read time.

**This is a breaking change for any page that already has duplicates.**
There are none on the reference instance. The check runs on write only, so
existing pages are never re-validated and cannot become unservable.

### A2. `getPage` on the pages origin, with CORS

Today `get_pages` explicitly refuses it:

```python
if not path or path in api.METHODS or path.startswith("getPage/"):
    return self.not_found()
```

That guard was right when the pages origin served only rendered documents.
It is reversed deliberately, and the reasoning is the same one that
produced the two origins in the first place: **public read data belongs on
the untrusted-content origin, not the one holding tokens.** A third-party
consumer should never have a reason to send a request to the editor.

- `GET /getPage/<path>` on the pages origin, no token, `return_content`
  supported. `_get_page` already reads no `access_token`.
- `Access-Control-Allow-Origin: *` on that response only. The data is
  already public to anyone who can fetch it; CORS only lets a browser
  script read what curl could already get.
- **The editor origin keeps its own copy**, because `editor.js:781` calls
  it. Same-origin, so no CORS header there. The pages origin is the
  documented public interface; the editor's is an implementation detail.
- Namespace protection is preserved: a page whose path collides with an
  API method name still 404s rather than being shadowed.

No other method is exposed on the pages origin. Not `getPageList`, which
takes a token, and not anything that writes.

### A3. `?ref=<id>` — a subtree, with its own ETag

```
GET /getPage/Bootpages-08-06?ref=sales
```

Returns the subtree rooted at the node carrying `id: sales`, as a node
list, with its own digest computed by the existing `fmt.digest()`.

The ETag for that response is scoped to the subtree, not the page. This is
the whole point: an agent polling `?ref=sales` gets **304, zero bytes**
until that block changes, and is not woken by edits elsewhere on the page.

- `ref` names an `id`, not a position. Positional paths like `/2/0` are
  rejected — they break the moment an author inserts a paragraph, which
  makes them worthless as subscription targets. Requiring an explicit `id`
  makes a subscription target a deliberate authoring act that survives
  reordering.
- An unknown `ref` is `REF_NOT_FOUND`, not an empty result. A subscription
  to something that no longer exists must be loud.
- The subtree ETag combines the page revision with the subtree digest, so
  it changes if the block changes and stays put if it does not.

### A4. No webhooks

Push means the store holds per-subscriber state and owes delivery. That is
a materially heavier promise than "here are some bytes, unchanged since
you last asked", and on a PowerBook facing the public internet the
difference is the whole design. Conditional GET is the subscription
mechanism. If polling ever proves insufficient, that is a separate spec.

---

## Part C′ — the curtain

An alternate view of the same page, served by the same renderer, with
**no script**.

```
/Bootpages-08-06              the HTML lens (today)
/Bootpages-08-06?lens=tree    the structure, rendered as HTML
/Bootpages-08-06?lens=json    the wire format
```

`format.md` already calls these lenses: five projections of one canonical
node list, *"never dialects with their own semantics."* So this ships an
existing concept rather than inventing a feature.

The tree lens shows, per node: its tag, whether this consumer implements
that tag or fell back to children, its attributes grouped by family
(`require-`, `prefer-`, `on-`, `meta-`, structural), and its `id` if it
has one — as an anchor, so a node with an `id` is visibly addressable and
one without is visibly not. That teaches the format better than
documentation does.

It needs no script, so it lives happily under `default-src 'none'` on the
pages origin. It gets the same ETag treatment as the HTML lens, keyed on
revision, and the same render cache keyed by `(path, revision, lens)`.

---

## Part B — the inspector, later

Only what genuinely needs a client: hover-tracking, live highlighting,
interactive subscribe controls. Those need script; script cannot run on
the pages origin; that is the entire reason B is separate.

When built, it is a **static page with no server**, fetching JSON through
A2's CORS endpoint. `babb.tel` already resolves to GitHub Pages, so it can
be hosted there at no cost and place no load on the PowerBook.

Out of scope for this cycle. A2 is what makes it possible for anyone to
build, which is a stronger position than shipping the only viewer.

---

## Testing

- Duplicate `id` is rejected on write, naming both paths.
- An `id` outside the permitted charset is rejected.
- A page with no `id` anywhere still publishes.
- `?ref=` returns exactly the subtree, and its digest matches
  `fmt.digest()` of that subtree computed independently.
- Editing a *different* block leaves the subtree ETag unchanged; editing
  the referenced block changes it.
- Unknown `ref` gives `REF_NOT_FOUND`.
- CORS header present on the pages origin's `getPage`, absent on rendered
  pages.
- `getPageList` and every writing method remain unreachable on the pages
  origin.
- Both lenses render, carry ETags, and produce a 304 on revalidation.

---

## Out of scope

- Part B, the interactive inspector.
- Author signatures, which `format.md` notes would close the honesty gap
  a digest alone leaves open.
- Any push or webhook delivery.
