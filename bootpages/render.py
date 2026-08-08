"""
Node tree to HTML.

The reference renderer implements no modules. That is deliberate rather
than unfinished: it makes this a Level 0 consumer, it exercises the
fallback path on every non-core tag, and it is the honest starting point
for a registry that should be discovered from use.

Nothing here parses or executes anything from a page. Text is escaped,
attributes come from a fixed allowlist per tag, and URLs are checked
against a scheme allowlist. Because the page is data rather than markup,
there is no sanitiser to get wrong - there is simply no path by which
author-supplied text becomes markup.
"""

from html import escape
from urllib.parse import urlparse

from . import format as fmt

# Rendered without a closing tag.
VOID = frozenset({"br", "hr", "img"})

# The only attributes that reach the output, per tag. Anything else a page
# carries - every require-, prefer-, on- and meta- attribute, and every
# module parameter - is instruction for a consumer, not presentation, and
# has no business in the HTML.
PASSTHROUGH = {
    "a": ("href",),
    "img": ("src",),
    "iframe": ("src",),
    "video": ("src",),
}

# javascript: and data: are how a URL becomes code. Neither is ever needed
# by a document.
SAFE_SCHEMES = frozenset({"http", "https", "mailto", ""})


def safe_url(value):
    """A URL, or None. Relative URLs are fine; scripts are not."""

    try:
        parsed = urlparse(value)

    except ValueError:
        return None

    if parsed.scheme.lower() not in SAFE_SCHEMES:
        return None

    return value


def render(nodes, modules=frozenset()):
    """
    HTML for a node list.

    `modules` names the non-core tags this consumer implements. The
    reference renderer passes none, so every module falls back - which is
    what a page should look like on a site that has never heard of it.
    """

    return "".join(_node(node, modules) for node in fmt.normalise(nodes))


def _node(node, modules):
    if isinstance(node, str):
        return escape(node)

    tag = node["tag"]
    attrs = node["attrs"]
    children = node["children"]

    # A condition this consumer cannot evaluate.
    #
    # format.md: "A consumer that cannot evaluate the condition must not
    # show the node." This renderer has no notion of a viewer, so it can
    # evaluate none of them - and the safe reading is the one the format
    # already uses everywhere else. The node is not shown; its children
    # are, because the confidentiality rule makes them safe by
    # construction: data in `children` is published, data behind `source`
    # is only pointed at. The fallback the author wrote for exactly this
    # case is what a reader gets.
    gated = any(fmt.family(name) == "require" for name in attrs)

    known = (tag in fmt.CORE_TAGS or tag in modules) and not gated

    if not known:
        # The one rule: an unsupported node renders its children in
        # document order. An author who would rather show nothing than an
        # approximation says so, and gets nothing.
        if attrs.get("on-unsupported") == "omit":
            return ""

        return render(children, modules)

    if tag not in fmt.CORE_TAGS:
        # A module this renderer claims to implement. There are none yet;
        # when there are, they dispatch here.
        return render(children, modules)

    return _element(tag, attrs, children, modules)


def _element(tag, attrs, children, modules):
    rendered = ""

    for name in PASSTHROUGH.get(tag, ()):
        value = attrs.get(name)

        if not value:
            continue

        checked = safe_url(value) if name in ("href", "src") else value

        if checked is not None:
            rendered += f' {name}="{escape(checked, quote=True)}"'

    if tag in VOID:
        return f"<{tag}{rendered}>"

    return f"<{tag}{rendered}>{render(children, modules)}</{tag}>"


# The lenses a reader can switch between, in the order the bar shows them.
# JSON is included because it is what a consumer receives, and a reader
# who wants to see what their software sees should not need to be told a
# query string exists.
LENSES = (("", "Read"), ("memo", "Memo"), ("tree", "Structure"),
          ("json", "JSON"))


def lens_bar(path, current=""):
    """
    A thin bar for switching lens. No script, deliberately and easily.

    Switching lens is navigation, not interaction - three links do it. A
    published page executes nothing, and that is a claim consuming sites
    can check rather than a promise they have to take: `default-src
    'none'` says it in a header. Trading that for a nicer control would
    downgrade a verifiable property to a conditional one, and this
    particular control does not need the trade.

    Anything that genuinely needs a client - clipboard, hover-tracking
    across panes, live subscription - belongs in a separate consumer on
    its own origin. See docs/status.md.
    """

    if not path:
        return ""

    links = ""

    for lens, label in LENSES:
        if lens == current:
            links += (f'<span class="here" aria-current="page">'
                      f'{escape(label)}</span>')
            continue

        href = f"/{path}" + (f"?lens={lens}" if lens else "")
        links += f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'

    return f'<nav class="lensbar" aria-label="Lenses">{links}</nav>'


PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="/static/page.css">
<article>
<h1>{title}</h1>
<address>{byline}{date}</address>
{body}
</article>
{bar}
"""


def document(title, body, author_name="", author_url="", date="", path=""):
    """A whole page, ready to serve."""

    byline = escape(author_name or "")

    if byline and author_url:
        checked = safe_url(author_url)

        if checked:
            byline = f'<a href="{escape(checked, quote=True)}">{byline}</a>'

    return PAGE.format(
        title=escape(title or "Untitled"),
        byline=byline,
        date=f" &middot; {escape(date)}" if date else "",
        body=body,
        bar=lens_bar(path),
    )


# ----------------------------------------------------------------- lenses
#
# docs/format.md calls these lenses: projections of one canonical node
# list, never dialects with their own semantics. So the tree below adds no
# expressive power - it shows the same page a reader gets, with the
# structure that was always there made visible.
#
# It emits no script, deliberately. Published pages are served under
# `default-src 'none'`, and an inspector that needed JavaScript could not
# live on that origin at all. Everything here is static markup and a
# stylesheet, so pulling back the curtain costs the page nothing.


def _attr_rows(attrs):
    """Attributes grouped by family, because the family says what is owed."""

    if not attrs:
        return ""

    rows = ""

    for name in sorted(attrs):
        kind = fmt.family(name)
        rows += (
            f'<div class="attr {kind}">'
            f'<span class="family">{escape(kind)}</span>'
            f'<code class="name">{escape(name)}</code>'
            f'<span class="value">{escape(attrs[name])}</span>'
            f'</div>'
        )

    return f'<div class="attrs">{rows}</div>'


def tree(nodes, modules=frozenset()):
    """The node list as nested HTML, showing what a consumer would do."""

    items = ""

    for node in fmt.normalise(nodes):
        if isinstance(node, str):
            items += f'<li class="text">{escape(node)}</li>'
            continue

        tag = node["tag"]
        attrs = node["attrs"]
        # Gated the same way, so the structure view shows a section
        # whose condition cannot be checked as falling back - which is
        # exactly what a reader of that page would get.
        gated = any(fmt.family(name) == "require" for name in attrs)

        known = (tag in fmt.CORE_TAGS or tag in modules) and not gated

        # The one law, made visible: an unknown tag renders its children,
        # so a reader can see exactly which parts of this page a Level 0
        # consumer is showing as fallback.
        state = "known" if known else "fallback"
        note = "" if known else '<span class="note">falls back to children</span>'

        identifier = attrs.get("id")
        anchor = (f'<a class="id" id="{escape(identifier, quote=True)}" '
                  f'href="#{escape(identifier, quote=True)}">#{escape(identifier)}</a>'
                  if identifier else '<span class="anon">no id</span>')

        items += (
            f'<li class="node {state}">'
            f'<div class="head"><code class="tag">{escape(tag)}</code>'
            f'{anchor}{note}</div>'
            f'{_attr_rows(attrs)}'
            f'{tree(node["children"], modules) if node["children"] else ""}'
            f'</li>'
        )

    return f'<ol class="tree">{items}</ol>' if items else ""


TREE_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} &mdash; structure</title>
<link rel="stylesheet" href="/static/page.css">
<article class="lens">
<h1>{title}</h1>
<p class="lensnote">The structure of this page: every node, what a
consumer does with it, and which of them can be addressed.</p>
<dl class="facts">
<dt>digest</dt><dd><code>{digest}</code></dd>
<dt>revision</dt><dd>{revision}</dd>
<dt>tags</dt><dd>{tags}</dd>
<dt>falls back on</dt><dd>{fallbacks}</dd>
</dl>
{body}
</article>
{bar}
"""


def tree_document(title, nodes, path, digest, revision, modules=frozenset()):
    """The tree lens, whole."""

    used = sorted(fmt.tags_used(nodes))
    missing = sorted(fmt.unsupported(nodes, set(fmt.CORE_TAGS) | set(modules)))

    return TREE_PAGE.format(
        title=escape(title or "Untitled"),
        path=escape(f"/{path}", quote=True),
        digest=escape(digest),
        revision=revision,
        tags=escape(", ".join(used)) or "none",
        # Nothing here is a failure. Falling back is the normal path for a
        # Level 0 consumer, which this renderer deliberately is.
        fallbacks=escape(", ".join(missing)) or "nothing",
        body=tree(nodes, modules),
        bar=lens_bar(path, "tree"),
    )
