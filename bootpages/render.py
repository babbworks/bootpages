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

    known = tag in fmt.CORE_TAGS or tag in modules

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
"""


def document(title, body, author_name="", author_url="", date=""):
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
    )
