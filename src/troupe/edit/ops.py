"""Primitive write-back operations on one node of a freshly loaded tree.

Each returns the text edits for one source file. They never touch bytes outside what the change needs.
"""

from dataclasses import dataclass

from troupe.blockscalar import BlockLayout
from troupe.edit.blocks import (
    Rendered,
    block_ok,
    copy_value,
    entry_lines,
    flow_text,
    item_lines,
    literal_body,
    needs_indent_digit,
    render_value,
    required_chomp,
)
from troupe.edit.folded import MoreIndented, refold
from troupe.edit.scalars import QUOTE_STYLES, double, render_key
from troupe.edit.text import (
    Edit,
    Layout,
    comment_start,
    detect_layout,
    held_end,
    held_span,
    indicator_end,
    inline_edit,
    insert_lines,
    insertion_point,
    owned_end,
)
from troupe.errors import WriteRefused
from troupe.overrides import REF_KEY
from troupe.schema import Data
from troupe.source import SourceFile
from troupe.tree import Entry, Item, MappingNode, Node, ScalarNode, SequenceNode


@dataclass
class Slot:
    """Where a node sits: the collection holding it and its entry or item there."""

    node: Node
    parent: MappingNode | SequenceNode
    entry: Entry | None = None
    item: Item | None = None

    @property
    def indicator_end(self) -> int:
        """Where text written right after the `key:` or `-` goes: past the node's anchor if it is there."""
        if self.entry is not None:
            end = indicator_end(self.node.file, self.entry.key_node.end)
        else:
            assert self.item is not None and self.item.dash is not None
            end = self.item.dash + 1
        anchor = self.node.anchor
        src = self.node.file
        if anchor is not None and anchor.start >= end and src.line_start(anchor.start) == src.line_start(end):
            return anchor.end
        return end


type FileEdits = tuple[SourceFile, list[Edit]]


def _scalar_style(node: Node | None) -> str | None:
    if isinstance(node, ScalarNode) and node.style in QUOTE_STYLES:
        return node.style
    return None


def replace(slot: Slot, value: Data, where: str) -> FileEdits:
    node = slot.node
    src = node.file
    if isinstance(node, ScalarNode) and (node.opaque or node.tagged):
        raise WriteRefused(f"{where}: cannot rewrite this value safely (unsupported tag or block layout)")
    if node.in_flow:
        text = flow_text(value, _scalar_style(node), flow=True)
        return src, [inline_edit(src, node.start, node.end, text)]
    layout = detect_layout(src)
    if isinstance(node, ScalarNode) and node.block is not None:
        return src, _replace_block_scalar(slot, node, node.block, value, layout, where)
    if isinstance(node, MappingNode | SequenceNode) and not node.flow_style:
        return src, _replace_block_collection(slot, node, value, layout)
    if isinstance(node, ScalarNode) and node.start == node.end:
        return src, _replace_empty(slot, value, layout)
    return src, _replace_inline(slot, value, layout)


def _replace_empty(slot: Slot, value: Data, layout: Layout) -> list[Edit]:
    """Fill an empty (implicit null) value such as `key:`: the text goes right after the indicator."""
    src = slot.node.file
    pos = slot.indicator_end
    r = _render_for(slot, value, layout, None)
    edits = [inline_edit(src, pos, pos, " " + r.inline)] if r.inline else []
    if r.lines:
        edits.append(insert_lines(src, src.next_line(pos), r.lines))
    return edits


def _render_for(slot: Slot, value: Data, layout: Layout, preferred: str | None) -> Rendered:
    owner_col = slot.node.owner_col
    return render_value(
        value, owner_col=owner_col, owner_is_key=slot.entry is not None, layout=layout, preferred=preferred
    )


def _replace_inline(slot: Slot, value: Data, layout: Layout) -> list[Edit]:
    """Replace a plain/quoted scalar or flow collection sitting on its owner's line(s)."""
    node = slot.node
    src = node.file
    r = _render_for(slot, value, layout, _scalar_style(node))
    if r.inline:
        edits = [inline_edit(src, node.start, node.end, r.inline)]
    else:
        start = (
            node.start if src.text[node.end : src.line_end(node.end)].strip() else _ws_start(src, node.start)
        )
        # With an end-of-line comment the comment keeps its column; without, drop the space before the value.
        edits = [inline_edit(src, start, node.end, "")]
    if r.lines:
        edits.append(insert_lines(src, src.next_line(node.end), r.lines))
    return edits


def _ws_start(src: SourceFile, pos: int) -> int:
    while pos > 0 and src.text[pos - 1] in " \t":
        pos -= 1
    return pos


def _replace_block_collection(
    slot: Slot, node: MappingNode | SequenceNode, value: Data, layout: Layout
) -> list[Edit]:
    src = node.file
    ind_end = slot.indicator_end
    compact = src.line_start(node.start) == src.line_start(ind_end)
    end = owned_end(node)
    if compact:
        # `- key: v` / `- - v`: the collection starts on the dash's line; rewrite it in the same form.
        assert slot.item is not None
        col = src.column(ind_end - 1)
        lines = item_lines(value, col, layout)
        first = lines[0][col + 1 :].lstrip(" ")
        new = first + "".join(src.newline + line for line in lines[1:])
        return [inline_edit(src, node.start, end, new)]
    region = Edit(src.next_line(ind_end), src.next_line(end), "")
    r = _render_for(slot, value, layout, None)
    edits: list[Edit] = []
    if r.inline:
        edits.append(inline_edit(src, ind_end, ind_end, " " + r.inline))
    nl = src.newline
    edits.append(Edit(region.start, region.end, "".join(line + nl for line in r.lines)))
    return edits


def _replace_block_scalar(
    slot: Slot, node: ScalarNode, block: BlockLayout, value: Data, layout: Layout, where: str
) -> list[Edit]:
    src = node.file
    nl = src.newline
    content = Edit(block.body_start, max(block.region_end, block.body_start), "")
    if isinstance(value, str):
        core = value.rstrip("\n")
        chomp = required_chomp(len(value) - len(core), block.chomp)
        header = _header(src.text[block.start : block.header_end], chomp)
        if block.indicator == ">":
            try:
                body = refold(block, core)
            except MoreIndented:
                raise WriteRefused(
                    f"{where}: the new value would need a more-indented line in a folded scalar"
                ) from None
            ci = block.content_indent
            body = [(" " * ci + line) if line else "" for line in body]
            if chomp == "+":
                body.extend([""] * (len(value) - len(core) - 1))
        else:
            if needs_indent_digit(value) and block.indent_digit is None:
                header = header[0] + str(block.content_indent - max(node.owner_col, 0)) + header[1:]
            body = literal_body(value, chomp, block.content_indent)
        if block_ok(value, header, body, node.owner_col) or block.indicator == ">":
            if block.region_end == len(src.text) and body and not src.text.endswith("\n"):
                return [
                    inline_edit(src, block.start, block.header_end, header),
                    Edit(content.start, content.end, nl.join(body)),
                ]
            return [
                inline_edit(src, block.start, block.header_end, header),
                Edit(content.start, content.end, "".join(line + nl for line in body)),
            ]
        return [inline_edit(src, block.start, block.header_end, double(value)), content]
    r = _render_for(slot, value, layout, None)
    if r.inline:
        return [
            inline_edit(src, block.start, block.header_end, r.inline),
            Edit(content.start, content.end, "".join(line + nl for line in r.lines)),
        ]
    has_comment = src.text[block.header_end : src.line_end(block.start)].strip() != ""
    start = block.start if has_comment else _ws_start(src, block.start)
    return [
        inline_edit(src, start, block.header_end, ""),
        Edit(content.start, content.end, "".join(line + nl for line in r.lines)),
    ]


def _header(old: str, chomp: str) -> str:
    """The block header `old` (e.g. `|2-`) with its chomping indicator set to `chomp`."""
    for i, ch in enumerate(old):
        if ch in "+-":
            return old[:i] + chomp + old[i + 1 :]
    return old + chomp


def add_key(mapping: MappingNode, key: str, value: Data) -> FileEdits:
    src = mapping.file
    last = mapping.entries[-1] if mapping.entries else None
    key_style = _scalar_style(last.key_node) if last else None
    value_style = _scalar_style(last.value) if last and last.alias is None else None
    if mapping.flow_style:
        entry = f"{render_key(key, key_style, flow=True)}: {flow_text(value, value_style, flow=True)}"
        return src, [_flow_append(mapping, held_span(last)[1] if last else None, entry)]
    layout = detect_layout(src)
    if last is None:
        col, pos = 0, len(src.text)
    else:
        col = src.column(last.key_node.start)
        pos = insertion_point(src, owned_end(mapping), col)
    lines = entry_lines(key, value, col, layout, key_style=key_style, value_style=value_style)
    return src, [insert_lines(src, pos, lines)]


def to_mapping_form(string: ScalarNode, key: Entry | None, entries: dict[str, Data]) -> FileEdits:
    """Turn the include `string` into a mapping-form include holding `$ref` and the override `entries`.

    `key` is the block mapping entry whose value is `string` (None for a list item or the document root).
    On the key's line, the string and the space before it go, and the mapping follows one indentation unit
    deeper. Otherwise `$ref: ` goes in front of the string and the entries follow at its column. The
    string's bytes are kept.
    """
    src = string.file
    if string.block is not None:
        raise WriteRefused(f"{src.path}: cannot convert a block-scalar include to mapping form")
    written = src.text[string.start : string.end]
    style = _scalar_style(string)
    if string.in_flow:
        items = ", ".join(
            f"{render_key(k, None, flow=True)}: {flow_text(v, style, flow=True)}" for k, v in entries.items()
        )
        return src, [inline_edit(src, string.start, string.end, f"{{{REF_KEY}: {written}, {items}}}")]
    layout = detect_layout(src)
    lines: list[str] = []
    if key is not None and src.line_start(key.key_node.start) == src.line_start(string.start):
        col = src.column(key.key_node.start) + layout.unit
        lines.append(" " * col + f"{REF_KEY}: {written}")
        edits = [Edit(_ws_start(src, string.start), string.end, "")]
    else:
        col = src.column(string.start)
        edits = [inline_edit(src, string.start, string.start, f"{REF_KEY}: ")]
    for k, v in entries.items():
        lines.extend(entry_lines(k, v, col, layout, value_style=style))
    edits.append(insert_lines(src, src.next_line(string.end), lines))
    return src, edits


def append_item(seq: SequenceNode, value: Data) -> FileEdits:
    src = seq.file
    last = seq.items[-1] if seq.items else None
    style = _scalar_style(last.value) if last and last.alias is None else None
    if seq.flow_style:
        last_end = held_span(last)[1] if last else None
        return src, [_flow_append(seq, last_end, flow_text(value, style, flow=True))]
    assert last is not None and last.dash is not None
    layout = detect_layout(src)
    col = src.column(last.dash)
    pos = insertion_point(src, owned_end(seq), col)
    return src, [insert_lines(src, pos, item_lines(value, col, layout, value_style=style))]


def _flow_append(node: MappingNode | SequenceNode, last_end: int | None, entry: str) -> Edit:
    src = node.file
    if last_end is None:
        open_end = node.start + 1
        return inline_edit(src, open_end, open_end, entry)
    return inline_edit(src, last_end, last_end, ", " + entry)


def delete(parent: MappingNode | SequenceNode, index: int, where: str) -> FileEdits:
    """Delete the entry or item at `index` of a collection that keeps at least one other entry."""
    src = parent.file
    if parent.flow_style:
        spans = (
            [(e.key_node.start, max(held_span(e)[1], e.key_node.end)) for e in parent.entries]
            if isinstance(parent, MappingNode)
            else [held_span(i) for i in parent.items]
        )
        start, end = spans[index]
        if index > 0:
            return src, [inline_edit(src, spans[index - 1][1], end, "")]
        if len(spans) > 1:
            return src, [Edit(start, spans[1][0], "")]
        return src, [inline_edit(src, start, end, "")]
    starts = (
        [e.key_node.start for e in parent.entries]
        if isinstance(parent, MappingNode)
        else [i.dash if i.dash is not None else held_span(i)[0] for i in parent.items]
    )
    holder: Entry | Item = parent.entries[index] if isinstance(parent, MappingNode) else parent.items[index]
    end = held_end(holder)
    first = starts[index]
    line_start = src.line_start(first)
    if src.text[line_start:first].strip(" ") == "":
        return src, [Edit(line_start, src.next_line(end), "")]
    if index == 0 and len(starts) > 1:
        # The first entry of a compact `- key: v` shares the dash's line: pull the next entry up into
        # its place, which sits at the same column.
        return src, [Edit(first, starts[1], "")]
    raise WriteRefused(f"{where}: cannot delete an entry that shares its line with another")


EXPANDED_COMMENT = "# expanded from *{name} by troupe"


def expand_alias(
    parent: MappingNode | SequenceNode, holder: Entry | Item, copy: Node, where: str
) -> FileEdits:
    """Replace the alias that is `holder`'s value with `copy`, its anchored node as written, in block style.

    The `*name` goes, and the end-of-line comment `EXPANDED_COMMENT` is put on the key's (or dash's) line, two
    spaces after whatever ends it. A scalar copy takes the alias's place; a collection copy follows that line.
    """
    alias = holder.alias
    assert alias is not None and not alias.in_flow, where
    src = parent.file
    if isinstance(holder, Entry):
        owner = holder.key_node.start
    else:
        assert holder.dash is not None, where
        owner = holder.dash
    r = copy_value(
        copy, owner_col=src.column(owner), owner_is_key=isinstance(holder, Entry), layout=detect_layout(src)
    )
    marker = "  " + EXPANDED_COMMENT.format(name=alias.name)
    owner_end = src.line_end(owner)
    edits: list[Edit] = []
    if src.line_start(alias.start) == src.line_start(owner):
        commented = comment_start(src, alias.end) is not None
        if r.inline and commented:
            edits += [inline_edit(src, alias.start, alias.end, r.inline), Edit(owner_end, owner_end, marker)]
        elif r.inline:
            edits.append(Edit(alias.start, owner_end, r.inline + marker))
        elif commented:  # the comment keeps its bytes, and so does the whitespace before it
            edits += [Edit(_ws_start(src, alias.start), alias.end, ""), Edit(owner_end, owner_end, marker)]
        else:
            edits.append(Edit(_ws_start(src, alias.start), owner_end, marker))
    else:
        if src.line_text(alias.start).strip(" \t") != src.text[alias.start : alias.end]:
            raise WriteRefused(
                f"{where}: cannot expand *{alias.name}: it shares its line with something else"
            )
        edits.append(Edit(owner_end, owner_end, marker))
        if r.inline:
            edits.append(Edit(alias.start, alias.end, r.inline))
        else:
            edits.append(Edit(src.line_start(alias.start), src.next_line(alias.start), ""))
    if r.lines:
        edits.append(insert_lines(src, src.next_line(alias.end), r.lines))
    return src, edits
