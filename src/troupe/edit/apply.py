"""Carrying out a `set`: plan, apply each operation to in-memory texts, verify, then write.

Operations are applied one at a time, re-loading the configuration from the edited texts before each, so
every primitive works on an accurate tree. Nothing is written until the final texts load and match the
intended configuration; otherwise the set is refused and no file changes.
"""

import re
from dataclasses import dataclass
from pathlib import Path as FsPath

from troupe.edit import ops as prim
from troupe.edit.plan import AddKey, Append, Delete, Op, Replace, WriteText, plan
from troupe.edit.text import apply_edits
from troupe.errors import LoadError, WriteRefused
from troupe.leaves import diff_leaves, leaves
from troupe.loader import Config, load
from troupe.paths import Path, format_path
from troupe.schema import Data, same
from troupe.store import Change
from troupe.tree import Item, MappingNode, Node, ScalarNode, SequenceNode, TextNode, to_data


@dataclass
class SetResult:
    writes: dict[FsPath, str]  # file path → new text, only for files whose text changed
    changes: list[Change]


def compute_set(theatre: FsPath, config: Config, path: Path, value: Data) -> SetResult:
    operations = plan(config.root, path, value)
    original = {key: src.text for key, src in config.files.items()}
    texts = dict(original)
    current = config
    for op in operations:
        _apply(current, op, texts)
        current = _reload(theatre, texts, path)
    if texts == original:
        return SetResult({}, [])
    expected = _with_value(to_data(config.root), path, value)
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
    parent = _node_at(config.root, op.path[:-1])
    key = op.path[-1]
    if isinstance(op, AddKey):
        assert isinstance(parent, MappingNode)
        src, edits = prim.add_key(parent, key, op.value)
    elif isinstance(op, Append):
        assert isinstance(parent, SequenceNode)
        src, edits = prim.append_item(parent, op.value)
    elif isinstance(op, Delete):
        assert isinstance(parent, MappingNode | SequenceNode)
        index = [e.key for e in parent.entries].index(key) if isinstance(parent, MappingNode) else int(key)
        src, edits = prim.delete(parent, index, where)
    else:
        assert isinstance(op, Replace)
        src, edits = prim.replace(_slot(parent, key), op.value, where)
    file_key = src.path.resolve()
    texts[file_key] = apply_edits(texts[file_key], edits)


def to_crlf(text: str) -> str:
    """Text-include content for a CRLF target: every LF not already preceded by CR becomes CRLF."""
    return re.sub(r"(?<!\r)\n", "\r\n", text)


def _slot(parent: Node, key: str) -> prim.Slot:
    if isinstance(parent, MappingNode):
        entry = parent.get(key)
        assert entry is not None
        return prim.Slot(node=entry.value, parent=parent, entry=entry)
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
    if node.include is not None and isinstance(expected, str) and expected == node.include.string.value:
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
