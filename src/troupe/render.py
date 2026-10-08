"""Printing a configuration subtree as block YAML for `show`, optionally naming each scalar's file.

The output is one canonical layout (two-space indentation, compact `- key: v` items), not the user's own
formatting. Scalars are written by the same helpers `set` uses for new values, so quoting and literal blocks
follow one rule.
"""

from dataclasses import dataclass
from pathlib import Path

from troupe.edit.blocks import literal
from troupe.edit.scalars import render_key, render_scalar
from troupe.edit.text import Layout
from troupe.schema import Scalar
from troupe.source import SourceFile, source_label
from troupe.tree import MappingNode, Node, ScalarNode, SequenceNode, TextNode

INDENT = 2
_LAYOUT = Layout(unit=INDENT, seq_offset=INDENT)
SOURCE_COMMENT = " # from {}"


@dataclass(frozen=True)
class Line:
    text: str
    source: SourceFile | None = None  # set only on a line that holds a scalar value


def render(node: Node, theatre: Path, *, sources: bool) -> str:
    """`node` as a YAML document; with `sources`, every scalar's line ends with `# from <file>`."""
    if isinstance(node, MappingNode) and node.entries:
        lines = _mapping_lines(node, 0)
    elif isinstance(node, SequenceNode) and node.items:
        lines = _sequence_lines(node, 0)
    else:
        inline, source, rest = _value(node, -1)
        lines = [Line(inline, source), *rest]
    out = []
    for line in lines:
        comment = SOURCE_COMMENT.format(source_label(line.source, theatre)) if sources and line.source else ""
        out.append(line.text + comment + "\n")
    return "".join(out)


def _value(node: Node, owner_col: int) -> tuple[str, SourceFile | None, list[Line]]:
    """A value owned by a key or `-` at `owner_col`: text on the owner's line, its source, lines below."""
    if isinstance(node, MappingNode):
        return ("", None, _mapping_lines(node, owner_col + INDENT)) if node.entries else ("{}", None, [])
    if isinstance(node, SequenceNode):
        return ("", None, _sequence_lines(node, owner_col + INDENT)) if node.items else ("[]", None, [])
    if isinstance(node, TextNode):
        return _scalar(node.value, node.target, owner_col, block=True)
    assert isinstance(node, ScalarNode)
    return _scalar(node.value, node.file, owner_col, block=isinstance(node.value, str) and "\n" in node.value)


def _scalar(
    value: Scalar, source: SourceFile, owner_col: int, *, block: bool
) -> tuple[str, SourceFile | None, list[Line]]:
    if block and isinstance(value, str):
        rendered = literal(value, owner_col, _LAYOUT)
        if rendered is not None:
            return rendered.inline, source, [Line(text) for text in rendered.lines]
    return render_scalar(value, None, flow=False), source, []


def _mapping_lines(node: MappingNode, col: int) -> list[Line]:
    lines: list[Line] = []
    for entry in node.entries:
        inline, source, rest = _value(entry.value, col)
        head = " " * col + render_key(entry.key, None, flow=False) + ":" + (" " + inline if inline else "")
        lines += [Line(head, source), *rest]
    return lines


def _sequence_lines(node: SequenceNode, col: int) -> list[Line]:
    lines: list[Line] = []
    for item in node.items:
        inline, source, rest = _value(item.value, col)
        if not inline:  # a non-empty collection: its first line joins the dash (compact `- key: v` form)
            first = rest[0]
            lines += [Line(" " * col + "- " + first.text[col + INDENT :], first.source), *rest[1:]]
        else:
            lines += [Line(" " * col + "- " + inline, source), *rest]
    return lines
