# Conformance

What it means to *support* bootpages.

This document exists so that "bootpages-compatible" is a claim that can be
checked rather than a mood. A format becomes infrastructure at the moment
it publishes what supporting it requires; before that, every implementation
diverges in a slightly different direction and none of them are wrong.

Requirement words are used in their usual sense: **MUST**, **MUST NOT**,
**SHOULD**, **MAY**.

---

## The parties, and what each conforms to

Three roles, three different sets of obligations. An implementation may
occupy more than one, and is judged separately for each.

- A **store** holds and serves pages.
- A **consumer** renders them.
- An **author tool** produces them.

Publishing a [capability page](capability.md) is optional and has its own
obligations, listed there.

---

## Consumer levels

### Level 0 — Reader

The floor. A Level 0 consumer renders prose and falls back on everything
else.

A Level 0 consumer:

- **MUST** render the core HTML tag set.
- **MUST** render `children` for any `tag` it does not recognise.
- **MUST** render nothing for a node whose `on-unsupported` is `omit`.
- **MUST NOT** evaluate any attribute value as code.
- **MUST NOT** render a node whose `require-*` attributes it cannot
  evaluate as though they were satisfied.
- **MAY** ignore every `prefer-*` attribute.

A Level 0 consumer that ignores every preference is **fully conforming, not
degraded.** This is the whole point of the removability rule: preferences
are advisory, so declining all of them is a legitimate implementation and
not a partial one.

A plain Telegraph renderer is very nearly Level 0 already.

### Level 1 — Renderer

Everything in Level 0, plus the core module vocabulary.

A Level 1 consumer:

- **MUST** implement every module in the core registry, or fall back
  correctly for those it does not.
- **MUST** honour `require-*` attributes against whatever identity model it
  has, or treat them as unsatisfied.
- **SHOULD** honour `prefer-*` attributes where it has a sensible mapping.
- **SHOULD** read comma-separated `prefer-` values as an ordered
  preference list, taking the first it supports.
- **MUST** treat `meta-*` as informational and never let it affect
  rendering.

### Level 2 — Host

Everything in Level 1, plus its own extensions.

A Level 2 consumer:

- **MAY** register modules under its own vendor prefix.
- **MUST NOT** define tags or attributes in the reserved namespaces.
- **MUST** remain correct for pages that use none of its extensions.
- **SHOULD** document its extensions so pages written for it are portable
  in the fallback sense.

---

## Store conformance

A store is judged on neutrality and durability, not on features.

A conforming store:

- **MUST** return a page byte-equivalent in structure to what was stored.
- **MUST NOT** evaluate, execute or interpret page content.
- **MUST NOT** dereference any URL appearing in a page while serving it.
- **MUST NOT** vary a page's content by viewer, credential, time, or
  request header.
- **MUST NOT** inject, rewrite, decorate or "improve" stored content.
- **MUST** serve every page publicly at a stable, permanent path.
- **MUST** canonicalise a page on write and store the canonical bytes.
- **MUST** return a `revision` counter and a labelled `digest` from
  `getPage`. See [revision markers](format.md#revision-markers).
- **MUST NOT** return a bare unlabelled digest.
- **SHOULD** store the revision counter with the page rather than draw it
  from a global sequence, so that a restore stays internally consistent.
- **SHOULD** be API-compatible with Telegraph.

Normalising on write is the single permitted exception to "must not
rewrite": it provably preserves meaning, and it is what makes a digest
mean anything at all.

The prohibitions matter more than the capabilities. A store that
dereferences becomes a request-forgery engine; a store that varies by
viewer destroys cacheability, verifiability and the one law; a store that
rewrites content makes signatures and hashes meaningless.

**Neutrality is the product.**

---

## Author tool conformance

An author tool:

- **MUST** produce a canonical node list.
- **MUST NOT** emit a surface-specific construct that does not exist in the
  tree.
- **SHOULD** warn when a value contains a private syntax — a delimiter
  inside a string standing in for structure.
- **SHOULD** warn when a node has no `children` and no `on-unsupported`,
  since it will render as nothing on any consumer that does not know its
  tag.
- **SHOULD** prompt for fallback content when an author adds a module.
  Fallbacks are load-bearing and invisible, so they are skipped unless
  asked for directly.
- **SHOULD** show the fallback rendering alongside the supported one, so
  the [blind test](#the-blind-test) is part of writing rather than review.
- **MUST NOT** prevent an author writing a module that no loaded
  [capability page](capability.md) declares. Sites change, capability pages
  go stale, and writing ahead of a site is legitimate.

---

## The tests

Three mechanical checks. They are worth automating early, because each one
catches a class of error rather than an instance.

### The strip test

Remove every `prefer-*` attribute from a page. It **MUST** still be
complete and correct.

Catches preferences that were quietly load-bearing.

### The blind test

Render a page with an empty module registry, so every non-HTML tag falls
back. The result **MUST** be readable and **MUST NOT** misrepresent the
page — an omitted section is acceptable; a section that reads as though it
said something it did not is not.

Catches missing or misleading fallbacks.

### The opacity test

No attribute value is parsed as anything but a string or a comma-separated
list of strings.

Catches private syntaxes, which is how a small format stops being one.

---

## Claiming conformance

State the role, the level, and the extensions:

> *Example Reader is a Level 1 bootpages consumer. It implements the core
> module registry, honours `prefer-layout` and `prefer-emphasis`, ignores
> all other preferences, and defines no extensions.*

Naming the ignored preferences is not an admission of incompleteness. It is
the useful half of the sentence, and it is what lets an author know what
their page will actually look like when it lands there.
