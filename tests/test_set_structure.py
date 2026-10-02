"""How `set` adds, appends, replaces and deletes entries in block and flow collections."""

from collections.abc import Callable

import pytest


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param(
            "agents:\n  coder:\n    model: m\n",
            "agents.coder.temperature",
            "0.2",
            "agents:\n  coder:\n    model: m\n    temperature: 0.2\n",
            id="new-key-in-nested-mapping",
        ),
        pytest.param(
            "a: 1\n", "b.c.d", "x", "a: 1\nb:\n  c:\n    d: x\n", id="missing-intermediates-created"
        ),
        pytest.param(
            "a:\n    b: 1\n",
            "x.y",
            "1",
            "a:\n    b: 1\nx:\n    y: 1\n",
            id="intermediates-use-file-indentation",
        ),
        pytest.param(
            "a: 1\r\nb:\r\n  c: 2\r\n", "b.d", "3", "a: 1\r\nb:\r\n  c: 2\r\n  d: 3\r\n", id="crlf-new-key"
        ),
        pytest.param("a: 1", "b", "2", "a: 1\nb: 2\n", id="file-without-final-newline-gets-one"),
        pytest.param("", "a", "1", "a: 1\n", id="empty-file"),
        pytest.param("# just a comment\n", "a", "1", "# just a comment\na: 1\n", id="comment-only-file"),
        pytest.param(
            "m:\n  \"k1\": 'v1'\n",
            "m.k2",
            "v2",
            "m:\n  \"k1\": 'v1'\n  \"k2\": 'v2'\n",
            id="copies-sibling-styles",
        ),
        pytest.param(
            "m:\n  'k1': 1\n", "m.k2", "v", "m:\n  'k1': 1\n  'k2': v\n", id="key-style-copied-value-plain"
        ),
        pytest.param(
            'm:\n  k1: "v"\n', "m.k2", "5", 'm:\n  k1: "v"\n  k2: 5\n', id="non-string-ignores-style"
        ),
        pytest.param("m:\n  k: x\n", "m.true", "1", "m:\n  k: x\n  'true': 1\n", id="key-needing-quotes"),
        pytest.param(
            "a:\n  b: 1\n  # more b things\n\n# about c\nc: 2\n",
            "a.x",
            "1",
            "a:\n  b: 1\n  # more b things\n  x: 1\n\n# about c\nc: 2\n",
            id="below-trailing-comments",
        ),
        pytest.param(
            "a:\n  b: 1\n    # deeper comment\n# less indented\n  # after\nc: 2\n",
            "a.x",
            "1",
            "a:\n  b: 1\n    # deeper comment\n  x: 1\n# less indented\n  # after\nc: 2\n",
            id="less-indented-comment-ends-collection",
        ),
        pytest.param(
            "a:\n  b:\n    c: 1\n  # trailing\nz: 0\n",
            "a.d",
            "2",
            "a:\n  b:\n    c: 1\n  # trailing\n  d: 2\nz: 0\n",
            id="after-nested-value",
        ),
        pytest.param("a: 1\n# end\n", "b", "2", "a: 1\n# end\nb: 2\n", id="root-after-trailing-comment"),
        pytest.param(
            "a:\n    b: 1\n",
            "c",
            "{d: 1, e: [x, y]}",
            "a:\n    b: 1\nc:\n    d: 1\n    e:\n        - x\n        - y\n",
            id="block-collection-at-file-indent",
        ),
        pytest.param(
            "a:\n- x\nb:\n  c: 1\n",
            "d",
            "[1, 2]",
            "a:\n- x\nb:\n  c: 1\nd:\n- 1\n- 2\n",
            id="indentless-lists-stay",
        ),
        pytest.param("a: 1\n", "b", "{}", "a: 1\nb: {}\n", id="empty-mapping-is-flow"),
        pytest.param("a: 1\n", "b", "[]", "a: 1\nb: []\n", id="empty-list-is-flow"),
        pytest.param(
            "a: 1\n",
            "b",
            "[{n: 1, m: 2}, [x, y]]",
            "a: 1\nb:\n  - n: 1\n    m: 2\n  - - x\n    - y\n",
            id="nested-lists-compact",
        ),
    ],
)
def test_new_keys(set_file: Callable[..., str], before: str, path: str, value: str, after: str) -> None:
    assert set_file(before, path, value) == after


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param(
            "tools:\n  - a\n  - b\n", "tools.2", "c", "tools:\n  - a\n  - b\n  - c\n", id="block-append"
        ),
        pytest.param("tools:\n- a\n", "tools.1", "b", "tools:\n- a\n- b\n", id="indentless-append"),
        pytest.param(
            "tools:\n  - 'a'\n", "tools.1", "b", "tools:\n  - 'a'\n  - 'b'\n", id="copies-item-style"
        ),
        pytest.param(
            "tools:\n  - a\n  # more tools\nx: 1\n",
            "tools.1",
            "b",
            "tools:\n  - a\n  # more tools\n  - b\nx: 1\n",
            id="below-trailing-comment",
        ),
        pytest.param(
            "l:\n  - n: 1\n",
            "l.1",
            "{n: 2, m: [a]}",
            "l:\n  - n: 1\n  - n: 2\n    m:\n      - a\n",
            id="mapping-item",
        ),
        pytest.param("t: [a, b]\n", "t.2", "c", "t: [a, b, c]\n", id="flow-append"),
        pytest.param("t: []\n", "t.0", "c", "t: [c]\n", id="empty-flow-append"),
        pytest.param(
            "t: [a,\n  b]  # c\n", "t.2", "z", "t: [a,\n  b, z] # c\n", id="flow-append-on-last-line"
        ),
        pytest.param("a: {b: 1}\n", "a.c", "[1, 2]", "a: {b: 1, c: [1, 2]}\n", id="flow-mapping-new-key"),
        pytest.param("a: {}\n", "a.c", "{d: x}", "a: {c: {d: x}}\n", id="empty-flow-mapping"),
        pytest.param("a: {b: 1}\n", "a.c.d", "x", "a: {b: 1, c: {d: x}}\n", id="flow-intermediates"),
        pytest.param('a: {"b": 1}\n', "a.c", "x", 'a: {"b": 1, "c": x}\n', id="flow-key-style"),
    ],
)
def test_appends_and_flow_entries(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param(
            "a: 1  # note\n", "a", "{b: 2}", "a:    # note\n  b: 2\n", id="scalar-to-mapping-keeps-comment"
        ),
        pytest.param("a: 1\n", "a", "[x]", "a:\n  - x\n", id="scalar-to-list-without-comment"),
        pytest.param("a: 1\nb: 2\n", "a", "{c: 1}", "a:\n  c: 1\nb: 2\n", id="scalar-to-mapping-mid-file"),
        pytest.param("l:\n  - 1\n", "l.0", "{c: 1}", "l:\n  -\n    c: 1\n", id="list-item-scalar-to-mapping"),
        pytest.param("a:\n  b: 1\n  c: 2\nz: 0\n", "a", "5", "a: 5\nz: 0\n", id="mapping-to-scalar"),
        pytest.param(
            "a:  # keep\n  b: 1\nz: 0\n", "a", "5", "a: 5 # keep\nz: 0\n", id="mapping-to-scalar-comment"
        ),
        pytest.param("a:\n  b: 1\n", "a", "[x, y]", "a:\n  - x\n  - y\n", id="mapping-to-list"),
        pytest.param("a: [1, 2]\n", "a", "{b: 1}", "a:\n  b: 1\n", id="flow-list-to-mapping"),
        pytest.param("a:\n  b: 1\n", "a", "{}", "a: {}\n", id="mapping-emptied"),
        pytest.param(
            "l:\n  - a: 1\n    b: 2\n  - z\n", "l.0", "x", "l:\n  - x\n  - z\n", id="compact-item-to-scalar"
        ),
        pytest.param("l:\n  - a: 1\n", "l.0", "[p, q]", "l:\n  - - p\n    - q\n", id="compact-item-to-list"),
        pytest.param("a: {b: 1, c: 2}\n", "a.b", "[x]", "a: {b: [x], c: 2}\n", id="flow-parent-flow-value"),
        pytest.param("a: [1, {b: 2}]\n", "a.1", '"x\\ny"', 'a: [1, "x\\ny"]\n', id="flow-parent-multiline"),
    ],
)
def test_replacing_values(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param(
            "a:\n  b: 1  # keep\n  c: 2\n",
            "a",
            "{b: 1, c: 3}",
            "a:\n  b: 1  # keep\n  c: 3\n",
            id="partial-update",
        ),
        pytest.param("a:\n  b: 1\n  c: 2\n", "a", "{b: 1}", "a:\n  b: 1\n", id="key-removed"),
        pytest.param(
            "a:\n  # about b\n  b: 1\n  c:\n    d: 1\n  # trailing\n",
            "a",
            "{b: 1}",
            "a:\n  # about b\n  b: 1\n  # trailing\n",
            id="nested-entry-removed-comments-kept",
        ),
        pytest.param("a:\n  b: 1\n", "a", "{c: 2}", "a:\n  c: 2\n", id="all-keys-replaced"),
        pytest.param("l: [a, b, c]\n", "l", "[a, x]", "l: [a, x]\n", id="flow-list-diff"),
        pytest.param("l: [a, b, c]  # c\n", "l", "[b]", "l: [b]        # c\n", id="flow-list-shrinks"),
        pytest.param("m: {a: 1, b: 2}\n", "m", "{b: 2}", "m: {b: 2}\n", id="flow-first-entry-removed"),
        pytest.param("m: {a: 1, b: 2}\n", "m", "{a: 1}", "m: {a: 1}\n", id="flow-last-entry-removed"),
        pytest.param("l:\n  - a\n  - b\n  - c\n", "l", "[a]", "l:\n  - a\n", id="block-list-truncated"),
        pytest.param("l:\n  - a\n", "l", "[a, b]", "l:\n  - a\n  - b\n", id="block-list-extended"),
        pytest.param(
            "a:\n  b: 1\n  c: 2\n", "a", "{c: 2, b: 1}", "a:\n  b: 1\n  c: 2\n", id="key-order-ignored"
        ),
    ],
)
def test_collection_values_apply_as_a_diff(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


def test_deleting_the_first_entry_of_a_compact_item_pulls_the_next_up(set_file: Callable[..., str]) -> None:
    assert set_file("l:\n  - a: 1\n    b: 2\n", "l.0", "{b: 2}") == "l:\n  - b: 2\n"
    assert set_file("l:\n  - - x\n    - y\n", "l.0", "[x]") == "l:\n  - - x\n"


def test_kept_block_scalar_keeps_its_trailing_blank_lines_when_a_key_follows(
    set_file: Callable[..., str],
) -> None:
    assert set_file("p: |+\n  a\n\n", "q", "1") == "p: |+\n  a\n\nq: 1\n"


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param("a:\nb: 1\n", "a", "x", "a: x\nb: 1\n", id="scalar"),
        pytest.param("a:\n", "a", "x", "a: x\n", id="at-end-of-file"),
        pytest.param("a:   # c\nb: 1\n", "a", "x", "a: x # c\nb: 1\n", id="with-comment"),
        pytest.param("a:\nb: 1\n", "a", "{c: 1}", "a:\n  c: 1\nb: 1\n", id="mapping"),
        pytest.param("a:\nb: 1\n", "a", '"x\\ny\\n"', "a: |\n  x\n  y\nb: 1\n", id="literal"),
        pytest.param("l:\n  -\n  - b\n", "l.0", "x", "l:\n  - x\n  - b\n", id="empty-list-item"),
    ],
)
def test_filling_an_empty_value(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after
