"""The `!literal` tag: loading it (config-loading, "The `!literal` tag") and keeping it when a value changes
(config-set, "Writing literal strings")."""

from collections.abc import Callable

import pytest

from conftest import Result, Theatre


def test_literal_strings_load_as_strings_in_every_style(make: Callable[[str], Theatre]) -> None:
    t = make(
        'a: !literal https://example.com/api\nb: !literal 5\nc: !literal "file:x"\nd: !literal |\n  file:y\n'
    )
    r = t.run("show")
    assert (r.code, r.out) == (0, "a: https://example.com/api\nb: '5'\nc: file:x\nd: |\n  file:y\n"), r.err


def test_a_tagged_include_string_is_a_literal(make: Callable[[str], Theatre]) -> None:
    t = make("a: !literal file:nope.md\nb: !literal https://example.invalid/x.yaml\n")
    assert t.run("get", "a").out == "file:nope.md\n"
    assert t.run("get", "b").out == "https://example.invalid/x.yaml\n"


def test_a_literal_ref_does_not_make_a_mapping_form_include(make: Callable[[str], Theatre]) -> None:
    t = make("a:\n  $ref: !literal file:nope.yaml\n  b: 1\n")
    assert t.run("show", "a").out == "$ref: file:nope.yaml\nb: 1\n"


@pytest.mark.parametrize("config", ["a: !literal {b: 1}\n", "a: !literal\n  - 1\n", "a: !secret x\n"])
def test_literal_on_a_collection_and_other_tags_fail_to_load(
    make: Callable[[str], Theatre], config: str
) -> None:
    t = make(config)
    for args in (("show",), ("get", "a"), ("history",)):
        r = t.run(*args)
        assert (r.code, r.out) == (4, "") and "troupe.yml" in r.err


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        ("docs: !literal https://a.example.invalid\nb: 1\n", "docs", "other", "docs: !literal other\nb: 1\n"),
        ("docs: !literal 'x'  # c\n", "docs", "file:y", "docs: !literal 'file:y' # c\n"),
        ("a: !literal file:x\n", "a", "5", "a: 5\n"),
        ("a: !literal file:x\n", "a", "null", "a: null\n"),
        ("a: !literal file:x\nb: 1\n", "a", "{c: 1}", "a:\n  c: 1\nb: 1\n"),
        ("a: !literal\nb: 1\n", "a", "x", "a: !literal x\nb: 1\n"),
        ("a: &k !literal file:x\n", "a", "y", "a: &k !literal y\n"),
        ("a: !literal |\n  file:y\n  z\n", "a", '"p\\nq\\n"', "a: !literal |\n  p\n  q\n"),
        ("a: !literal |\n  file:y\n", "a", "7", "a: 7\n"),
    ],
)
def test_writing_over_a_literal_scalar(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


def test_other_tags_are_still_not_rewritten(refused: Callable[..., Result]) -> None:
    assert refused("a: !!str 5\n", "a", "6").code == 3


def test_expanding_an_alias_keeps_a_literal_in_the_copy(make: Callable[[str], Theatre]) -> None:
    t = make("base: &b\n  u: !literal file:q\nc: *b\n")
    r = t.run("set", "--expand-alias", "c.v", "1")
    assert (r.code, r.err) == (0, "")
    assert (
        t.read("troupe.yml")
        == "base: &b\n  u: !literal file:q\nc:  # expanded from *b by troupe\n  u: !literal file:q\n  v: 1\n"
    )
    assert t.run("get", "c.u").out == "file:q\n"
