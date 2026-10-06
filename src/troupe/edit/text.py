"""Text edits on a source file, and the layout facts they depend on (comments, indentation, placement)."""

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise

from troupe.source import SourceFile
from troupe.tree import Entry, Item, MappingNode, Node, ScalarNode, SequenceNode, build_tree

DEFAULT_INDENT = 2


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    text: str


def apply_edits(text: str, edits: list[Edit]) -> str:
    ordered = sorted(edits, key=lambda e: (e.start, e.end))
    for a, b in pairwise(ordered):
        if a.end > b.start:
            raise ValueError(f"overlapping edits {a} and {b}")
    for edit in reversed(ordered):
        text = text[: edit.start] + edit.text + text[edit.end :]
    return text


@dataclass(frozen=True)
class Layout:
    unit: int  # indentation of a block mapping nested under a key
    seq_offset: int  # indentation of a block sequence under a key, relative to the key (0 = indentless)


def detect_layout(src: SourceFile) -> Layout:
    """The file's indentation: from its first nested block mapping and first block sequence under a key."""
    unit: int | None = None
    seq_offset: int | None = None
    root = build_tree(src)
    for key, child in _block_entries(root):
        key_col = src.column(key.start)
        on_next_line = src.line_start(child.start) > key.start
        if isinstance(child, MappingNode) and not child.flow_style and child.entries and on_next_line:
            unit = unit or src.column(child.start) - key_col
        if isinstance(child, SequenceNode) and not child.flow_style and child.items and on_next_line:
            seq_offset = src.column(child.start) - key_col if seq_offset is None else seq_offset
    unit = unit or DEFAULT_INDENT
    return Layout(unit=unit, seq_offset=unit if seq_offset is None else seq_offset)


def _block_entries(node: Node | None) -> Iterator[tuple[ScalarNode, Node]]:
    """(key, value) of every block mapping entry, in document order."""
    if isinstance(node, MappingNode):
        for entry in node.entries:
            if not node.flow_style:
                yield entry.key_node, entry.value
            yield from _block_entries(entry.value)
    elif isinstance(node, SequenceNode):
        for item in node.items:
            yield from _block_entries(item.value)


def comment_start(src: SourceFile, pos: int) -> int | None:
    """Offset of the end-of-line comment on `pos`'s line, scanning from `pos` (a token boundary)."""
    text = src.text
    line_start = src.line_start(pos)
    end = src.line_end(pos)
    i = pos
    while i < end:
        ch = text[i]
        if ch == "#" and (i == line_start or text[i - 1] in " \t"):
            return i
        if ch in "'\"":
            i = _skip_quoted(text, i, end)
            if i < 0:
                return None
            continue
        i += 1
    return None


def _skip_quoted(text: str, i: int, end: int) -> int:
    quote = text[i]
    i += 1
    while i < end:
        if quote == '"' and text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            if quote == "'" and i + 1 < end and text[i + 1] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return -1


def inline_edit(src: SourceFile, start: int, end: int, new: str) -> Edit:
    """Replace [start, end) with `new`, keeping an end-of-line comment after `end` at its column.

    If the new text reaches the comment's column, exactly one space separates them.
    """
    hash_pos = comment_start(src, end)
    if hash_pos is None:
        return Edit(start, end, new)
    comment_col = src.column(hash_pos)
    segment = new + src.text[end:hash_pos].rstrip(" \t")
    if "\n" in segment:
        end_col = len(segment.rsplit("\n", 1)[1].rstrip("\r"))
    else:
        end_col = src.column(start) + len(segment)
    return Edit(start, hash_pos, segment + " " * max(1, comment_col - end_col))


def owned_end(node: Node) -> int:
    """The last offset belonging to the node's value (a kept block scalar owns its trailing blank lines).

    An included value ends where its reference does, in the file that holds the reference.
    """
    if node.include is not None:
        return owned_end(node.include.overrides or node.include.string)
    if isinstance(node, MappingNode) and node.written is not None:
        return owned_end(node.written)  # merged-in entries are written elsewhere
    if isinstance(node, ScalarNode) and node.block is not None and node.block.chomp == "+":
        return max(node.end, node.block.region_end - 1)
    if isinstance(node, MappingNode) and not node.flow_style and node.entries:
        return max(held_end(node.entries[-1]), node.entries[-1].key_node.end)
    if isinstance(node, SequenceNode) and not node.flow_style and node.items:
        return max(held_end(node.items[-1]), node.end)
    return node.end


def held_span(holder: Entry | Item) -> tuple[int, int]:
    """Where an entry's or item's value is written; for an alias, its `*name` (the value is elsewhere)."""
    if holder.alias is not None:
        return holder.alias.start, holder.alias.end
    return holder.value.start, holder.value.end


def held_end(holder: Entry | Item) -> int:
    """The last offset belonging to an entry's or item's value as written there."""
    return holder.alias.end if holder.alias is not None else owned_end(holder.value)


def insertion_point(src: SourceFile, last_end: int, col: int) -> int:
    """Where a new block entry goes: below the last entry and any comments indented at least `col`."""
    text = src.text
    pos = src.next_line(last_end)
    anchor = pos
    while pos < len(text):
        line = text[pos : src.line_end(pos)]
        stripped = line.lstrip(" ")
        if stripped.strip() == "":
            pos = src.next_line(pos)
            continue
        if stripped.startswith("#") and len(line) - len(stripped) >= col:
            pos = src.next_line(pos)
            anchor = pos
            continue
        break
    return anchor


def insert_lines(src: SourceFile, pos: int, lines: list[str]) -> Edit:
    """Insert whole lines at a line start `pos`, adding a line break first if the file lacks a final one."""
    nl = src.newline
    prefix = nl if pos == len(src.text) and src.text and not src.text.endswith("\n") else ""
    return Edit(pos, pos, prefix + "".join(line + nl for line in lines))


def indicator_end(src: SourceFile, key_end: int) -> int:
    """Offset just past the `:` that follows a block mapping key ending at `key_end`."""
    i = key_end
    while src.text[i] in " \t":
        i += 1
    assert src.text[i] == ":", f"expected ':' at {i} in {src.path}"
    return i + 1
