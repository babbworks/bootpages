"""
The format is the risk surface, so this is the suite that matters.

A page stored wrong cannot be fixed later without breaking pages that
already exist, and a digest that is not stable makes revision markers
meaningless.
"""

import pytest

from bootpages import format as fmt


# ------------------------------------------------------------ normalising


def test_all_three_fields_are_filled_in():
    """
    A client may post terse JSON and never type an empty brace. The store
    fills in the blanks on write - the only transformation it may perform,
    and permitted only because it demonstrably preserves meaning.
    """

    assert fmt.normalise([{"tag": "li", "children": ["North"]}]) == [
        {"tag": "li", "attrs": {}, "children": ["North"]}
    ]


def test_bare_strings_are_text():
    assert fmt.normalise(["Hello"]) == ["Hello"]


def test_nesting_is_normalised_all_the_way_down():
    tree = fmt.normalise([{"tag": "ul", "children": [{"tag": "li"}]}])

    assert tree[0]["children"][0] == {"tag": "li", "attrs": {}, "children": []}


def test_a_fourth_field_is_refused():
    """
    Accepting one would mean storing something no other implementation
    knows to read, and silently changing what the page hashes to.
    """

    with pytest.raises(fmt.FormatError, match="exactly tag, attrs and children"):
        fmt.normalise([{"tag": "p", "style": "red"}])


def test_a_node_without_a_tag_is_refused():
    with pytest.raises(fmt.FormatError, match="missing tag"):
        fmt.normalise([{"attrs": {}}])


def test_errors_name_the_offending_path():
    with pytest.raises(fmt.FormatError, match=r"content\[1\]"):
        fmt.normalise(["fine", {"attrs": {}}])


# ---------------------------------------------------------- opacity


def test_attribute_values_must_be_strings():
    """
    A number here reintroduces the one thing that makes canonicalisation
    hard - 1, 1.0 and 1e0 are one value with several spellings - in the
    component that must agree with itself for decades.
    """

    with pytest.raises(fmt.FormatError, match="values are strings"):
        fmt.normalise([{"tag": "chart", "attrs": {"max": 100}}])


def test_booleans_are_not_strings_either():
    with pytest.raises(fmt.FormatError, match="values are strings"):
        fmt.normalise([{"tag": "chart", "attrs": {"live": True}}])


def test_nested_structure_in_attrs_is_refused():
    with pytest.raises(fmt.FormatError, match="Structure goes in children"):
        fmt.normalise([{"tag": "chart", "attrs": {"axis": {"grid": "true"}}}])


# ------------------------------------------------------------- canonical


def test_two_spellings_converge():
    """The whole point. Same content, different JSON, one fingerprint."""

    one = [{"children": ["Hello"], "tag": "p"}]
    two = [{"tag": "p", "attrs": {}, "children": ["Hello"]}]

    assert fmt.canonical(one) == fmt.canonical(two)
    assert fmt.digest(one) == fmt.digest(two)


def test_canonical_is_one_line():
    line = fmt.canonical([{"tag": "p", "children": ["Hello"]}])

    assert "\n" not in line
    assert line == '[{"attrs":{},"children":["Hello"],"tag":"p"}]'


def test_attribute_order_does_not_change_the_digest():
    one = [{"tag": "map", "attrs": {"zoom": "11", "centre": "Truro"}}]
    two = [{"tag": "map", "attrs": {"centre": "Truro", "zoom": "11"}}]

    assert fmt.digest(one) == fmt.digest(two)


def test_non_ascii_is_written_literally():
    """
    Escaping is a second spelling. `café` and `caf\\u00e9` are one string
    and must not be two fingerprints.
    """

    assert "café" in fmt.canonical([{"tag": "p", "children": ["café"]}])


def test_content_changes_change_the_digest():
    before = fmt.digest([{"tag": "p", "children": ["Hello"]}])
    after = fmt.digest([{"tag": "p", "children": ["Goodbye"]}])

    assert before != after


def test_digest_is_labelled():
    """
    Never a bare hex string. The label is what lets the recipe and the
    algorithm each be replaced without redefining every digest ever issued.
    """

    value = fmt.digest([{"tag": "p", "children": ["Hello"]}])

    assert value.startswith("bp1-sha256:")
    assert len(value.split(":")[1]) == 64


def test_digest_is_stable_across_runs():
    """
    Pinned deliberately. If this value ever changes, every digest issued
    before the change silently means something else - which is exactly the
    failure the recipe label exists to make visible.
    """

    assert fmt.digest([{"tag": "p", "children": ["Hello"]}]) == (
        "bp1-sha256:"
        "76500c7aeed06bff02829ae495c029eae123283a1af813b43f854e481c83dfce"
    )


# ------------------------------------------------------------- families


def test_families_are_read_from_the_prefix():
    assert fmt.family("require-role") == "require"
    assert fmt.family("prefer-layout") == "prefer"
    assert fmt.family("on-select") == "on"
    assert fmt.family("meta-author") == "meta"
    assert fmt.family("source") == "structural"


def test_only_preferences_are_advisory():
    assert fmt.is_advisory("prefer-layout")
    assert not fmt.is_advisory("require-role")
    assert not fmt.is_advisory("source")


# --------------------------------------------------------- conformance


def test_stripping_preferences_leaves_everything_else():
    page = [{"tag": "map",
             "attrs": {"centre": "Truro", "prefer-emphasis": "high"},
             "children": [{"tag": "p",
                           "attrs": {"prefer-density": "tight"},
                           "children": ["Offices."]}]}]

    stripped = fmt.strip_preferences(page)

    assert stripped[0]["attrs"] == {"centre": "Truro"}
    assert stripped[0]["children"][0]["attrs"] == {}


def test_tags_used_walks_the_whole_tree():
    page = [{"tag": "columns", "children": [
        {"tag": "chart", "children": [{"tag": "p", "children": ["x"]}]}]}]

    assert fmt.tags_used(page) == {"columns", "chart", "p"}


def test_unsupported_is_what_a_consumer_falls_back_on():
    page = [{"tag": "map", "children": [{"tag": "p", "children": ["x"]}]}]

    assert fmt.unsupported(page, fmt.CORE_TAGS) == {"map"}


def test_a_telegraph_page_needs_no_fallbacks():
    """
    Compatibility as a consequence of the type system: a page whose tags
    are all core is a Telegraph page, and nothing has to convert it.
    """

    page = [{"tag": "p", "children": ["Ordinary prose."]},
            {"tag": "blockquote", "children": ["A quotation."]}]

    assert fmt.unsupported(page, fmt.CORE_TAGS) == set()
