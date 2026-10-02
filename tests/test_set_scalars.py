"""How `set` writes scalars: quoting styles, escaping and end-of-line comments."""

from collections.abc import Callable

import pytest


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param('a: "x"\n', "a", "y", 'a: "y"\n', id="double-quoted-style-kept"),
        pytest.param("a: 'x'\n", "a", "y", "a: 'y'\n", id="single-quoted-style-kept"),
        pytest.param("a: x\n", "a", "y z", "a: y z\n", id="plain-style-kept"),
        pytest.param("a: x\n", "a", '"true"', "a: 'true'\n", id="plain-cannot-hold-true-string-so-single"),
        pytest.param("a: x\n", "a", '"1.5"', "a: '1.5'\n", id="plain-cannot-hold-number-string-so-single"),
        pytest.param("a: x\n", "a", '"a: b"', "a: 'a: b'\n", id="plain-cannot-hold-colon-space"),
        pytest.param("a: x\n", "a", '"it\'s # hash"', "a: 'it''s # hash'\n", id="single-quote-doubled"),
        pytest.param("a: x\n", "a", '"tab\\there"', "a: 'tab\there'\n", id="tab-is-allowed-in-single-quotes"),
        pytest.param("a: 'x'\n", "a", '"bell\\a"', 'a: "bell\\a"\n', id="control-char-needs-double"),
        pytest.param("a: '1'\n", "a", "2", "a: 2\n", id="quoted-string-to-number-is-plain"),
        pytest.param('a: "x"\n', "a", "true", "a: true\n", id="quoted-string-to-bool-is-plain"),
        pytest.param("a: 1\n", "a", "null", "a: null\n", id="number-to-null"),
        pytest.param("a: 1\n", "a", "0.5", "a: 0.5\n", id="int-to-float"),
        pytest.param("a: 1\n", "a", "0x10", "a: 16\n", id="hex-written-canonical"),
        pytest.param("a: 1\n", "a", ".inf", "a: .inf\n", id="infinity"),
        pytest.param("a: x\n", "a", '""', "a: ''\n", id="empty-string-quoted"),
        pytest.param(
            'a: "x"\n', "a", '"é\\ttab"', 'a: "é\\ttab"\n', id="double-quoted-only-escapes-required"
        ),
        pytest.param(
            'a: "x"\n', "a", '"q\\"b\\\\s"', 'a: "q\\"b\\\\s"\n', id="double-quoted-escapes-quote-backslash"
        ),
        pytest.param('a: "x"\n', "a", '"\\u0085\\u0001\\x7f"', 'a: "\\N\\x01\\x7f"\n', id="control-escapes"),
        pytest.param('a: "x"\n', "a", '"日本 ☃"', 'a: "日本 ☃"\n', id="unicode-literal"),
        pytest.param("- a\n- b\n", "1", "c", "- a\n- c\n", id="root-list-item"),
        pytest.param(
            "a: {b: 1, c: x}\n", "a.c", '"y, z"', "a: {b: 1, c: 'y, z'}\n", id="flow-plain-cannot-hold-comma"
        ),
        pytest.param("a: [x, y]\n", "a.0", "long-value", "a: [long-value, y]\n", id="flow-list-item"),
        pytest.param("a: x\r\nb: y\r\n", "a", "zz", "a: zz\r\nb: y\r\n", id="crlf-file"),
    ],
)
def test_scalar_quoting(set_file: Callable[..., str], before: str, path: str, value: str, after: str) -> None:
    assert set_file(before, path, value) == after


@pytest.mark.parametrize(
    ("before", "value", "after"),
    [
        pytest.param("a: long  # c\n", "x", "a: x     # c\n", id="shorter-value-keeps-comment-column"),
        pytest.param("a: x  # c\n", "longer", "a: longer # c\n", id="value-reaching-column-leaves-one-space"),
        pytest.param("a: x     # c\n", "abc", "a: abc   # c\n", id="longer-value-before-column"),
        pytest.param("a: 'é'  # c\n", "'ü'", "a: 'ü'  # c\n", id="same-length-unchanged-padding"),
        pytest.param("a: ééé  # c\n", "x", "a: x    # c\n", id="columns-count-code-points"),
        pytest.param("a: 'x # no' # c\n", "y", "a: 'y'      # c\n", id="hash-inside-quotes-is-not-a-comment"),
        pytest.param("a: x # c\r\nb: 1\r\n", "yyy", "a: yyy # c\r\nb: 1\r\n", id="crlf-comment"),
    ],
)
def test_end_of_line_comment_alignment(
    set_file: Callable[..., str], before: str, value: str, after: str
) -> None:
    assert set_file(before, "a", value) == after


def test_comment_after_flow_collection_keeps_column(set_file: Callable[..., str]) -> None:
    assert set_file("a: {b: 1, c: 2}   # c\n", "a.b", "100") == "a: {b: 100, c: 2} # c\n"
    assert set_file("a: {b: 100, c: 2}   # c\n", "a.b", "1") == "a: {b: 1, c: 2}     # c\n"


def test_multiline_plain_scalar_is_replaced_whole(set_file: Callable[..., str]) -> None:
    assert set_file("a: one\n  two\nb: 1\n", "a", "x") == "a: x\nb: 1\n"
