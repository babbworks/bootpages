"""
The memo lens: the one people write in.

docs/format.md puts this first among the five lenses and states the whole
rule in a sentence - a heading opens a section, `key: value` lines
immediately beneath it configure it, everything after the first blank line
is its content.

Lineage is the header block that memos and mail have used for fifty
years, plus Markdown headings. That is deliberate: the structure of a
business document and the structure of a manifest are the same structure,
so an author who can write a memo can write a page.

A lens is a projection of the canonical node list, never a dialect with
its own semantics. Nothing here can express anything the tree cannot -
the moment it could, there would be two formats instead of one and they
would drift.

DISAMBIGUATION NEEDS NO ESCAPING
--------------------------------
Keys are lowercase and hyphenated only, and are recognised solely in the
contiguous block directly under a heading. So a paragraph beginning
"Note: this matters" is prose: `Note` is capitalised, and it sits after
the blank line. No author ever has to escape anything.
"""

import json
import re

from .format import FormatError

# Lowercase and hyphenated. The narrowness IS the disambiguation - it is
# what lets prose contain a colon without ceremony.
KEY = re.compile(r"^([a-z][a-z0-9-]*):[ \t]*(.*)$")

HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")

# A divider. Three or more of any of them, which is what every writer of
# Markdown already types, and unambiguous because prose does not begin a
# line that way.
RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")

# Header fields that mean something to the store. Anything else in the
# document header is refused rather than dropped, because a key that
# silently does nothing is worse than one that is rejected: the author
# believes it took effect.
DOCUMENT_FIELDS = ("title", "author", "author-url")

# The tag an attributed section becomes when it does not name one.
#
# Not a core tag, deliberately. An unknown tag renders its children, so a
# consumer that has never heard of `section` shows the prose inside it -
# which is exactly right - while `require-` attributes on it still fail
# closed. The one law does the work; nothing needed inventing.
DEFAULT_SECTION_TAG = "section"


def parse(source):
    """
    Memo text to `(fields, nodes)`.

    `fields` carries the document header - title and byline, which belong
    to the store rather than to the node list. `nodes` is an ordinary node
    list, indistinguishable from one written by hand.
    """

    lines = source.replace("\r\n", "\n").split("\n")
    index = 0

    fields, index = _document_header(lines, index)
    nodes = []

    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue

        if RULE.match(lines[index]):
            nodes.append({"tag": "hr", "attrs": {}, "children": []})
            index += 1
            continue

        heading = HEADING.match(lines[index])

        if heading:
            block, index = _section(lines, index)
            nodes.extend(block)
            continue

        paragraph, index = _paragraph(lines, index)
        nodes.append(paragraph)

    return fields, nodes


def _document_header(lines, index):
    """
    `key: value` lines before anything else, ending at the first blank.
    """

    fields = {}

    while index < len(lines) and lines[index].strip():
        if HEADING.match(lines[index]):
            break

        match = KEY.match(lines[index])

        if not match:
            break

        name, value = match.group(1), match.group(2).strip()

        if name not in DOCUMENT_FIELDS:
            raise FormatError(
                f"line {index + 1}: {name!r} is not a document field. "
                f"Expected one of {', '.join(DOCUMENT_FIELDS)}, or a blank "
                f"line before the body."
            )

        fields[name] = value
        index += 1

    return fields, index


def _section(lines, index):
    """
    A heading, the keys directly under it, and the content after the blank.
    """

    heading = HEADING.match(lines[index])
    depth, text = len(heading.group(1)), heading.group(2).strip()
    index += 1

    # The format has no h1 or h2: the renderer emits the h1 for the page
    # title, so content headings begin below it. Deeper than h4 flattens
    # rather than disappearing.
    nodes = [{"tag": "h4" if depth >= 3 else "h3", "children": [text]}]

    attrs = {}

    while index < len(lines) and lines[index].strip():
        match = KEY.match(lines[index])

        if not match:
            raise FormatError(
                f"line {index + 1}: expected a `key: value` line or a blank "
                f"line before the content of {text!r}. Keys are lowercase "
                f"and hyphenated."
            )

        attrs[match.group(1)] = match.group(2).strip()
        index += 1

    content = []

    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue

        if HEADING.match(lines[index]) or RULE.match(lines[index]):
            break

        paragraph, index = _paragraph(lines, index)
        content.append(paragraph)

    if not attrs:
        # Nothing to configure, so nothing to wrap. Prose is prose.
        return nodes + content, index

    tag = attrs.pop("type", DEFAULT_SECTION_TAG)

    nodes.append({"tag": tag, "attrs": attrs, "children": content})

    return nodes, index


def _paragraph(lines, index):
    """Wrapped lines up to the next blank or heading, joined."""

    run = []

    while index < len(lines) and lines[index].strip():
        if HEADING.match(lines[index]) or RULE.match(lines[index]):
            break

        run.append(lines[index].strip())
        index += 1

    return {"tag": "p", "children": [" ".join(run)]}, index


# ------------------------------------------------------------- projection


def render(nodes, fields=None):
    """
    A node list back to memo text.

    The other direction, which is what makes the memo a *lens* rather than
    an import format. A lens you can only write through is a converter;
    one you can read through as well is a view of the document, and the
    editor can then offer "edit this as text" over the same page rather
    than a second tool with its own idea of what a page is.

    Not every tree has a memo form - deep nesting has nowhere to go in a
    format whose whole shape is heading, keys, prose. Those nodes are
    written as a fenced block carrying their JSON, which round-trips
    through parse() as content rather than being lost. Honest, and ugly
    exactly where the document is doing something the lens cannot say.
    """

    out = []
    fields = fields or {}

    for name in DOCUMENT_FIELDS:
        if fields.get(name):
            out.append(f"{name}: {fields[name]}")

    if out:
        out.append("")

    index = 0

    while index < len(nodes):
        node = nodes[index]
        following = nodes[index + 1] if index + 1 < len(nodes) else None

        # A heading and the section it configures are one thing in this
        # lens, and must be emitted as one: the keys go IMMEDIATELY under
        # the heading, with no blank line, or they are prose when read
        # back. The rule that makes disambiguation free also makes the
        # blank line load-bearing.
        if _is_heading(node) and _is_section(following):
            out.append(_heading_line(node))
            out.extend(_keys(following))
            out.append("")
            out.extend(_prose(following.get("children") or []))
            index += 2
            continue

        out.extend(_emit(node))
        index += 1

    return "\n".join(out).rstrip() + "\n"


def _is_heading(node):
    return isinstance(node, dict) and node.get("tag") in ("h3", "h4")


def _is_section(node):
    """A node this lens can write as keys under a heading."""

    if not isinstance(node, dict) or not node.get("attrs"):
        return False

    return all(isinstance(kid, dict) and kid.get("tag") == "p"
               for kid in node.get("children") or [])


def _heading_line(node):
    prefix = "##" if node["tag"] == "h3" else "###"

    return f"{prefix} {_text(node.get('children') or [])}"


def _keys(node):
    attrs = dict(node.get("attrs") or {})
    lines = []

    if node.get("tag") != DEFAULT_SECTION_TAG:
        lines.append(f"type: {node['tag']}")

    lines.extend(f"{name}: {attrs[name]}" for name in sorted(attrs))

    return lines


def _prose(children):
    out = []

    for kid in children:
        out.append(_text(kid.get("children") or []))
        out.append("")

    return out


def _emit(node):
    if isinstance(node, str):
        return [node, ""]

    tag = node.get("tag")
    children = node.get("children") or []

    if _is_heading(node):
        return [_heading_line(node), ""]

    if tag == "hr" and not node.get("attrs"):
        return ["---", ""]

    if tag == "p" and not node.get("attrs"):
        return [_text(children), ""]

    if _is_section(node):
        # A section with no heading of its own still needs one to hang its
        # keys from, since the lens has nowhere else to put them.
        return ["## " + (node.get("attrs", {}).get("id") or tag)] + \
               _keys(node) + [""] + _prose(children)

    # Anything the lens cannot say, said plainly rather than lost.
    return ["```json", json.dumps(node, ensure_ascii=False), "```", ""]


def _text(children):
    return " ".join(c for c in children if isinstance(c, str)).strip()
