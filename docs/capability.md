# Capability pages

A consuming site publishes a page describing what it welcomes: which
modules it implements, what each one takes, and what the values may be.

That page is itself a bootpage. The format describes what consumes the
format, which is what closes the system — and it means an authoring tool
needs no built-in knowledge of any site. It ships knowing the node shape
and nothing else. Everything site-specific arrives at runtime, as data,
from an address somebody pasted in.

One editor therefore serves every site that will ever exist, including ones
written long after the editor stopped being maintained.

---

## The vocabulary

Two reserved tags, and nothing else is needed.

**`module`** declares something the site implements.
**`attr`** declares one of its attributes.

```json
{"tag": "module", "attrs": {"name": "map", "shape": "leaf"}, "children": [
  {"tag": "p", "children": ["An interactive map."]},
  {"tag": "attr", "attrs": {"name": "centre", "type": "string", "required": "true"},
   "children": [{"tag": "p", "children": ["A place name, or a latitude and longitude."]}]}]}
```

### `module` attributes

| | |
|---|---|
| `name` | the tag this module handles |
| `shape` | `leaf` or `container` — see [children](format.md#children) |

### `attr` attributes

| | |
|---|---|
| `name` | the attribute name |
| `type` | `string`, `integer`, `decimal`, `boolean`, `date`, `reference` |
| `required` | `true` or `false` (default `false`) |
| `values` | permitted values, comma-separated, for an enumeration |
| `min` / `max` | bounds for a number |
| `default` | what applies when the attribute is absent |
| `example` | a specimen value, shown as placeholder text |

Note `min` and `max` as two separate scalars rather than a range written
into one string. A range with a delimiter in it would be a private syntax,
which [values are opaque](format.md#values-are-opaque) forbids. The rule
catches this kind of thing even when you know it is there.

### The children carry the description

The children of a `module` or `attr` are its human description.

That means one set of bytes is simultaneously the documentation a reader
sees, the helper text beside a field in an authoring tool, and the fallback
if something renders the capability page without understanding it. They
cannot drift apart, because they are the same bytes.

Documentation going stale is a permanent condition of every API ecosystem.
Here it is structurally impossible rather than merely discouraged.

---

## A capability page, written

In the memo lens, the way a site would actually author one:

```
title: What this site renders
meta-updated: 2026-08-02
meta-valid-until: 2027-08-02

## map
type: module
shape: leaf

An interactive map. Give it a centre, and optionally a block of markers.

### centre
type: string
required: true
example: Truro, Cornwall

A place name, or a latitude and longitude.

### zoom
type: integer
min: 1
max: 18
default: 11

How far in the map starts. Higher is closer.

### markers
type: reference

Points at a block of locations elsewhere in the page.
```

---

## What an authoring tool does with it

The author pastes the site's capability address into a search box — which
doubles as the place to paste a link, since both are "tell me about a
site."

### Completion, per block and per line

**At a heading**, the editor offers the site's module names with their
descriptions inline. The author picks from what the site can actually do,
rather than from a general list of things that may or may not work.

**Within a block**, once the heading names `map`, the `key: value` lines
beneath are constrained to that module's declared attributes. Typing `z`
offers `zoom`. Typing `zoom: ` offers a bounded number field, because
`min` and `max` said so. Typing `markers: ` offers `#offices`, because a
block with `id: offices` exists earlier in the page.

This is ordinary editor behaviour, except that the language definition
arrived from a URL a moment ago.

### The sequence when a module is chosen

Selecting a module starts a prompt sequence. The order matters:

1. **Required attributes**, one at a time, with the declared type driving
   the control — a picker for an enumeration, a bounded field for a range,
   a list of in-page identifiers for a reference.
2. **Optional attributes**, each showing its default, so skipping one is an
   informed choice rather than an omission.
3. **Preferences**, clearly marked advisory — *the site may ignore this.*
4. **The fallback, as an explicit step.** *"What should a site without maps
   show here?"*

That fourth step is the one to insist on. Fallbacks are load-bearing and
invisible, so authors will skip them unless asked directly. Making it a
prompt rather than an afterthought is the cheapest available fix for the
format's most common failure.

The sequence must be abandonable at any point. A partially configured block
is still a valid page, because the fallback carries it.

---

## Authoring against several sites at once

Load two or three capability pages and an editor can do something document
tools generally cannot:

- Show the **intersection** — modules available everywhere — as the safe
  palette.
- Mark divergences: *"`map` works on A and B. C will show your fallback."*
- Render **both previews at once**: what a supporting site displays, and
  what a non-supporting one displays.

The second preview matters most. Fallbacks are the mechanism the whole
format rests on, and authors neglect them because they never see them. An
editor showing the degraded view continuously makes the
[blind test](conformance.md#the-blind-test) part of writing rather than
part of review.

One thing to design against: intersection authoring pulls toward the lowest
common denominator. The divergence view should make reaching for a
site-specific module feel like a deliberate choice with a known
consequence, not a warning to be avoided.

---

## Validation before publishing

With a capability page loaded, an authoring tool can check things the store
never will and never should:

- an attribute the target does not declare
- a value outside a declared enumeration or range
- a required attribute missing
- **a node with no children targeting a site that does not implement its
  tag**, which will render as nothing at all

None of this is the store's business. All of it is available for free the
moment a capability page is loaded.

---

## Convergence without a committee

Capability pages are bootpages, so they are addressable, fetchable,
linkable and pinnable like any other. A site can publish one that **cites**
another's, declaring that it supports the same vocabulary.

Compatibility therefore becomes a citation graph that anyone can read and
follow, and a de-facto core registry emerges from sites copying vocabularies
that already work — visible in public, rather than agreed in a committee.
That is what [the roadmap](roadmap.md) means by discovering the registry
from use.

It also means an automated agent can author a valid, site-targeted page
with no integration work at all: fetch the capability page, generate,
validate against it, publish.

---

## Limits, honestly

**A capability page is advertising, not a contract.** A site may change what
it implements without warning, and an editor may offer a module that was
removed last month. The mitigations already exist — `revision`, `digest`,
`meta-valid-until` — but the failure mode is real and should not be papered
over.

**Capability does not travel.** If every site declares its own vocabulary
and none coincide, a `map` written for one site does nothing at another.
The fallback rule means a page always *reads* correctly anywhere; it does
not mean the capability follows. That is the accepted cost of letting sites
own their own modules, and convergence by citation is the counterweight.

**Chicken and egg.** This is only valuable if sites publish. An authoring
tool must be entirely usable with nothing loaded, degrading to plain
writing.

---

## Conformance

Publishing a capability page is **optional**. A site that publishes one:

- **SHOULD** serve it at a stable, advertised address.
- **SHOULD** carry `meta-updated`, and `meta-valid-until` where the
  vocabulary is expected to change.
- **MUST** describe only what it actually implements.
- **MUST NOT** declare modules in a namespace it does not own — see
  [namespaces](format.md#namespaces).

An authoring tool that consumes capability pages:

- **MUST** remain usable with none loaded.
- **SHOULD** prompt for fallback content when a module is chosen.
- **SHOULD** show the fallback rendering alongside the supported one.
- **MUST NOT** prevent an author from writing a module the loaded
  capability pages do not declare. Sites change, capability pages go stale,
  and an author writing ahead of a site is a legitimate act.
