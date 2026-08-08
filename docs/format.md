# Format

The wire format, the attribute families, the canonical form, and the lenses
people read and write it through.

This document specifies. The [vision](vision.md) explains why, and where
they disagree, the vision wins.

---

## The node

A page is an ordered list of nodes. A node is either a string, or an object
with three fields:

```json
{"tag": "p", "attrs": {}, "children": ["Some prose."]}
```

| Field | Meaning |
|---|---|
| `tag` | what this is |
| `attrs` | how it is configured |
| `children` | nodes, or strings — and the fallback if `tag` is unknown |

A bare string is text.

**All three fields are always present**, including when `attrs` is empty or
a node has no children. This is not cosmetic: an optional field is a way
for two implementations to write the same page differently, and a page that
can be written two ways cannot be fingerprinted. See
[canonical form](#canonical-form).

That is the entire syntax, and it does not grow. New capability arrives as
new values of `tag`, never as new structure.

### Why three fields and not four

Adding a field is the cheapest-looking change and the most expensive one.
It breaks every consumer, invalidates every stored page, and ends
compatibility with the Telegraph clients that come free with this shape.
Anything that feels like it needs a fourth field is an attribute, a child,
or a mistake.

---

## Tag: the extension point

`tag` is the only thing that varies, and it decides how a node is treated.

- **An HTML tag** from the core set renders as that element.
- **A module name** is dispatched to whatever the consumer has registered.
- **Anything unrecognised** falls back to `children`.

The core HTML set is the one Telegraph accepts, and it is closed:

```
a  aside  b  blockquote  br  code  em  figcaption  figure  h3  h4  hr
i  iframe  img  li  ol  p  pre  s  strong  u  ul  video
```

### Telegraph compatibility is a consequence, not a feature

A Telegraph page is a list of exactly these nodes with exactly these tags.
Under the rules above, that is already a valid bootpage — one in which
every tag happens to be an HTML tag.

There is no conversion layer, no import step and no compatibility mode,
because none is required. Compatibility falls out of the type system, and
maintaining it costs nothing as long as the node shape does not change.

---

## Children

One rule covers every case:

> **An unsupported node renders its children in document order. What a
> supported node does with its children is the module's business.**

"Children are the fallback" is a useful shorthand, but not quite true — for
a `p`, children are simply its content. The rule above is the accurate
form, and it works because modules come in two shapes that both degrade
correctly under it.

### Leaf modules

The module renders from its attributes. Children exist purely as the
fallback, and a supporting consumer ignores them.

```json
{"tag": "poll",
 "attrs": {"endpoint": "https://example.org/vote"},
 "children": [{"tag": "p", "children": ["Vote: yes, no, or abstain."]}]}
```

Supported, a poll. Unsupported, one sentence.

### Container modules

The children *are* the content, and the module arranges them.

```json
{"tag": "columns",
 "attrs": {"count": "2"},
 "children": [{"tag": "p", "children": ["Left."]},
              {"tag": "p", "children": ["Right."]}]}
```

Supported, two columns. Unsupported, the same two paragraphs stacked in
order — **the fallback is free.** Nothing was written twice, and it cannot
be wrong.

Which shape a module has is declared in the site's
[capability page](capability.md), because a site is the authority on its
own modules.

Containers are where the flat memo lens bites: nesting is natural in fenced
blocks and YAML, awkward in a memo. That makes
[decision 2](decisions.md) more consequential than it first appears.

### Why this works

This single rule gives progressive enhancement at the document level, and
removes the need for versioning, capability negotiation or content
handshakes — the three things that usually kill formats like this. Every
new module type is backward compatible by construction, because an unaware
renderer always has something valid to show.

A consumer that wants to know what a page needs simply inspects which tags
it uses. The tags are the declaration; no manifest of the manifest is
required.

### When a fallback is worse than nothing

Not every author would rather show something than nothing. A signature
block, a payment control or a compliance notice may be better omitted than
approximated.

```
on-unsupported: fallback | omit        (default: fallback)
```

`omit` means a consumer that cannot honour the node renders nothing for it
at all.

---

## The five attribute families

Attributes sort by one question: **what happens if the consumer ignores
this?**

### `require-*` — binding

```
require-role: finance
require-capability: camera
```

Ignoring it produces a wrong or unsafe result. A consumer that cannot
evaluate a `require-` attribute must not render the node as though it were
satisfied. Multiple `require-` attributes all have to hold.

These are **labels, not expressions.** The page states what is required;
the consumer evaluates it against whoever is asking. There is no comparison
operator, no boolean logic and no expression language, and there must never
be one — see *pressure points* below.

### `prefer-*` — advisory

```
prefer-layout: grid, list
prefer-emphasis: high
prefer-reveal: on-scroll
```

Ignoring it produces a valid page that looks different. A consumer may
honour all, some or none of these and remains fully conforming.

**The removability test:** strip every `prefer-*` attribute from a page and
it must still be complete and correct. If removing something breaks the
page, it was never a preference.

Values are **intent, never measurement.** `prefer-emphasis: high` survives
being rendered as a phone card, a print sheet, a terminal or spoken aloud.
`prefer-font-size: 24px` is meaningless in three of those and hardcodes one
consumer's design system into a portable document.

Comma-separated values are an ordered preference list, read the way font
stacks and content negotiation headers are read: take the first supported,
fall back leftward.

### `on-*` — behavioural intent

```
on-select: navigate
on-submit: send
on-unsupported: omit
```

Named actions from a closed vocabulary. Never code, never an expression,
never a function call. A consumer that does not support the named action
falls back to `children`.

### `meta-*` — informational

```
meta-author: operations
meta-license: CC-BY-4.0
meta-updated: 2026-08-01
meta-valid-until: 2026-12-31
```

Describes the content rather than instructing the consumer. Never affects
rendering. Frequently affects trust, which is why it matters more in a
manifest than it would in an article — `meta-valid-until` lets a consumer
know when a page stops being something it should still be acting on.

### Unprefixed — structural

```
id: sales
ref: #sales
source: https://finance.example.internal/q3
```

The wiring that makes composition and retrieval work. Binding, and part of
the reserved core vocabulary.

### Choosing a family

| Test | Family |
|---|---|
| Remove it — does the page break? If no | `prefer-` |
| Ignore it — does the page become wrong or unsafe? If yes | `require-` |
| Does it name an action? | `on-` |
| Does it describe rather than direct? | `meta-` |
| Is it wiring? | unprefixed |

---

## Values are opaque

> **A scalar may be typed. Structure goes in `children`.**

An attribute value is a string, or a comma-separated list of strings.

A module **may** declare that one of its attributes is an integer, a date
or one of a fixed set — that is a typed read of a single value, and it is
what `width="100"` has always meant. A consumer reads it according to what
the module declared, in its own [capability page](capability.md).

What is forbidden is encoding **structure** in a string: a delimiter
standing in for a list of records, nested pairs crammed onto one line, any
value with internal shape. If a value seems to need structure, it wants to
be `children` or a nested node.

This matters because the alternative is invisible. Writing
`options: "a|b|c"` looks harmless, and it is a private grammar inside a
string. Do it four times and the format has an undocumented syntax that
every consumer must reimplement and none will agree on. Comma-separated
lists are the one permitted exception, because they are a flat sequence of
scalars and already how preference lists and content negotiation work.

### Why values are not JSON

Two reasons, neither about coordinating module authors.

**Canonicalisation.** Numbers have many spellings — `1`, `1.0`, `1e0` —
plus floating-point precision. Allowing them turns a twenty-line
[canonical form](#canonical-form) into a genuinely hard problem, in the one
component that must still agree with itself in forty years.

**The memo lens.** `key: value` lines with inferred types is the well-known
configuration footgun: a country code parsed as a boolean, a version number
turned into a float, a leading zero dropped. Strings mean zero inference —
what someone types is what is stored.

---

## Referencing

Three mechanisms, and choosing between them is the same act as deciding
what is public.

**Inline — `children`.** The data is in the page. Public, permanent,
cacheable, readable by anyone who fetches the raw page.

**External — `source`.** The page holds only an address. The consumer
decides whether to fetch it, under the viewer's own credentials. This is
[selective retrieval](vision.md#selective-retrieval).

**Within the page — `id` and `ref`.** One block points at another. Resolved
locally, with no network and no cycles beyond the page itself.

```
## Sales figures
id: sales

## Chart
type: chart
ref: #sales
prefer-layout: line, table
```

This is the confidentiality rule wearing different clothes. Data in
`children` is *published*; data behind `source` is *pointed at*. So "which
mechanism do I use?" and "is this safe to make public?" are the same
question with the same answer — an author cannot leak something
confidential by choosing the wrong markup. They would have to type it into
the page.

---

## Media

Images and video use the tags already in the core set — `img`, `video`,
`figure` — with `src`. No module is required.

One consequence to be explicit about: **`src` is a pointer, and the store
never proxies it.** The reader's browser fetches directly from wherever the
media lives, so that host sees the IP address of everyone who views the
page. Documented here rather than discovered later.

---

## Tables

The core tag set has no `table`, so a table is a list of rows and a row is
a list of cells:

```json
{"tag": "table", "attrs": {}, "children": [
  {"tag": "ul", "children": [
    {"tag": "li", "children": [
      {"tag": "ul", "children": [
        {"tag": "li", "children": ["North"]},
        {"tag": "li", "children": ["120"]}]}]}]}]}
```

A site implementing `table` lays it out as a grid. One that does not
renders nested bullets, which still reads as rows.

This is verbose, and the verbosity is deliberate. A flatter form is
possible — one list of cells, sliced by a `columns` attribute — and it is
roughly half the size, but it degrades into every cell in sequence, which
is unreadable beyond two columns. **Fallback fidelity is the property the
format rests on**, and the redundancy that makes this look bloated is
exactly what a compressor removes.

No human writes this. See the lens syntaxes below.

### Writing a table

The memo lens accepts two forms, because nobody types a table — they paste
one. Copying from a spreadsheet yields tab-separated text:

```
## Regional sales
type: table

Region	Q2	Q3
North	120	140
South	98	131
```

And for those who already know them, pipe tables:

```
| Region | Q2  | Q3  |
|--------|-----|-----|
| North  | 120 | 140 |
```

Both produce the same tree. Two input syntaxes, one format — which is what
lenses are for.

---

## Pressure points

Three ways logic tries to get in. All predictable, all refused by the rules
above.

**Conditionals.** Someone will want
`when: user.role == 'finance' && region == 'EU'`. That is an expression
language arriving through the back door. The answer is multiple `require-`
labels, evaluated by the consumer.

**Inline code in `on-*`.** `on-select: doThing(); track()`. Closed
vocabulary of action names only.

**Mini-syntaxes inside values.** The sneakiest, because each instance looks
reasonable in isolation. Covered by *values are opaque*.

---

## Namespaces

Reserved permanently by this specification:

- the unprefixed core vocabulary
- the prefixes `require-`, `prefer-`, `on-`, `meta-`
- the core HTML tag set
- `module` and `attr`, used by [capability pages](capability.md)
- core module names as the registry adopts them

Everything else belongs to whoever defines it, under a vendor prefix:

```
x-acme-workflow
```

The reasoning is the same one that led HTML to require a hyphen in custom
element names: reserve the plain space early, and the two spaces never
collide. It costs a sentence now and cannot be retrofitted once pages exist
in the world.

---

## Canonical form

A page needs a fingerprint, so that two parties anywhere can confirm they
are looking at the same thing. A fingerprint is computed from text — and
the same page can be written as text in several equally valid ways. So
before fingerprinting, a page is rewritten in one agreed way.

That agreed way is the canonical form.

### The recipe

Each step eliminates one way two implementations can disagree.

1. **All three fields present** on every node, even when empty. *Removes:
   one tool omitting empty fields while another includes them.*
   This applies to the **stored** form. A client may post
   `{"tag":"li","children":["North"]}` and the store fills in the empty
   `attrs` on write — nobody has to type the empty braces.
2. **Fields in sorted order**, bytewise. *Removes: one tool writing `tag`
   first, another writing `children` first.*
3. **No insignificant whitespace** — no indentation, no line breaks, no
   space after a colon or comma. *Removes: pretty-printed versus compact.*
4. **UTF-8, minimal escaping.** Characters outside ASCII are written
   literally. *Removes: `café` versus `café`.*
5. **The whole node list as one line of text.**
6. **Hash that line.**
7. **Label the result** with the recipe and the algorithm.

### Worked example

Two tools hold the same paragraph. One writes:

```json
{
  "children": ["Hello"],
  "tag": "p"
}
```

The other writes:

```json
{"tag":"p","children":["Hello"]}
```

Identical content, different bytes, different fingerprint — useless. Both
canonicalise to exactly one line:

```json
{"attrs":{},"children":["Hello"],"tag":"p"}
```

Identical text, identical fingerprint.

### Why this subset is easy to canonicalise

General JSON canonicalisation is a hard problem, mostly because of numbers
— floating point has many spellings for one value. This format has none.
Attribute values are strings, nodes have three fields, and there are no
numbers, booleans or nulls anywhere. The recipe above is perhaps twenty
lines in any language.

That simplicity is a direct dividend of the *values are opaque* rule, and
is a reason to keep resisting pressure to relax it.

### Who has to implement it

Almost nobody.

The **store** canonicalises on write. A **consumer** that wants change
control treats the digest as an opaque string — it stores the one it
approved and compares on the next fetch, never hashing or canonicalising
anything. Only a consumer that wants to *independently verify* the store
needs the recipe, which is rare and optional.

A seven-step process is therefore work for one implementation rather than
for everyone who touches the format.

### Storage

The canonical bytes are what the store holds.

Computing the digest once at write, and never again, is what stops it
drifting as libraries, languages and JSON serialisers change across the
decades this format is meant to survive. It also makes the store's
neutrality provable rather than promised: it returns exactly the bytes it
took.

One honest consequence: a page posted in non-canonical JSON is normalised
on write, so what comes back is not byte-identical to what went in. That is
the **only** transformation a store may perform, and only because it
demonstrably preserves meaning. Injecting, rewriting, decorating or
reformatting anything else remains forbidden.

---

## Revision markers

Consumers ask two different questions, and they need two different answers.

> *"Is this the same content I approved?"* — identity of **content**
>
> *"How many times has this changed, and is this newer?"* — identity of
> **event**

A hash answers the first and cannot answer the second: edit a page from A
to B and back to A, and the hash returns to its original value. A counter
answers the second and cannot answer the first: it reports that something
changed, not whether it matters.

So `getPage` returns both:

```json
{"path": "q3-onboarding-08-01",
 "revision": 7,
 "digest": "bp1-sha256:9f2c…",
 "content": [...]}
```

Telegraph clients ignore response fields they do not recognise, so this
costs nothing in compatibility.

### The label

`bp1` names the canonicalisation recipe. `sha256` names the hash function.

Both will eventually need replacing — recipes get refined, hash functions
weaken with age. Naming them means a digest computed today still means
something precise in forty years, because it says how it was made. Without
the label, changing either one silently redefines every digest ever issued,
with no way to tell which era one came from.

**Never emit a bare hex digest.**

### Pinning is the consumer's job

This follows from the three-party model: identity is the store's to
provide, policy is the consumer's to apply.

A consumer that needs change control stores the digest it approved and
compares it on each fetch. If it differs, the page has moved and should not
be applied until somebody re-approves it.

That requires **nothing further from the store** — no revision history, no
extra endpoints, no storage growth. Addressable revisions remain possible
later without changing anything specified here.

### What a digest does and does not prove

It proves two observers are looking at the same bytes. It catches
corruption, accidental rewriting, and silent drift, and it lets a consumer
check a page against a digest obtained from the author by other means.

It does **not** by itself prove the store is honest — a dishonest store
could alter content and report a matching digest. Author signatures would
close that gap; the label scheme leaves room for them, and they are not
specified here.

### The counter's failure mode

A counter restored from backup can go backwards, so a consumer that saw
revision 7 might later be handed revision 6.

The mitigation is that the counter is stored **with the page** rather than
drawn from a global sequence, which keeps a restore internally consistent.
This is written down because it is the kind of thing otherwise discovered
at the worst possible moment.

---

## Lenses

Five ways to look at one page. All are **projections of the canonical node
list, never dialects with their own semantics.** The moment a lens can
express something the tree cannot, there are five formats instead of one
and they drift.

| Lens | For |
|---|---|
| Memo | writing and editing by hand |
| Fenced blocks | module-dense pages |
| YAML | tooling and precision |
| JSON | the wire |
| HTML | a consumer displaying the page |
| Tree | seeing what a consumer does with each node |

The tree lens was added after the others and is not a writing lens: it
renders the structure — each node's tag, whether the consumer implements
it or falls back, its attributes by family, and its `id` as an anchor. It
projects the same node list and adds no semantics, which is the only test
a lens has to pass.

The canonical one-line string is not among them, and no person or consumer
ever handles it. Authors see the memo lens, consumers receive the tree,
readers see HTML. The canonical string exists solely so two machines can
agree they are discussing the same page — it is plumbing, not an interface.

### 1. Memo — for people

Lineage: the header block that memos and mail have used for fifty years,
plus Markdown headings.

```
title: Q3 Onboarding
audience: new staff

## Welcome

Just write. Prose is prose — no markup, no keys, nothing to learn.
This becomes a run of paragraph nodes.

## Expenses
require-role: finance
source: https://finance.example.internal/q3
prefer-layout: table, list

If you have finance access, this section loads live figures.
Otherwise you are reading this sentence, which is the fallback.
```

The whole rule in one sentence: **a heading opens a section; `key: value`
lines immediately beneath it configure it; everything after the first blank
line is its content.**

Disambiguation needs no escaping. Keys are lowercase and hyphenated only,
and are recognised solely in the contiguous block directly under a heading.
A paragraph beginning "Note: this matters" is prose — `Note` is
capitalised, and it sits after the blank line.

### 2. Fenced blocks — for module-dense pages

Lineage: the fenced code block with an info string, which nearly every
writer of documentation already knows.

````
```chart kind=line source=#sales
Sales rose through Q3, ending 18% up.
```
````

The text inside is the fallback — the same contract as everywhere else, so
the rule is only ever taught once.

### 3. YAML — for precision and tooling

```yaml
- tag: chart
  attrs: {kind: line, source: "#sales"}
  children: ["Sales rose through Q3, ending 18% up."]
```

The triplet spelled out. What generators emit, and what an author drops to
when they want exact control.

### 4. JSON — the wire format

What the API accepts and returns. Nobody authors here by hand and nobody
has to.

### Round-tripping, honestly

The canonical direction is guaranteed: any tree renders to any surface.
The reverse is not lossless — comments, blank-line choices and key ordering
do not survive a rebuild.

The resolution is that **the tree is what is stored.** Lenses are for
authoring and editing, not for storage.

---

## Why the output looks regular without anyone formatting anything

Authors never write styling. There is no bold, no typeface, no spacing to
choose. They declare what a thing *is*, and the consumer's stylesheet
decides how it looks.

This is why documents produced under an enforced template look consistent
and free-form ones do not — except that here the constraint is structural
rather than social. There is no way to express a visual choice, so every
page rendered by a given consumer belongs to that consumer's house style,
and the same page rendered elsewhere adopts a different one.

The page is portable precisely because it carries no appearance.
