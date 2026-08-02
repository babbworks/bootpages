# Vision and principles

This document is the reasoning. The [format](format.md) is downstream of
it, and when the two disagree the reasoning wins.

---

## The problem

Distributing an experience through the browser currently means shipping
code. To change what an audience sees, someone edits a file, redeploys a
server, or pushes to a CDN. The information and the machinery that presents
it are welded together, so every change to the first requires access to the
second.

That has three consequences worth naming. Only people with deployment
access can change what is presented. Every consuming site needs its own
copy of the logic. And a change has to be made everywhere it was copied to,
or the copies diverge.

Documents solve none of this because documents carry no structure a machine
can act on. Applications solve it by absorbing everything, which means
whoever holds the deployment key holds the content too.

Bootpages is the third option: **a document with enough structure to drive
an interface, and no capability to be one.**

---

## The one law

> **A page is a public value. Anything that varies by viewer, time, or
> secret belongs to the consumer.**

A value is the same for everyone who asks. It does not know who is reading
it. It does not change between two fetches unless someone edited it. It has
no session, no personalisation and no execution.

This is the constraint that makes everything else possible, and it is worth
being precise about what it buys:

- **Cacheability.** A page can be held anywhere, indefinitely.
- **Verifiability.** A page can be hashed, so a consumer can pin a version
  and know it has not moved underneath them.
- **Portability.** The same page renders in a browser, a terminal, a print
  sheet or a screen reader, because it carries no appearance to be wrong in
  any of them.
- **Safety at scale.** A page cannot attack the store that holds it or the
  site that renders it, so it can be served anonymously without becoming a
  compute platform for strangers.

### What it costs, plainly

Pages cannot be dynamic *from the store*. No page renders differently per
viewer at fetch time. No server-side personalisation. No value computed
when the page is requested.

That is a real limitation and it should be stated rather than
rationalised. Everything in the list above is bought with it.

---

## Three parties

Most document systems have two: an author and a reader. Bootpages has
three, and separating them resolves nearly every ambiguity in the design.

**The author owns meaning.** What the page says, what its parts are, what
each part requires, and what they would prefer it looked like.

**The store owns durability.** Holding the page and serving it faithfully.
The store is neutral: it does not interpret, evaluate, dereference,
personalise or improve what it holds. Its entire promise is that the bytes
come back.

**The consumer owns behaviour.** What to render, what to fetch, what to
execute, and what to show to whom. All logic lives here — not because logic
is unwelcome, but because the consumer is the only party that knows who is
asking.

When a question is hard, it is usually because it has been asked of the
wrong party.

---

## Execution, precisely

"No code execution" is four different claims wearing one phrase. Only one
of them is a rule here.

**1. The store evaluates page content.** *Excluded.* This is the only
exclusion. It would make bootpages a compute platform — sandboxing,
resource limits, untrusted execution — which is a different product, orders
of magnitude more work, and incompatible with ever opening to the public.

**2. The consumer runs code the page carries.** *Not our decision.* A
receiving site may do whatever it likes with what it fetched, under its own
runtime and its own risk.

**3. The page declares behaviour the consumer implements.** *Encouraged.*
This is what modules are.

**4. The page contains code as content.** *Unrestricted.* A page may carry
an entire program.

The distinction that matters is between **carrying** code and **running**
it. They are unrelated capabilities. A source repository hosts more code
than almost anywhere and executes none of it as part of serving it — which
is precisely why it can host anything at all.

So the rule, stated so it does not limit anything it should not:

> The store never evaluates page content. What a consumer does with it is
> the consumer's business.

---

## Selective presentation and selective retrieval

A single page can drive an interface that shows different things to
different people. There are two mechanisms for this and they are not
interchangeable.

### Selective presentation

The page contains every variant. The consumer shows some and hides others
based on who is asking.

This is **not confidentiality.** The page is public and permanent — anyone
can fetch the raw JSON and read every branch, including ones they would
never be shown. It is a routing and layout mechanism, appropriate where the
differences are not sensitive: a contractor seeing a shorter onboarding
path than a permanent member of staff.

It is the foundation, because it requires nothing of the consumer beyond
knowing who the viewer is.

### Selective retrieval

The page contains no privileged content at all. It declares *where* data
lives and *what capability is needed to reach it*. The consumer fetches it
using the viewer's own credentials against the organisation's own systems.

The page never holds the data, never holds a secret, and never sees the
credential.

This is where the larger value is. A page stops being a document with
hidden sections and becomes a manifest of an experience — one published
artifact driving a permission-aware interface, with the actual data
remaining behind whatever authentication already protects it.

### The trap

Putting confidential content in a page and relying on the consumer to hide
it looks like it works. It will keep looking like it works. It is a breach
with a delay on it.

The spec says this loudly and repeatedly because it is the obvious wrong
turn and somebody will take it.

---

## Simplest markup, maximum possibility

The apparent paradox — the smallest set of document methods with the widest
range of uses — resolves in one move:

> **The syntax is closed. The vocabulary is open.**

The node shape never changes: three fields, forever. Capability grows by
adding *tags*, never by adding syntax. This is why formats like this
survive: expressive power lives in the vocabulary, where it can grow
indefinitely without anybody having to learn a new grammar.

It gives a falsifiable rule to hold every future proposal against, and one
that can be pointed at in an argument:

> **If it needs new syntax, it is wrong. If it can be a tag with attrs, it
> is right.**

Every simple format that stayed simple had a rule like this. Every one that
did not became a template language, and then a bad programming language.

---

## Preference without authority

Authors can express how they would like something displayed or to behave,
and consumers are free to ignore all of it. This is deliberate: a page will
be rendered in contexts its author cannot imagine, and an author who can
*compel* appearance has made the page unportable.

Preferences are therefore advisory, semantic rather than measured, and
removable — strip every one of them and the page must still be complete and
correct. See [format](format.md) for the mechanism.

Authors get influence. Consumers keep authority. That is the correct
division for a document that outlives the assumptions of whoever wrote it.

---

## Composition

Pages are standalone. A page must make sense on its own, fetched alone,
rendered by something that has never heard of any other page.

They may nonetheless refer to each other, and a reference is a
**declaration, not an include**. A page says where something else lives;
whether to fetch and inline it is the consumer's decision.

This matters more than it sounds. A store that dereferenced references
while serving would acquire three problems at once: server-side request
forgery, reference cycles, and unbounded render cost from a single page. A
non-dereferencing store always answers in bounded time from bytes it
already holds.

The same reasoning applies to outside data sources. The store does not
police what a page points at. It simply never follows the pointer itself.

---

## Governance of the vocabulary

An open vocabulary collides unless somebody reserves a space. The core
names and the four reserved prefixes belong to the specification; everyone
else uses a vendor prefix.

This costs one sentence now and is unfixable once pages exist in the world.
It is the same move HTML made in requiring a hyphen in custom element
names, and that space has never collided since.

---

## What this makes possible

Stated concretely, because a principles document that never lands anywhere
is just a mood:

- An organisation publishes one page describing an onboarding process. Six
  internal tools render it, each in its own house style. Changing the
  process means editing the page — no deploys, no tickets, no drift between
  the six copies.
- A page declares that a section requires a finance role and names an
  endpoint. Staff with that role see live figures pulled under their own
  credentials. Everyone else sees a sentence. The page contains neither the
  figures nor a credential.
- A site accepts bootpages from its users as a way of contributing
  structured content, safe in the knowledge that a page cannot execute
  anything, cannot carry a secret, and renders in bounded time.
- A page carries a program as content — configuration, a schema, a
  workflow — and a consumer that knows what to do with it does so in its
  own runtime, under its own trust rules.

In each case the page is a value, the consumer supplies the context, and
nobody redeployed anything.
