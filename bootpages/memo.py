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

import re

from .format import FormatError

# Lowercase and hyphenated. The narrowness IS the disambiguation - it is
# what lets prose contain a colon without ceremony.
KEY = re.compile(r"^([a-z][a-z0-9-]*):[ \t]*(.*)$")

HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")

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

        if HEADING.match(lines[index]):
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
        if HEADING.match(lines[index]):
            break

        run.append(lines[index].strip())
        index += 1

    return {"tag": "p", "children": [" ".join(run)]}, index
