"""
Markdown to nodes.

A converter that silently drops what it does not understand is how a
published page comes to differ from its source without anyone noticing, so
the interesting tests here are the refusals.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import publish                                    # noqa: E402

from bootpages import format as fmt               # noqa: E402


def test_headings_start_at_h3_because_the_format_has_no_h1_or_h2():
    """
    render.document() emits the h1 for the title, so content headings
    begin below it. A `#` heading that became h1 would collide with it;
    one that became h2 would hit the fallback and render as bare text.
    """

    assert publish.blocks("# Top")[0]["tag"] == "h3"
    assert publish.blocks("## Second")[0]["tag"] == "h3"
    assert publish.blocks("#### Fourth")[0]["tag"] == "h4"
    assert publish.blocks("##### Fifth")[0]["tag"] == "h4"


def test_paragraphs_join_wrapped_lines():
    nodes = publish.blocks("one\ntwo\n\nthree")

    assert [n["tag"] for n in nodes] == ["p", "p"]
    assert nodes[0]["children"] == ["one two"]


def test_inline_spans():
    nodes = publish.blocks("plain **bold** and `code` and *slanted*")
    tags = [c["tag"] for c in nodes[0]["children"] if isinstance(c, dict)]

    assert tags == ["strong", "code", "em"]


def test_links_carry_href():
    node = publish.blocks("see [the docs](https://example.com/x)")[0]
    link = [c for c in node["children"] if isinstance(c, dict)][0]

    assert link["tag"] == "a"
    assert link["attrs"]["href"] == "https://example.com/x"
    assert link["children"] == ["the docs"]


def test_code_fence_keeps_its_lines_and_nests_in_pre():
    node = publish.blocks("```\nfirst\n  second\n```")[0]

    assert node["tag"] == "pre"
    assert node["children"][0]["tag"] == "code"
    assert node["children"][0]["children"] == ["first\n  second"]


def test_lists():
    assert publish.blocks("- a\n- b")[0]["tag"] == "ul"
    assert publish.blocks("1. a\n2. b")[0]["tag"] == "ol"


def test_tables_are_refused_rather_than_mangled():
    """
    A table is a module, not a core tag. Rendering one as paragraphs would
    publish something quietly different from the source.
    """

    with pytest.raises(publish.SourceError, match="table"):
        publish.blocks("| a | b |\n|---|---|\n| 1 | 2 |")


def test_an_unclosed_fence_is_refused():
    with pytest.raises(publish.SourceError, match="unclosed"):
        publish.blocks("```\nnever closed")


def test_output_is_always_valid_for_the_store():
    """
    Whatever comes out must survive normalise, or publishing fails at the
    far end with a less useful message.
    """

    source = (
        "# Title\n\nProse with **bold**.\n\n- one\n- two\n\n"
        "```\ncode\n```\n\n---\n\n> quoted\n\n#### Sub\n"
    )

    nodes = publish.blocks(source)

    fmt.normalise(nodes)
    assert fmt.tags_used(nodes) <= fmt.CORE_TAGS
