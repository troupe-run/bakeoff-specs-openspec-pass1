"""Rendering new values for a block context: block collections and literal block scalars."""

from dataclasses import dataclass, field
from pathlib import Path

from troupe.edit.scalars import is_printable, render_key, render_scalar
from troupe.edit.text import Layout
from troupe.errors import LoadError
from troupe.schema import Data
from troupe.source import SourceFile
from troupe.tree import Entry, Item, MappingNode, Node, ScalarNode, SequenceNode, build_tree


@dataclass
class Rendered:
    """A value as written after its `key:` or `-`: text on that line, then whole lines below it."""

    inline: str
    lines: list[str] = field(default_factory=list)


def is_multiline(value: Data) -> bool:
    return isinstance(value, str) and "\n" in value


def flow_text(value: Data, preferred: str | None = None, *, flow: bool) -> str:
    """A value in flow style; scalars in the preferred quoting style when it can hold them."""
    if isinstance(value, dict):
        inner = ", ".join(
            f"{render_key(k, None, flow=True)}: {flow_text(v, flow=True)}" for k, v in value.items()
        )
        return "{" + inner + "}"
    if isinstance(value, list):
        return "[" + ", ".join(flow_text(v, flow=True) for v in value) + "]"
    return render_scalar(value, preferred, flow=flow)


def required_chomp(trailing_newlines: int, current: str | None) -> str:
    """The chomping indicator: the current one if it can represent the value's trailing newlines."""
    fits = {"-": trailing_newlines == 0, "": trailing_newlines == 1, "+": trailing_newlines >= 1}
    if current is not None and fits[current]:
        return current
    if trailing_newlines == 0:
        return "-"
    return "" if trailing_newlines == 1 else "+"


def literal_body(value: str, chomp: str, content_indent: int) -> list[str]:
    """The lines of a literal block holding `value` (whose trailing newlines `chomp` accounts for)."""
    core = value.rstrip("\n")
    trailing = len(value) - len(core)
    lines = core.split("\n") if core else []
    body = [(" " * content_indent + line) if line else "" for line in lines]
    if chomp == "+":
        body.extend([""] * (trailing - 1))
    return body


def needs_indent_digit(value: str) -> bool:
    first = next((line for line in value.split("\n") if line != ""), "")
    return first.startswith(" ")


def block_ok(value: str, header: str, body: list[str], owner_col: int) -> bool:
    """Whether a block scalar with this header and body reads back as `value`."""
    if any(ch == "\r" or not is_printable(ch) for ch in value):
        return False
    pad = " " * max(owner_col, 0)
    doc = f"{pad}k: {header}\n" + "".join(line + "\n" for line in body)
    try:
        root = build_tree(SourceFile(Path("<check>"), doc))
    except LoadError:
        return False
    if not isinstance(root, MappingNode) or len(root.entries) != 1:
        return False
    node = root.entries[0].value
    return getattr(node, "value", None) == value


def literal(value: str, owner_col: int, layout: Layout) -> Rendered | None:
    """A new literal block for a multi-line string, or None if a literal block cannot hold it."""
    content_indent = max(owner_col, 0) + layout.unit
    chomp = required_chomp(len(value) - len(value.rstrip("\n")), None)
    digit = str(content_indent - max(owner_col, 0)) if needs_indent_digit(value) else ""
    header = "|" + digit + chomp
    body = literal_body(value, chomp, content_indent)
    if not block_ok(value, header, body, owner_col):
        return None
    return Rendered(header, body)


def render_value(
    value: Data, *, owner_col: int, owner_is_key: bool, layout: Layout, preferred: str | None = None
) -> Rendered:
    """A value in a block context, owned by a key or `-` at column `owner_col`."""
    if isinstance(value, dict) and value:
        return Rendered("", mapping_lines(value, owner_col + layout.unit, layout))
    if isinstance(value, list) and value:
        offset = layout.seq_offset if owner_is_key else layout.unit
        return Rendered("", sequence_lines(value, owner_col + offset, layout))
    if isinstance(value, str) and is_multiline(value):
        block = literal(value, owner_col, layout)
        if block is not None:
            return block
    return Rendered(flow_text(value, preferred, flow=False))


def entry_lines(
    key: str,
    value: Data,
    col: int,
    layout: Layout,
    *,
    key_style: str | None = None,
    value_style: str | None = None,
) -> list[str]:
    r = render_value(value, owner_col=col, owner_is_key=True, layout=layout, preferred=value_style)
    head = " " * col + render_key(key, key_style, flow=False) + ":" + (" " + r.inline if r.inline else "")
    return [head, *r.lines]


def mapping_lines(value: dict[str, Data], col: int, layout: Layout) -> list[str]:
    lines: list[str] = []
    for key, child in value.items():
        lines.extend(entry_lines(key, child, col, layout))
    return lines


def sequence_lines(value: list[Data], col: int, layout: Layout) -> list[str]:
    lines: list[str] = []
    for child in value:
        lines.extend(item_lines(child, col, layout))
    return lines


def item_lines(value: Data, col: int, layout: Layout, *, value_style: str | None = None) -> list[str]:
    """A block sequence item at column `col`; mappings and lists use the compact `- key: v` form."""
    if isinstance(value, dict | list) and value:
        inner = (
            mapping_lines(value, col + 2, layout)
            if isinstance(value, dict)
            else sequence_lines(value, col + 2, layout)
        )
        return [" " * col + "- " + inner[0][col + 2 :], *inner[1:]]
    r = render_value(value, owner_col=col, owner_is_key=False, layout=layout, preferred=value_style)
    return [" " * col + "-" + (" " + r.inline if r.inline else ""), *r.lines]


# --- copies of anchored nodes (`set --expand-alias`) -------------------------------------------------------


def copy_value(node: Node, *, owner_col: int, owner_is_key: bool, layout: Layout) -> Rendered:
    """A block-style copy of `node` as written (built from its own file, without includes expanded).

    Keys and single-line scalars keep their written text, so quoting, number formats and include strings stay.
    Nested aliases stay `*name`. The node's anchors and comments are not copied. Collections are written in
    block style like new values; multi-line scalars are written as new multi-line values are.
    """
    if isinstance(node, MappingNode) and node.entries:
        assert node.written is None, "a copy never holds a merge key"
        col = owner_col + layout.unit
        lines: list[str] = []
        for entry in node.entries:
            lines.extend(_copy_entry(entry, col, layout))
        return Rendered("", lines)
    if isinstance(node, SequenceNode) and node.items:
        col = owner_col + (layout.seq_offset if owner_is_key else layout.unit)
        lines = []
        for item in node.items:
            lines.extend(_copy_item(item, col, layout))
        return Rendered("", lines)
    if isinstance(node, MappingNode | SequenceNode):
        return Rendered("{}" if isinstance(node, MappingNode) else "[]")
    assert isinstance(node, ScalarNode)
    text = node.file.text[node.start : node.end]
    if node.block is None and not node.tagged and "\n" not in text and "\r" not in text:
        return Rendered(text)
    return render_value(node.value, owner_col=owner_col, owner_is_key=owner_is_key, layout=layout)


def _copied(holder: Entry | Item, owner_col: int, owner_is_key: bool, layout: Layout) -> Rendered:
    if holder.alias is not None:
        return Rendered("*" + holder.alias.name)
    return copy_value(holder.value, owner_col=owner_col, owner_is_key=owner_is_key, layout=layout)


def _copy_entry(entry: Entry, col: int, layout: Layout) -> list[str]:
    key = entry.key_node
    written = key.file.text[key.start : key.end]
    key_text = written if "\n" not in written else render_key(entry.key, None, flow=False)
    r = _copied(entry, col, True, layout)
    return [" " * col + key_text + ":" + (" " + r.inline if r.inline else ""), *r.lines]


def _copy_item(item: Item, col: int, layout: Layout) -> list[str]:
    """An item at column `col`; a non-empty collection is compact (`- key: v`), as in `item_lines`."""
    value = item.value
    if (
        item.alias is None
        and isinstance(value, MappingNode | SequenceNode)
        and (value.entries if isinstance(value, MappingNode) else value.items)
    ):
        # Collections owned by a `-` go one unit in; place them at col + 2 so the first joins the dash.
        inner = copy_value(value, owner_col=col + 2 - layout.unit, owner_is_key=False, layout=layout).lines
        return [" " * col + "- " + inner[0][col + 2 :], *inner[1:]]
    r = _copied(item, col, False, layout)
    return [" " * col + "-" + (" " + r.inline if r.inline else ""), *r.lines]
