from pathlib import Path

from troupe.source import SourceFile
from troupe.tree import MappingNode, build_tree


def _value_text(text: str, key: str) -> str:
    src = SourceFile(Path("t.yml"), text)
    root = build_tree(src)
    assert isinstance(root, MappingNode)
    entry = root.get(key)
    assert entry is not None
    return text[entry.value.start : entry.value.end]


def test_marks_index_exact_characters_in_crlf_text() -> None:
    assert _value_text("a: 1\r\nb: 'two'\r\n", "b") == "'two'"


def test_marks_count_code_points_after_non_ascii_text() -> None:
    assert _value_text('é: ü\nnext: "ok"\n', "next") == '"ok"'


def test_newline_style_comes_from_the_first_line_break() -> None:
    assert SourceFile(Path("x"), "a\r\nb\n").newline == "\r\n"
    assert SourceFile(Path("x"), "a\nb\r\n").newline == "\n"
    assert SourceFile(Path("x"), "").newline == "\n"


def test_line_helpers_handle_crlf() -> None:
    src = SourceFile(Path("x"), "ab\r\ncd\r\n")
    assert src.line_end(0) == 2
    assert src.next_line(0) == 4
    assert src.line_start(5) == 4
    assert src.column(5) == 1
