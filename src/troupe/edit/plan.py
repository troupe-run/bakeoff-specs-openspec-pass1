"""Turning `set PATH VALUE` into a list of primitive operations, by path, against the loaded tree.

When the existing value and VALUE are both mappings (or both lists) only their differences become
operations, so unchanged entries keep their bytes. YAML include roots are never rewritten: changing or
deleting one is refused.
"""

from dataclasses import dataclass

from troupe.errors import PathError, WriteRefused
from troupe.paths import Path, format_path, is_index
from troupe.schema import Data, same
from troupe.tree import MappingNode, Node, ScalarNode, SequenceNode, TextNode, to_data


@dataclass(frozen=True)
class Replace:
    path: Path
    value: Data


@dataclass(frozen=True)
class AddKey:
    path: Path  # path of the new key; its parent mapping exists
    value: Data


@dataclass(frozen=True)
class Append:
    path: Path  # path of the new item (index == length)
    value: Data


@dataclass(frozen=True)
class Delete:
    path: Path


@dataclass(frozen=True)
class WriteText:
    path: Path
    text: str


type Op = Replace | AddKey | Append | Delete | WriteText


def describe(node: Node) -> str:
    return (
        "a mapping"
        if isinstance(node, MappingNode)
        else "a list"
        if isinstance(node, SequenceNode)
        else "a scalar"
    )


def plan(root: Node, path: Path, value: Data) -> list[Op]:
    """Operations that make the value at `path` equal `value`. Raises PathError / WriteRefused."""
    node: Node = root
    for i, segment in enumerate(path):
        here = path[: i + 1]
        rest = path[i + 1 :]
        if isinstance(node, MappingNode):
            entry = node.get(segment)
            if entry is None:
                if any(is_index(s) for s in path[i:]):
                    raise PathError(f"{format_path(path)}: not found ({format_path(here)} does not exist)")
                return [AddKey(here, _nest(rest, value))]
            node = entry.value
        elif isinstance(node, SequenceNode):
            if not is_index(segment):
                raise PathError(f"{format_path(path)}: {format_path(path[:i]) or 'the root'} is a list")
            index = int(segment)
            if index < len(node.items):
                node = node.items[index].value
            elif index == len(node.items) and not rest:
                return [Append(here, value)]
            else:
                raise PathError(
                    f"{format_path(path)}: index {index} is out of range (length {len(node.items)})"
                )
        else:
            raise PathError(
                f"{format_path(path)}: {format_path(path[:i])} is a scalar, not a mapping or list"
            )
    ops: list[Op] = []
    _diff(node, value, path, ops)
    return ops


def _nest(rest: Path, value: Data) -> Data:
    for segment in reversed(rest):
        value = {segment: value}
    return value


def _check_no_includes(node: Node, path: Path) -> None:
    if node.include is not None:
        raise WriteRefused(
            f"{format_path(path)}: its value comes from {node.include.target}; not replacing it"
        )
    if isinstance(node, MappingNode):
        for entry in node.entries:
            _check_no_includes(entry.value, (*path, entry.key))
    elif isinstance(node, SequenceNode):
        for index, item in enumerate(node.items):
            _check_no_includes(item.value, (*path, str(index)))


def _diff(node: Node, value: Data, path: Path, ops: list[Op]) -> None:
    where = format_path(path)
    include = node.include
    if include is not None and isinstance(value, str) and value == include.string.value:
        return
    if isinstance(node, TextNode):
        if not isinstance(value, str):
            raise WriteRefused(f"{where}: is the text of {node.target.path}; VALUE must be a string")
        if value != node.value:
            ops.append(WriteText(path, value))
        return
    if include is not None:
        if same(to_data(node), value):
            return
        raise WriteRefused(f"{where}: its whole value comes from {include.target}; not replacing it")
    if isinstance(node, MappingNode) and isinstance(value, dict) and (value or not node.entries):
        adds: list[Op] = []
        deletes: list[Op] = []
        for entry in node.entries:
            if entry.key not in value:
                _check_no_includes(entry.value, (*path, entry.key))
                deletes.append(Delete((*path, entry.key)))
        for key, child in value.items():
            existing = node.get(key)
            if existing is None:
                adds.append(AddKey((*path, key), child))
            else:
                _diff(existing.value, child, (*path, key), ops)
        ops.extend(adds + deletes)
        return
    if isinstance(node, SequenceNode) and isinstance(value, list) and (value or not node.items):
        for index, (item, child) in enumerate(zip(node.items, value, strict=False)):
            _diff(item.value, child, (*path, str(index)), ops)
        for index in range(len(node.items), len(value)):
            ops.append(Append((*path, str(index)), value[index]))
        for index in reversed(range(len(value), len(node.items))):
            _check_no_includes(node.items[index].value, (*path, str(index)))
            ops.append(Delete((*path, str(index))))
        return
    if isinstance(node, ScalarNode) and same(node.value, value):
        return
    _check_no_includes(node, path)
    if same(to_data(node), value):
        return
    ops.append(Replace(path, value))
