"""How `set` writes multi-line strings: literal blocks, block-scalar rewrites and folded re-wrapping."""

from collections.abc import Callable

import pytest

from conftest import Result


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param("p: x\nq: 1\n", "p", '"a\\nb\\n"', "p: |\n  a\n  b\nq: 1\n", id="plain-to-literal-clip"),
        pytest.param(
            "p: x\n", "p", '"a\\nb"', "p: |-\n  a\n  b\n", id="literal-strip-without-trailing-newline"
        ),
        pytest.param("p: 'x'\n", "p", '"a\\n\\n"', "p: |+\n  a\n\n", id="literal-keep-for-several-newlines"),
        pytest.param(
            "p: x  # c\n", "p", '"a\\nb\\n"', "p: |  # c\n  a\n  b\n", id="comment-stays-on-header-line"
        ),
        pytest.param("l:\n  - x\n", "l.0", '"a\\nb\\n"', "l:\n  - |\n    a\n    b\n", id="list-item-literal"),
        pytest.param(
            "a:\n    b: x\n", "a.b", '"a\\nb\\n"', "a:\n    b: |\n        a\n        b\n", id="file-indent"
        ),
        pytest.param(
            "p: x\n", "p", '"  lead\\nb\\n"', "p: |2\n    lead\n  b\n", id="leading-space-needs-indicator"
        ),
        pytest.param("p: x\n", "p", '"a\\n\\nb\\n"', "p: |\n  a\n\n  b\n", id="blank-line-inside"),
        pytest.param(
            "p: x\n", "p", '"a\\u0001\\nb"', 'p: "a\\x01\\nb"\n', id="control-char-falls-back-to-double"
        ),
        pytest.param("p: x\r\nq: 1\r\n", "p", '"a\\nb\\n"', "p: |\r\n  a\r\n  b\r\nq: 1\r\n", id="crlf"),
        pytest.param("a: 1\n", "p", '"a\\nb\\n"', "a: 1\np: |\n  a\n  b\n", id="new-key-literal"),
        pytest.param(
            "a: {b: 1}\n", "a.p", '"a\\nb\\n"', 'a: {b: 1, p: "a\\nb\\n"}\n', id="new-key-in-flow-is-double"
        ),
        pytest.param(
            "p: |\n  a\nq: 1\n", "p", "x", "p: |-\n  x\nq: 1\n", id="single-line-into-literal-keeps-block"
        ),
        pytest.param("p: |\n  a\nq: 1\n", "p", '"x\\n"', "p: |\n  x\nq: 1\n", id="literal-content-only"),
        pytest.param(
            "p: |+\n    a\n\nq: 1\n",
            "p",
            '"b\\n"',
            "p: |+\n    b\nq: 1\n",
            id="keep-chomping-kept-when-it-fits",
        ),
        pytest.param(
            "p: |+\n    a\n\nq: 1\n", "p", "b", "p: |-\n    b\nq: 1\n", id="chomping-changes-when-needed"
        ),
        pytest.param(
            "p: |-\n  a\n\nq: 1\n",
            "p",
            '"b\\nc"',
            "p: |-\n  b\n  c\n\nq: 1\n",
            id="layout-blank-after-strip-kept",
        ),
        pytest.param("p: |2-\n    a\n", "p", '"  b"', "p: |2-\n    b\n", id="indicator-kept"),
        pytest.param("p: |  # note\n  a\n", "p", '"bb\\n"', "p: |  # note\n  bb\n", id="header-comment-kept"),
        pytest.param("p: |\n  a\n  b\nq: 1\n", "p", "5", "p: 5\nq: 1\n", id="block-to-number"),
        pytest.param("p: |\n  a\nq: 1\n", "p", "{x: 1}", "p:\n  x: 1\nq: 1\n", id="block-to-mapping"),
        pytest.param(
            "p:\n  x: 1\nq: 1\n", "p", '"a\\nb\\n"', "p: |\n  a\n  b\nq: 1\n", id="mapping-to-literal"
        ),
        pytest.param("p: |\n  a\n", "p", '"a\\n"', "p: |\n  a\n", id="unchanged-is-noop"),
    ],
)
def test_literal_blocks(set_file: Callable[..., str], before: str, path: str, value: str, after: str) -> None:
    assert set_file(before, path, value) == after


@pytest.mark.parametrize(
    ("before", "value", "after"),
    [
        pytest.param(
            "d: >\n  one two\n  three\n\n  alpha beta\n",
            '"one two three\\nalpha beta gamma\\n"',
            "d: >\n  one two\n  three\n\n  alpha beta\n  gamma\n",
            id="unchanged-paragraph-keeps-bytes",
        ),
        pytest.param(
            "d: >\n  aaa bb\n  c\n",
            '"aaa extraordinary b\\n"',
            "d: >\n  aaa\n  extraordinary\n  b\n",
            id="long-word-on-its-own-line",
        ),
        pytest.param(
            "d: >\n  one two\n\n  short\n",
            '"one two\\nshort\\nbrand new paragraph here\\n"',
            "d: >\n  one two\n\n  short\n\n  brand\n  new\n  paragraph\n  here\n",
            id="new-paragraph-wraps-at-overall-width",
        ),
        pytest.param(
            "d: >\n  keep me\n\n  drop me\n\n  last one\n",
            '"keep me\\nlast one\\n"',
            "d: >\n  keep me\n\n  last one\n",
            id="deleted-paragraph",
        ),
        pytest.param(
            "d: >-\n  a b\n  c\n",
            '"a b c d e f\\n"',
            "d: >\n  a b\n  c d\n  e f\n",
            id="chomping-follows-value",
        ),
        pytest.param(
            "d: >\n  a\n\n\n  bb cc\n",
            '"a\\n\\nbb cc dd\\n"',
            "d: >\n  a\n\n\n  bb cc\n  dd\n",
            id="extra-blank-lines-preserved",
        ),
        pytest.param("d: >\n  x\nz: 1\n", '"y\\n"', "d: >\n  y\nz: 1\n", id="single-word"),
    ],
)
def test_folded_blocks(set_file: Callable[..., str], before: str, value: str, after: str) -> None:
    assert set_file(before, "d", value) == after


@pytest.mark.parametrize("value", ['"a\\n  indented\\n"', '"\\tx\\n"', '" lead"'])
def test_more_indented_line_in_folded_is_refused(refused: Callable[..., Result], value: str) -> None:
    r = refused("d: >\n  some text\n", "d", value)
    assert r.code == 3 and "d" in r.err


def test_block_scalar_rewrite_in_crlf_file_uses_crlf(set_file: Callable[..., str]) -> None:
    assert set_file("p: |\r\n  a\r\nq: 1\r\n", "p", '"b\\nc\\n"') == "p: |\r\n  b\r\n  c\r\nq: 1\r\n"
    assert (
        set_file("d: >\r\n  aa bb\r\nq: 1\r\n", "d", '"aa bb cc\\n"') == "d: >\r\n  aa bb\r\n  cc\r\nq: 1\r\n"
    )
