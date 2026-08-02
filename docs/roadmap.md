# Roadmap

The build, in order, with the reasoning for the order.

Effort figures assume the [open decisions](decisions.md) do not churn.
Revision identity is settled — see [revision markers](format.md#revision-markers).

---

## Why this order

Each phase constrains the next. The content model decides the storage
format, the storage format decides the API, and the API decides what a
consumer can rely on. Building them out of order means rewriting the
earlier ones.

There is one exception to "build it when you need it": **anything that
becomes impossible to add later comes first.** Revision identity and
internal delete are both in that category — cheap now, unfixable once
pages exist that other people depend on.

---

## Phase 0 — Ground · 1 day

The repository, this documentation, and a conformance harness before there
is anything to conform.

- Repo, licence, contribution notes.
- A stub server answering the eight methods with fixtures.
- An existing Telegraph client pointed at the stub.

**Done when** a real, unmodified Telegraph client talks to the stub and
gets sensible answers. That client becomes the conformance suite for every
later phase, and it did not have to be written.

---

## Phase 1 — Format · 2–4 days

The node model made real: parse, validate, canonicalise, render.

- Canonical node list, and validation against the reserved namespaces.
- The five attribute families, with family determined by prefix.
- Fallback rendering, including `on-unsupported: omit`.
- The three tests from [conformance](conformance.md) — strip, blind,
  opacity — as an automated suite.
- The memo lens parser, including pasted tab-separated and pipe tables, and
  a YAML lens.

**Done when** a page round-trips tree → memo → tree unchanged, and the
three conformance tests run in CI.

**This is the risk surface.** Everything downstream inherits its
correctness from here, and format mistakes are the ones that cannot be
fixed later without breaking stored pages. It deserves property-based
tests, not example-based ones.

---

## Phase 2 — Store and API · 3–5 days

The eight methods, with persistence.

`createAccount` · `getAccountInfo` · `editAccountInfo` ·
`revokeAccessToken` · `createPage` · `editPage` · `getPage` · `getPageList`

- Accounts, tokens, pages, permanent paths.
- Canonicalisation on write, storing canonical bytes.
- `revision` counter and labelled `digest` on `getPage`.
- View counting, exposed as the `views` field on `getPage`.
- Internal `hidden` and `deleted` flags on pages and accounts, unexposed
  by the public API.

**Done when** the Telegraph client from Phase 0 performs every operation it
supports against the real store, unmodified.

**Note on `getViews`.** Real clients read view counts from the `views`
field returned by `getPage` rather than calling `getViews`. The counter is
required; the endpoint is optional.

**Note on the hidden flags.** They will not be used for a long time. They
exist now because adding a delete path to a store that has promised
permanence is close to impossible, and because the first time they are
needed will be urgent.

---

## Phase 3 — Serving · 2–3 days

Public rendering of a page at its path.

- Node tree to HTML, from templates the store controls.
- Caching, which the one law makes straightforward — a page is a value, so
  it can be cached until it is edited.
- View counting on render.

Different performance profile from the API, and probably a different code
path. Worth keeping separable.

---

## Phase 4 — Gating and operations · 2–3 days

- Network gating, plus an administrative tool for minting tokens.
- Deployment, TLS, a domain.
- Backups. Not ops hygiene — a product requirement. Clients are being
  promised permanence, and `editPage` replaces wholesale with no undo.
- Monitoring.

**Done when** an invited account can publish a page from a real client and
that page renders publicly.

**A gated instance is usable here — roughly two weeks of work.**

---

## Phase 5 — Durability · ongoing

Restore drills, integrity checks, capacity. Unglamorous and load-bearing.

A store whose entire promise is that the bytes come back has to prove it
periodically. A backup that has never been restored is a hypothesis.

---

## Phase 5b — Capability pages and an editor · 3–5 days

The [capability page](capability.md) mechanism, and the authoring tool that
makes it worth having.

- `module` and `attr` as reserved tags, with validation.
- A capability page published for the reference renderer, describing
  itself.
- An editor that loads one by address and completes module names per block
  and declared attributes per line.
- The module prompt sequence, ending in the fallback step.
- Side-by-side supported and fallback previews.

**Done when** an author can paste a capability address and write a valid
targeted page without reading any documentation.

This is where the format stops being a specification and starts being
usable by someone who has not read it. Sequenced after a working store
because a capability page is a bootpage and needs somewhere to live.

---

## Phase 6 — Modules · ongoing, demand-led

The core registry, discovered from real pages rather than designed in
advance.

The fallback rule means shipping a module late costs nothing: until it
exists, nodes using it render as their children. That is unusual and worth
exploiting — resist the urge to guess at a registry before there are pages
that want one.

---

## Phase 7 — Uploads · optional

Image and file hosting.

Deliberately last. It carries storage cost, and it is the single worst
abuse vector in any public content system. A gated instance may never need
it; an open one needs a moderation story first.

---

## Phase 8 — Opening up · weeks, whenever

Everything that gating currently makes unnecessary:

- Rate limiting and account-creation friction.
- Content scanning and reporting.
- Takedown workflow, using the flags built in Phase 2.
- A stated legal posture on hosted user content.

**This phase is larger than every preceding phase combined**, and it is
entirely about abuse rather than features. Anonymous, free, permanent,
public hosting is the exact combination attackers look for.

Nothing in the earlier phases should assume it will never happen, and
nothing should be delayed waiting for it.

---

## Effort summary

| Phase | | Effort |
|---|---|---|
| 0 | Ground | 1 day |
| 1 | Format | 2–4 days |
| 2 | Store and API | 3–5 days |
| 3 | Serving | 2–3 days |
| 4 | Gating and operations | 2–3 days |
| | **gated instance usable** | **~2 weeks** |
| 5 | Durability | ongoing |
| 5b | Capability pages and an editor | 3–5 days |
| 6 | Modules | demand-led |
| 7 | Uploads | optional |
| 8 | Opening up | weeks |

The two-week figure is honest for a working gated service. The distance
between that and a public one is not a phase, it is a different commitment.
