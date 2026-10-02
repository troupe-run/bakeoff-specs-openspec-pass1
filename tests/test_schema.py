import math

import pytest

from troupe.schema import Scalar, plain_text, resolve_plain, same, show_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("null", None),
        ("Null", None),
        ("NULL", None),
        ("~", None),
        ("", None),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", 0),
        ("-12", -12),
        ("+7", 7),
        ("0o17", 15),
        ("0x1F", 31),
        ("0.2", 0.2),
        ("-1.5e3", -1500.0),
        (".5", 0.5),
        ("1.", 1.0),
        (".inf", math.inf),
        ("-.Inf", -math.inf),
        ("+.INF", math.inf),
        ("abc", "abc"),
        ("yes", "yes"),
        ("on", "on"),
        ("2001-01-01", "2001-01-01"),
        ("1_000", "1_000"),
        ("0b101", "0b101"),
        ("nULL", "nULL"),
        ("tRUE", "tRUE"),
    ],
)
def test_plain_scalars_resolve_by_the_yaml_1_2_core_schema(text: str, expected: Scalar) -> None:
    value = resolve_plain(text)
    assert type(value) is type(expected) and value == expected


def test_nan_spellings_resolve_to_nan() -> None:
    for text in (".nan", ".NaN", ".NAN"):
        value = resolve_plain(text)
        assert isinstance(value, float) and math.isnan(value)


@pytest.mark.parametrize(
    ("value", "printed"),
    [
        ("hi", "hi\n"),
        ("hi\n", "hi\n"),
        ("a\nb", "a\nb\n"),
        ("", "\n"),
        (True, "true\n"),
        (False, "false\n"),
        (None, "null\n"),
        (31, "31\n"),
        (0.2, "0.2\n"),
        (1e20, "1e+20\n"),
        (math.inf, "inf\n"),
    ],
)
def test_show_prints_scalars_per_contract(value: Scalar, printed: str) -> None:
    assert show_text(value) == printed


@pytest.mark.parametrize("value", [None, True, 0, -3, 0.2, 1e20, math.inf, -math.inf])
def test_plain_text_of_a_non_string_reads_back_as_the_same_value(value: Scalar) -> None:
    assert same(resolve_plain(plain_text(value)), value)


def test_same_distinguishes_int_float_and_bool() -> None:
    assert not same(1, 1.0)
    assert not same(1, True)
    assert same(math.nan, math.nan)
    assert same({"a": 1, "b": 2}, {"b": 2, "a": 1})
    assert not same([1, 2], [2, 1])
