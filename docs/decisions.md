# Open decisions

What is not settled. Each entry states the question, why it matters, the
options, and a recommendation where there is one.

Decisions are cheap now and expensive once pages exist in the world.

Revision identity was the blocking one. It is now
[settled](format.md#revision-markers).

---

## 1. Nesting in the memo lens

**Question.** May a section contain another section in the human authoring
lens?

**Why it matters.** Flat is dramatically simpler to write, parse, teach and
round-trip. Nesting is more expressive and will eventually be wanted for
layout modules.

**Note.** This is a *lens* question, not a format question. The node tree
nests already, and fenced blocks and YAML can express nesting whatever the
memo lens does.

**Sharper than it first looked.** Container modules — `columns`, `tabs`,
`steps` — are exactly the case where an author wants nesting in the lens
they actually write in. See [children](format.md#children).

**Recommendation.** Keep the memo lens flat. Let depth be available in the
lenses whose audience will not be confused by it. The simple lens staying
simple is worth more than uniformity across lenses.

---

## 2. Composition depth

**Question.** May a page referenced by another page itself reference
others, and how far does a consumer follow?

**Why it matters.** The store never dereferences, so this is entirely a
consumer concern — but leaving it unstated means consumers will differ, and
a page that renders in one and hangs in another is a bad artifact.

**Recommendation.** The specification should state a recommended maximum
depth and require cycle detection, without mandating that any consumer
follow references at all.

---

## 3. Gating mechanism

**Question.** The first instance is gated. How, exactly — and can the API
stay Telegraph-compatible while it is?

**Why it matters.** `createAccount` is the entry point, and a Telegraph
client calls it with no extra parameters. Gating it necessarily breaks
something.

**Options.**

- **Network gating.** Bind to a private address or allowlist. The API stays
  byte-compatible; access is controlled outside it.
- **Invite parameter.** `createAccount` requires an additional argument.
  Only account creation breaks; every other method stays compatible.
- **Out-of-band minting.** `createAccount` is disabled entirely and tokens
  are issued by an admin tool. The public API stays clean.

**Recommendation.** Network gating first, since it costs nothing and breaks
nothing, with out-of-band minting as the administrative path. Keep the
invite-parameter option in reserve for a semi-open phase.

---

## 4. Core module registry

**Question.** Which modules ship as core?

**Why it matters.** Core modules are what Level 1 conformance means. Too
few and the format does nothing on its own; too many and every consumer has
an enormous surface to implement, which suppresses the ecosystem.

**Recommendation.** Deliberately unanswered until real pages have been
written. The registry should be discovered from use rather than designed in
advance, and the fallback rule means shipping late costs nothing — a module
that does not exist yet simply renders as its children.

---

## Settled, recorded here so they are not relitigated

- A page is a public value. Variation belongs to the consumer.
- The store never evaluates page content, and never dereferences.
- Three fields: `tag`, `attrs`, `children`. The syntax does not grow, and
  all three are always present — an optional field is a way for two
  implementations to write one page differently.
- One children rule: an unsupported node renders its children in document
  order; what a supported node does with them is the module's business.
  Modules are either leaf or container, declared by the site.
- Attribute values are strings or comma-separated lists of strings. A
  scalar may be typed by the module that declares it; structure goes in
  `children`. Not JSON — canonicalisation and the memo lens both depend on
  it, for reasons unrelated to coordinating module authors.
- Referencing has three mechanisms — inline `children`, external `source`,
  in-page `id`/`ref` — and choosing between them is the same act as
  deciding what is public.
- Media `src` is a pointer the store never proxies, so the media host sees
  every reader.
- Tables are nested lists, chosen for fallback fidelity over compactness.
  No new vocabulary; the memo lens accepts pasted tab-separated text and
  pipe tables.
- Capability pages: a site publishes what it welcomes, as a bootpage.
  Optional, advertising rather than contract, and the mechanism by which a
  de-facto registry converges.
- A canonical form exists, and the canonical bytes are what the store
  holds. Normalising on write is the only transformation a store may make.
- Two revision markers: a `revision` counter for ordering, a `digest` for
  content identity. They answer different questions and neither replaces
  the other.
- Digests carry a label naming both the canonicalisation recipe and the
  hash function (`bp1-sha256:`). Never a bare hex digest.
- Pinning is the consumer's job and needs nothing further from the store.
- Telegraph compatibility is permanent, and is a consequence of the node
  shape rather than a layer.
- Five attribute families: `require-`, `prefer-`, `on-`, `meta-`,
  unprefixed.
- Preferences are advisory, semantic, and removable.
- Attribute values are opaque.
- Reserved namespaces, with vendor prefixes for everyone else.
- Pages are standalone; references are declarations, not includes.
- Selective presentation is a routing mechanism, not confidentiality.
- Confidential content never enters a page.
