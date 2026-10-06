"""Carrying out a `set`: plan, apply each operation to in-memory texts, verify, then write.

Operations are applied one at a time, re-loading the configuration from the edited texts before each, so
every primitive works on an accurate tree. Nothing is written until the final texts load and match the
intended configuration; otherwise the set is refused and no file changes.
"""

import re
from dataclasses import dataclass
from pathlib import Path as FsPath

from troupe.edit import ops as prim
from troupe.edit.plan import (
    AddKey,
    AddOverride,
    Append,
    Delete,
    ExpandAlias,
    Op,
    Replace,
    WriteText,
    nest,
    plan,
)
from troupe.edit.text import apply_edits
from troupe.errors import LoadError, MergeKeyWrite, ThroughAlias, WriteRefused
from troupe.leaves import diff_leaves, leaves
from troupe.loader import Config, load
from troupe.overrides import is_bare, ref_entry
from troupe.paths import Path, format_path
from troupe.schema import Data, same
from troupe.store import Change
from troupe.tree import (
    Entry,
    Item,
    MappingNode,
    Node,
    ScalarNode,
    SequenceNode,
    TextNode,
    build_tree,
    to_data,
)


@dataclass
class SetResult:
    writes: dict[FsPath, str]  # file path → new text, only for files whose text changed
    changes: list[Change]


def compute_set(
    theatre: FsPath,
    config: Config,
    path: Path,
    value: Data,
    *,
    in_include: bool = False,
    expand_alias: bool = False,
) -> SetResult:
    original = {key: src.text for key, src in config.files.items()}
    texts = dict(original)
    current = config
    while True:
        try:
            operations = plan(current.root, path, value, in_include=in_include)
            break
        except ThroughAlias as e:
            # With --expand-alias, give the alias the set stopped at a copy, then plan again on the result.
            # Each round replaces one alias nearer the change, so this ends.
            if not expand_alias or e.in_flow:
                raise
            _apply(current, ExpandAlias(e.alias_at), texts)
            current = _reload(theatre, texts, path)
    expected = _expected(current.root, path, value)  # an expansion changes no value
    for op in operations:
        _apply(current, op, texts)
        current = _reload(theatre, texts, path)
    if texts == original:
        return SetResult({}, [])
    if not _matches(current.root, expected):
        raise WriteRefused(
            f"{format_path(path)}: the edited files would not read back as intended; not writing"
        )
    writes = {current.files[k].path: t for k, t in texts.items() if t != original.get(k)}
    return SetResult(writes, diff_leaves(leaves(to_data(config.root)), leaves(to_data(current.root))))


def _reload(theatre: FsPath, texts: dict[FsPath, str], path: Path) -> Config:
    try:
        return load(theatre, overlay=texts)
    except LoadError as e:
        raise WriteRefused(f"{format_path(path)}: the result would not load ({e}); not writing") from None


def _apply(config: Config, op: Op, texts: dict[FsPath, str]) -> None:
    where = format_path(op.path)
    if isinstance(op, WriteText):
        node = _node_at(config.root, op.path)
        assert isinstance(node, TextNode)
        texts[node.target.path.resolve()] = to_crlf(op.text) if "\r\n" in node.target.text else op.text
        return
    if isinstance(op, ExpandAlias):
        src, edits = _expand_alias(config.root, op.path, where)
        texts[src.path.resolve()] = apply_edits(texts[src.path.resolve()], edits)
        return
    for src, edits in _edits(config.root, op, where):
        file_key = src.path.resolve()
        texts[file_key] = apply_edits(texts[file_key], edits)


def _edits(root: Node, op: Op, where: str) -> list[prim.FileEdits]:
    if isinstance(op, AddOverride):
        return [_add_override(root, op)]
    parent = _node_at(root, op.path[:-1])
    key = op.path[-1]
    if isinstance(op, AddKey):
        assert isinstance(parent, MappingNode), where
        return [prim.add_key(physical_mapping(parent), key, op.value)]
    if isinstance(op, Append):
        assert isinstance(parent, SequenceNode)
        return [prim.append_item(parent, op.value)]
    if isinstance(op, Delete):
        if isinstance(parent, SequenceNode):
            return [prim.delete(parent, int(key), where)]
        assert isinstance(parent, MappingNode)
        return _delete_key(root, op.path[:-1], parent, key, where)
    assert isinstance(op, Replace)
    return [prim.replace(_slot(parent, key), op.value, where)]


def _delete_key(root: Node, path: Path, parent: MappingNode, key: str, where: str) -> list[prim.FileEdits]:
    """Delete `key` from every mapping `parent` was merged from, so that no layer brings it back.

    An override mapping that would be left empty is deleted from its own parent instead (an empty override
    changes nothing), up to the mapping that holds `$ref`, which stays.
    """
    out: list[prim.FileEdits] = []
    for depth, merged in enumerate(parent.layers or [parent]):
        layer = as_written(merged)
        entry = layer.get(key)
        if entry is None:
            continue
        if depth > 0 and len(layer.entries) == 1 and ref_entry(layer) is None:
            out.extend(_delete_layer(root, path, layer, where))
        else:
            out.append(prim.delete(layer, layer.entries.index(entry), where))
    return _by_file(out)


def _delete_layer(root: Node, path: Path, layer: MappingNode, where: str) -> list[prim.FileEdits]:
    """Delete the override mapping `layer` (the value at `path`) from the override that holds it."""
    holder = _node_at(root, path[:-1])
    assert isinstance(holder, MappingNode), where
    for depth, merged in enumerate(holder.layers or [holder]):
        outer = as_written(merged)
        entry = outer.get(path[-1])
        if entry is not None and entry.value is layer:
            if depth > 0 and len(outer.entries) == 1 and ref_entry(outer) is None:
                return _delete_layer(root, path[:-1], outer, where)
            return [prim.delete(outer, outer.entries.index(entry), where)]
    raise AssertionError(f"{where}: no override holds the mapping at {format_path(path)}")


def _by_file(file_edits: list[prim.FileEdits]) -> list[prim.FileEdits]:
    """The same edits, one group per file, so edits to one file are applied to the same text."""
    grouped: dict[FsPath, prim.FileEdits] = {}
    for src, edits in file_edits:
        key = src.path.resolve()
        if key in grouped:
            grouped[key][1].extend(edits)
        else:
            grouped[key] = (src, list(edits))
    return list(grouped.values())


def _add_override(root: Node, op: AddOverride) -> prim.FileEdits:
    """Write the new key as an override of the include at `op.include_path`, where its reference is.

    The key goes into the deepest mapping of its path that the overrides already have. A scalar-form
    include is first turned into mapping form.
    """
    node = _node_at(root, op.include_path)
    include = node.include
    assert include is not None, op.include_path
    rel = op.path[len(op.include_path) :]
    if include.overrides is None:
        key: Entry | None = None
        if op.include_path:
            parent = _node_at(root, op.include_path[:-1])
            if isinstance(parent, MappingNode):
                key = parent.get(op.include_path[-1])
        return prim.to_mapping_form(include.string, key, {rel[0]: nest(rel[1:], op.value)})
    mapping = as_written(include.overrides)
    while len(rel) > 1:
        entry = mapping.get(rel[0])
        if entry is None:
            break
        assert isinstance(entry.value, MappingNode) and entry.value.include is None, op.path
        mapping, rel = as_written(entry.value), rel[1:]
    return prim.add_key(mapping, rel[0], nest(rel[1:], op.value))


def _expand_alias(root: Node, path: Path, where: str) -> prim.FileEdits:
    """The edits that replace the alias at `path` with a copy of its anchored node as written."""
    parent = _node_at(root, path[:-1])
    holder: Entry | Item | None = None
    if isinstance(parent, MappingNode):
        for merged in reversed(parent.layers or [parent]):  # the alias as written, in whichever layer has it
            layer = as_written(merged)
            entry = layer.get(path[-1])
            if entry is not None and entry.alias is not None:
                parent, holder = layer, entry
                break
    else:
        assert isinstance(parent, SequenceNode), where
        holder = parent.items[int(path[-1])]
    assert holder is not None and holder.alias is not None, where
    anchor = holder.alias.target.anchor
    assert anchor is not None, where
    # The anchored node as written: its own file's tree, with no includes expanded.
    copy = _anchored_at(build_tree(parent.file), anchor.start)
    if _holds_merge_key(copy):
        raise MergeKeyWrite(where, format_path(path), f"the copy of *{holder.alias.name} would contain")
    return prim.expand_alias(parent, holder, copy, where)


def _anchored_at(node: Node | None, start: int) -> Node:
    """The node of a tree built from one file whose anchor starts at `start`."""
    stack = [node]
    while stack:
        here = stack.pop()
        if here is None:
            continue
        if here.anchor is not None and here.anchor.start == start:
            return here
        if isinstance(here, MappingNode):
            stack.extend(e.value for e in as_written(here).entries if e.alias is None)
        elif isinstance(here, SequenceNode):
            stack.extend(i.value for i in here.items if i.alias is None)
    raise AssertionError(f"no anchor at offset {start}")


def _holds_merge_key(node: Node) -> bool:
    """Whether a merge key is written in `node` (not counting what aliases in it refer to)."""
    if isinstance(node, MappingNode):
        return node.written is not None or any(
            e.alias is None and _holds_merge_key(e.value) for e in node.entries
        )
    if isinstance(node, SequenceNode):
        return any(i.alias is None and _holds_merge_key(i.value) for i in node.items)
    return False


def to_crlf(text: str) -> str:
    """Text-include content for a CRLF target: every LF not already preceded by CR becomes CRLF."""
    return re.sub(r"(?<!\r)\n", "\r\n", text)


def physical_mapping(node: MappingNode) -> MappingNode:
    """The mapping as written that a new key of `node` goes into.

    For a merged mapping that is the innermost included one (only `set --in-include` adds keys there).
    """
    mapping = as_written(node.layers[0] if node.layers else node)
    assert not mapping.layers
    return mapping


def as_written(mapping: MappingNode) -> MappingNode:
    """A mapping as written in its file: for one with a merge key, without the merged-in entries."""
    return mapping.written or mapping


def _slot(parent: Node, key: str) -> prim.Slot:
    """Where the value at `key` is written: for a merged mapping, in the last layer that sets it."""
    if isinstance(parent, MappingNode):
        layer = next(as_written(m) for m in reversed(parent.layers or [parent]) if m.get(key) is not None)
        entry = layer.get(key)
        assert entry is not None
        return prim.Slot(node=entry.value, parent=layer, entry=entry)
    assert isinstance(parent, SequenceNode)
    item: Item = parent.items[int(key)]
    return prim.Slot(node=item.value, parent=parent, item=item)


def _node_at(root: Node, path: Path) -> Node:
    node = root
    for segment in path:
        if isinstance(node, MappingNode):
            entry = node.get(segment)
            assert entry is not None, segment
            node = entry.value
        else:
            assert isinstance(node, SequenceNode), segment
            node = node.items[int(segment)].value
    return node


def _expected(root: Node, path: Path, value: Data) -> Data:
    """The configuration once `value` is at `path`: wherever the changed node appears, through an alias or
    a merge key as well (an alias's value is the anchored node object itself), it has the new value."""
    target, depth = root, 0
    for segment in path:
        if isinstance(target, MappingNode) and (entry := target.get(segment)) is not None:
            target = entry.value
        elif isinstance(target, SequenceNode) and segment.isdigit() and int(segment) < len(target.items):
            target = target.items[int(segment)].value
        else:
            break
        depth += 1
    changed = _with_value(to_data(target), path[depth:], value)

    def build(node: Node) -> Data:
        if node is target:
            return changed
        if isinstance(node, MappingNode):
            return {e.key: build(e.value) for e in node.entries}
        if isinstance(node, SequenceNode):
            return [build(i.value) for i in node.items]
        return to_data(node)

    return build(root)


def _with_value(data: Data, path: Path, value: Data) -> Data:
    if not path:
        return value
    head, rest = path[0], path[1:]
    if isinstance(data, dict):
        out = dict(data)
        out[head] = _with_value(data.get(head, {}), rest, value)
        return out
    assert isinstance(data, list)
    items = list(data)
    index = int(head)
    if index == len(items):
        items.append(_with_value(None, rest, value))
    else:
        items[index] = _with_value(items[index], rest, value)
    return items


def _matches(node: Node, expected: Data) -> bool:
    """Whether the re-loaded tree spells `expected`; an include string in `expected` matches its include."""
    if node.include is not None and is_bare(node.include, expected):
        return True
    if isinstance(node, MappingNode):
        return (
            isinstance(expected, dict)
            and len(node.entries) == len(expected)
            and all(e.key in expected for e in node.entries)
            and all(_matches(e.value, expected[e.key]) for e in node.entries)
        )
    if isinstance(node, SequenceNode):
        return (
            isinstance(expected, list)
            and len(node.items) == len(expected)
            and all(_matches(i.value, x) for i, x in zip(node.items, expected, strict=True))
        )
    if isinstance(node, TextNode) and isinstance(expected, str) and "\r\n" in node.value:
        return node.value == to_crlf(expected)
    assert isinstance(node, ScalarNode | TextNode)
    return same(node.value, expected)
