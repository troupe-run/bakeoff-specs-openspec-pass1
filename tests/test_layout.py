from pathlib import Path

import pytest

from troupe.edit.text import Layout, comment_start, detect_layout, insertion_point
from troupe.source import SourceFile


def src(text: str) -> SourceFile:
    return SourceFile(Path("t.yml"), text)


@pytest.mark.parametrize(
    ("text", "layout"),
    [
        ("a: 1\n", Layout(2, 2)),
        ("a:\n    b: 1\n", Layout(4, 4)),
        ("a:\n   b:\n      c: 1\nl:\n- x\n", Layout(3, 0)),
        ("l:\n  - x\nm:\n    k: 1\n", Layout(4, 2)),
        ("x: {a: {b: 1}}\nm:\n  k: 1\n", Layout(2, 2)),
    ],
)
def test_layout_is_detected_from_the_first_nested_block_collections(text: str, layout: Layout) -> None:
    assert detect_layout(src(text)) == layout


def test_comment_start_ignores_hashes_inside_quotes_and_words() -> None:
    s = src("a: 'x # y' \"q # r\" b#c  # real\n")
    assert comment_start(s, 0) == s.text.index("# real")
    assert comment_start(src("a: b#c\n"), 0) is None


def test_insertion_point_skips_comments_at_or_deeper_than_entries_and_stops_at_shallower() -> None:
    s = src("a:\n  b: 1\n\n  # c1\n    # c2\n\n# top\n  # after\n")
    assert insertion_point(s, s.text.index("1"), 2) == s.text.index("\n# top")
