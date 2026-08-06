"""
The node model, the canonical form, and the digest.

This is the risk surface. Everything downstream inherits its correctness
from here, and format mistakes are the ones that cannot be fixed later
without breaking pages that already exist.

Pure functions only: no filesystem, no network, no clock. See
docs/format.md, which this implements and which wins where they disagree.
"""

import hashlib
import json
import re

# The canonicalisation recipe this module implements. It travels in every
# digest so that a value computed today still means something precise in
# forty years - recipes get refined and hash functions weaken, and a bare
# hex string records neither.
RECIPE = "bp1"
ALGORITHM = "sha256"


class FormatError(ValueError):
    """Something that cannot be stored. Always names the offending path."""


# The tag set Telegraph accepts, and therefore the set a Telegraph page can
# possibly contain. Closed, permanently: a bootpage whose tags are all in
# here IS a Telegraph page, which is what makes compatibility a consequence
# of the type system rather than a layer anyone maintains.
CORE_TAGS = frozenset({
    "a", "aside", "b", "blockquote", "br", "code", "em", "figcaption",
    "figure", "h3", "h4", "hr", "i", "iframe", "img", "li", "ol", "p",
    "pre", "s", "strong", "u", "ul", "video",
})

# Used by capability pages to describe what a site implements. Reserved
# here so that no site can define them as something else.
STRUCTURAL_TAGS = frozenset({"module", "attr"})

RESERVED_TAGS = CORE_TAGS | STRUCTURAL_TAGS

# Attribute families, in the order they are tested. See docs/format.md -
# the family decides what a consumer is obliged to do when it cannot
# honour the attribute.
PREFIXES = ("require-", "prefer-", "on-", "meta-")

# Everyone outside the specification uses one of these. The reasoning is
# the one that led HTML to demand a hyphen in custom element names: reserve
# the plain space early and the two never collide.
VENDOR_PREFIX = "x-"


def family(name):
    """
    Which family an attribute belongs to.

    Returns one of "require", "prefer", "on", "meta" or "structural".
    Structural means unprefixed - id, ref, source, and the core wiring.
    """

    for prefix in PREFIXES:
        if name.startswith(prefix):
            return prefix[:-1]

    return "structural"


def is_advisory(name):
    """
    Whether a consumer may ignore this attribute and remain conforming.

    Exactly the prefer- family, which is what makes the strip test
    meaningful: remove every advisory attribute and the page must still be
    complete and correct.
    """

    return family(name) == "prefer"


# ----------------------------------------------------------- normalising


def normalise(nodes, path="content"):
    """
    A node list in canonical shape: every node a string, or a dict with all
    three fields present.

    Filling in omitted fields is what the store does on write, and it is
    the only transformation a store may perform. A client may post
    {"tag": "li", "children": ["North"]} and never type an empty brace;
    what comes back has attrs. That is meaning-preserving, which is why it
    is permitted where rewriting anything else is not.
    """

    if not isinstance(nodes, list):
        raise FormatError(f"{path}: expected a list of nodes")

    return [_node(node, f"{path}[{index}]") for index, node in enumerate(nodes)]


def _node(node, path):
    # A bare string is text. It carries no attributes and has no children,
    # so there is nothing to fill in.
    if isinstance(node, str):
        return node

    if not isinstance(node, dict):
        raise FormatError(f"{path}: expected a string or an object")

    tag = node.get("tag")

    if not isinstance(tag, str) or not tag:
        raise FormatError(f"{path}: missing tag")

    unknown = set(node) - {"tag", "attrs", "children"}

    if unknown:
        # Refusing a fourth field is not pedantry. Accepting one would mean
        # storing something no other implementation knows to read, and
        # silently changing what the page hashes to.
        raise FormatError(
            f"{path}: unexpected field(s) {sorted(unknown)}. A node has "
            f"exactly tag, attrs and children."
        )

    return {
        "tag": tag,
        "attrs": _attrs(node.get("attrs") or {}, path),
        "children": normalise(node.get("children") or [], f"{path}.children"),
    }


# An id has to survive being a URL fragment and a query parameter, so the
# permitted shape is decided at write time rather than escaped at every
# read. 64 is generous for a name a person chose deliberately.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def check_ids(nodes, path="content"):
    """
    Every `id` in the tree, mapped to where it was found. Raises on a
    duplicate or a malformed one.

    Deliberately NOT part of normalise(). normalise runs on read as well -
    render.py calls it on every page - so putting this there would make a
    page containing a duplicate unservable rather than unpublishable, and
    would punish existing pages for a rule made after they were written.
    This runs on the write path only.

    The strictness is for subscription rather than for `ref`. A broken ref
    fails visibly: a block points at nothing and someone notices. An
    ambiguous subscription fails silently and in the wrong direction - a
    watcher resolves `#sales` to the first match, the author edits the
    second, and nothing errors. It simply stops being true.
    """

    found = {}
    _collect_ids(nodes, path, found)

    return found


def _collect_ids(nodes, path, found):
    if not isinstance(nodes, list):
        raise FormatError(f"{path}: expected a list of nodes")

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue

        here = f"{path}[{index}]"
        value = (node.get("attrs") or {}).get("id")

        if value is not None:
            if not isinstance(value, str) or not ID_PATTERN.match(value):
                raise FormatError(
                    f"{here}.attrs.id: {value!r} is not a usable id. Letters, "
                    f"digits, hyphen and underscore, up to 64 characters."
                )

            if value in found:
                raise FormatError(
                    f"duplicate id {value!r}: {found[value]} and {here}. An "
                    f"id addresses one node, and a ref or a subscription "
                    f"pointing at two of them is ambiguous."
                )

            found[value] = here

        _collect_ids(node.get("children") or [], f"{here}.children", found)


def _attrs(attrs, path):
    """
    Attribute values are strings. Nothing else survives this function.

    A number here would reintroduce the one thing that makes canonical JSON
    hard - 1, 1.0 and 1e0 are one value with several spellings - in the
    component that has to agree with itself for decades. A module may still
    declare that its value is an integer and read it as one; that is a
    typed read of a scalar, and it happens in the consumer, not here.
    """

    if not isinstance(attrs, dict):
        raise FormatError(f"{path}.attrs: expected an object")

    clean = {}

    for name, value in attrs.items():
        if not isinstance(name, str) or not name:
            raise FormatError(f"{path}.attrs: attribute names must be strings")

        if isinstance(value, bool) or not isinstance(value, str):
            raise FormatError(
                f"{path}.attrs.{name}: attribute values are strings. "
                f"Structure goes in children."
            )

        clean[name] = value

    return clean


# ------------------------------------------------------------- canonical


def canonical(nodes):
    """
    One line of text, identical for identical content.

    The steps, each removing one way two implementations can disagree:

      1. all three fields present          - normalise(), above
      2. object keys sorted                - sort_keys
      3. no insignificant whitespace       - separators
      4. UTF-8, minimal escaping           - ensure_ascii=False
      5. the whole list as one line        - no indent

    Sorting by Python string comparison is sorting by code point, and UTF-8
    is designed so that byte order and code point order agree. So this is
    bytewise sorting without having to say so.
    """

    return json.dumps(
        normalise(nodes),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def digest(nodes):
    """
    The fingerprint, labelled with how it was made.

    Never a bare hex string. The label is what lets the recipe and the
    algorithm each be replaced without silently redefining every digest
    ever issued.
    """

    line = canonical(nodes).encode("utf-8")

    return f"{RECIPE}-{ALGORITHM}:{hashlib.sha256(line).hexdigest()}"


# ------------------------------------------------------------ conformance


def strip_preferences(nodes):
    """
    The same page with every advisory attribute removed.

    The strip test: what comes back must still be complete and correct. If
    removing something breaks the page, it was never a preference.
    """

    stripped = []

    for node in normalise(nodes):
        if isinstance(node, str):
            stripped.append(node)
            continue

        stripped.append({
            "tag": node["tag"],
            "attrs": {
                name: value
                for name, value in node["attrs"].items()
                if not is_advisory(name)
            },
            "children": strip_preferences(node["children"]),
        })

    return stripped


def tags_used(nodes):
    """
    Every tag appearing in a page.

    This is how a consumer discovers what a page needs - the tags are the
    declaration, and no separate manifest is required. Also what an editor
    checks against a capability page.
    """

    found = set()

    for node in normalise(nodes):
        if isinstance(node, str):
            continue

        found.add(node["tag"])
        found |= tags_used(node["children"])

    return found


def unsupported(nodes, known):
    """Tags a consumer holding `known` would have to fall back on."""

    return {tag for tag in tags_used(nodes) if tag not in known}
