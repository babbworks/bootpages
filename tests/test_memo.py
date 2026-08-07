"""
The memo lens.

The interesting tests are the disambiguation ones. docs/format.md claims
an author never has to escape anything, which is only true if "Note: this
matters" is reliably prose and `require-role: finance` is reliably a key.
"""

import pytest

from bootpages import format as fmt
from bootpages.memo import parse

SPEC_EXAMPLE = """title: Q3 Onboarding

## Welcome

Just write. Prose is prose - no markup, no keys, nothing to learn.
This becomes a run of paragraph nodes.

## Expenses
require-role: finance
source: https://finance.example.internal/q3
prefer-layout: table, list

If you have finance access, this section loads live figures.
Otherwise you are reading this sentence, which is the fallback.
"""


def test_the_example_from_the_specification_parses():
    fields, nodes = parse(SPEC_EXAMPLE)

    assert fields["title"] == "Q3 Onboarding"

    tags = [n["tag"] for n in nodes]
    assert tags == ["h3", "p", "h3", "section"]


def test_a_section_with_no_keys_is_just_prose():
    """
    "This becomes a run of paragraph nodes." Nothing to configure, so
    nothing to wrap.
    """

    _, nodes = parse("## Welcome\n\nOne.\n\nTwo.\n")

    assert [n["tag"] for n in nodes] == ["h3", "p", "p"]
    assert nodes[1]["children"] == ["One."]


def test_keys_under_a_heading_configure_the_section():
    _, nodes = parse(SPEC_EXAMPLE)
    section = nodes[3]

    assert section["attrs"] == {
        "require-role": "finance",
        "source": "https://finance.example.internal/q3",
        "prefer-layout": "table, list",
    }
    assert section["children"][0]["tag"] == "p"


def test_type_names_the_tag():
    _, nodes = parse("## Chart\ntype: chart\nref: #sales\n\nFallback text.\n")

    assert nodes[1]["tag"] == "chart"
    assert "type" not in nodes[1]["attrs"]
    assert nodes[1]["attrs"]["ref"] == "#sales"


def test_an_attributed_section_without_a_type_falls_back_by_the_one_law():
    """
    `section` is deliberately not a core tag. An unknown tag renders its
    children, so a consumer that never heard of it shows the prose - while
    a require- attribute on it still fails closed.
    """

    _, nodes = parse("## Expenses\nrequire-role: finance\n\nFallback.\n")

    assert nodes[1]["tag"] == "section"
    assert nodes[1]["tag"] not in fmt.CORE_TAGS
    assert nodes[1]["children"][0]["children"] == ["Fallback."]


# ------------------------------------------------------- disambiguation


def test_a_capitalised_colon_line_after_the_blank_is_prose():
    """
    The claim docs/format.md makes: no escaping, ever. `Note` is
    capitalised and sits after the blank line, so it is prose.
    """

    _, nodes = parse("## Heading\n\nNote: this matters a great deal.\n")

    assert [n["tag"] for n in nodes] == ["h3", "p"]
    assert nodes[1]["children"] == ["Note: this matters a great deal."]


def test_a_lowercase_colon_line_after_the_blank_is_still_prose():
    """
    Position decides as well as case. Keys are recognised only in the
    contiguous block directly under a heading.
    """

    _, nodes = parse("## Heading\n\nsee: the difference is where it sits.\n")

    assert nodes[1]["tag"] == "p"
    assert nodes[1]["children"][0].startswith("see:")


def test_a_url_in_prose_does_not_become_a_key():
    _, nodes = parse("## Heading\n\nRead https://example.com/x for more.\n")

    assert nodes[1]["tag"] == "p"


# -------------------------------------------------------------- refusals


def test_an_unknown_document_field_is_refused():
    """
    A header key that silently did nothing would be worse than one that is
    rejected: the author would believe it took effect.
    """

    with pytest.raises(fmt.FormatError, match="not a document field"):
        parse("title: Fine\naudience: new staff\n\n## X\n\nBody.\n")


def test_a_non_key_line_directly_under_a_heading_is_refused():
    with pytest.raises(fmt.FormatError, match="expected a `key: value`"):
        parse("## Expenses\nrequire-role: finance\nthis is not a key\n\nBody.\n")


# ------------------------------------------------------------- integration


def test_what_comes_out_is_an_ordinary_node_list():
    """
    A lens is a projection, never a dialect. Whatever this produces has to
    survive the same validation as a hand-written page.
    """

    _, nodes = parse(SPEC_EXAMPLE)

    fmt.normalise(nodes)
    fmt.check_ids(nodes)
    assert fmt.digest(nodes).startswith("bp1-sha256:")


def test_ids_written_in_a_memo_are_addressable():
    """
    Which is what makes subscription reachable from the authoring lens.
    """

    _, nodes = parse("## Sales\nid: sales\n\nFigures here.\n")

    assert fmt.check_ids(nodes) == {"sales": "content[1]"}
    assert fmt.subtree(nodes, "sales")[0]["children"][0]["children"] == [
        "Figures here."]


def test_headings_never_produce_h1_or_h2():
    _, nodes = parse("# One\n\na\n\n## Two\n\nb\n\n#### Four\n\nc\n")

    assert {n["tag"] for n in nodes if n["tag"].startswith("h")} == {"h3", "h4"}
