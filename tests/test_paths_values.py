import pytest

from troupe.errors import UsageError
from troupe.paths import parse_path
from troupe.schema import Data, same
from troupe.values import parse_value


def test_paths_split_on_dots() -> None:
    assert parse_path("agents.coder.model") == ("agents", "coder", "model")
    assert parse_path("tools.1") == ("tools", "1")


@pytest.mark.parametrize("text", ["", "a..b", "a.", ".a"])
def test_paths_with_empty_segments_are_usage_errors(text: str) -> None:
    with pytest.raises(UsageError, match="invalid path"):
        parse_path(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.2", 0.2),
        ("true", True),
        ("null", None),
        ("abc", "abc"),
        ('"0.2"', "0.2"),
        ("'x y'", "x y"),
        ("2001-01-01", "2001-01-01"),
        ("0x10", 16),
        ("", None),
        ("{a: 1}", {"a": 1}),
        ("[a, b]", ["a", "b"]),
        ("{a: [1, {b: c}]}", {"a": [1, {"b": "c"}]}),
        ('"line one\\nline two\\n"', "line one\nline two\n"),
        ('"é\\ttab"', "é\ttab"),
        ("file:x.md", "file:x.md"),
    ],
)
def test_values_parse_as_one_yaml_1_2_flow_node(text: str, expected: Data) -> None:
    assert same(parse_value(text), expected)


@pytest.mark.parametrize("text", ["[a, b", "a: b: c", "a: b", "- a", "|\n  x\n", "{a: 1", "&x a", "*x"])
def test_values_that_are_not_a_single_flow_node_are_usage_errors(text: str) -> None:
    with pytest.raises(UsageError, match="invalid VALUE"):
        parse_value(text)
