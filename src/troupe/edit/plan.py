"""Turning `set PATH VALUE` into a list of primitive operations, by path, against the loaded tree.

When the existing value and VALUE are both mappings (or both lists) only their differences become
operations, so unchanged entries keep their bytes. YAML include roots are never rewritten: changing or
deleting one is refused. Nothing is written through an alias (`*name`), since that would change the anchor
and every other use of it: such a set raises `ThroughAlias`, naming the alias. Merge keys (`<<`) are never
written: a set that would change one, or a value one supplies, raises `MergeKeyWrite`.
"""

from dataclasses import dataclass

from troupe.errors import MergeKeyWrite, PathError, ThroughAlias, WriteRefused
from troupe.overrides import is_bare
from troupe.paths import Path, format_path, is_index
from troupe.schema import Data, same
from troupe.tree import Alias, MappingNode, Node, ScalarNode, SequenceNode, TextNode, merged_in, to_data


@dataclass(frozen=True)
class Replace:
    path: Path
    value: Data


@dataclass(frozen=True)
class AddKey:
    path: Path  # path of the new key; its parent mapping exists
    value: Data


@dataclass(frozen=True)
class AddOverride:
    path: Path  # path of the new key, below the include at `include_path`
    include_path: Path  # the include whose overrides get the key, in the file holding its reference
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


@dataclass(frozen=True)
class ExpandAlias:
    path: Path  # the entry or item whose value is written as an alias; it gets a copy of the anchored node


type Op = Replace | AddKey | AddOverride | Append | Delete | WriteText | ExpandAlias


def describe(node: Node) -> str:
    return (
        "a mapping"
        if isinstance(node, MappingNode)
        else "a list"
        if isinstance(node, SequenceNode)
        else "a scalar"
    )


def plan(root: Node, path: Path, value: Data, *, in_include: bool = False) -> list[Op]:
    """Operations that make the value at `path` equal `value`. Raises PathError / WriteRefused."""
    existing = _existing(root, path)
    if existing is not None and same(to_data(existing), value):
        return []  # nothing changes, even through an alias
    node: Node = root
    for i, segment in enumerate(path):
        here = path[: i + 1]
        rest = path[i + 1 :]
        if isinstance(node, MappingNode):
            entry = node.get(segment)
            if entry is None:
                if any(is_index(s) for s in path[i:]):
                    raise PathError(f"{format_path(path)}: not found ({format_path(here)} does not exist)")
                return [new_key_target(root, here, nest(rest, value), in_include=in_include)]
            if merged_in(node, segment) is not None:
                raise merge_supplied(path, here)
            if entry.alias is not None:
                raise through_alias(root, path, here, entry.alias)
            node = entry.value
        elif isinstance(node, SequenceNode):
            if not is_index(segment):
                raise PathError(f"{format_path(path)}: {format_path(path[:i]) or 'the root'} is a list")
            index = int(segment)
            if index < len(node.items):
                item = node.items[index]
                if item.alias is not None:
                    raise through_alias(root, path, here, item.alias)
                node = item.value
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
    _diff(root, node, value, path, ops, in_include, path)
    return ops


def _existing(root: Node, path: Path) -> Node | None:
    """The node at `path`, or None if there is none."""
    node = root
    for segment in path:
        if isinstance(node, MappingNode) and (entry := node.get(segment)) is not None:
            node = entry.value
        elif isinstance(node, SequenceNode) and is_index(segment) and int(segment) < len(node.items):
            node = node.items[int(segment)].value
        else:
            return None
    return node


def merge_supplied(path: Path, value_path: Path) -> MergeKeyWrite:
    """The refusal for a `set` of `path` that would change the merge-supplied value at `value_path`."""
    return MergeKeyWrite(
        format_path(path), format_path(value_path[:-1]), f"{format_path(value_path)} is supplied by"
    )


def _check_no_merge_keys(node: Node, path: Path, top: Path) -> None:
    """Refuse to replace or delete `node` (at `path`) if a merge key is written in it."""
    if isinstance(node, MappingNode):
        if node.written is not None:
            raise MergeKeyWrite(format_path(top), format_path(path), "this would rewrite")
        for entry in node.entries:
            if entry.alias is None:
                _check_no_merge_keys(entry.value, (*path, entry.key), top)
    elif isinstance(node, SequenceNode):
        for index, item in enumerate(node.items):
            if item.alias is None:
                _check_no_merge_keys(item.value, (*path, str(index)), top)


def through_alias(root: Node, path: Path, alias_path: Path, alias: Alias) -> ThroughAlias:
    """The refusal for a `set` of `path` that would write through `alias`, written at `alias_path`."""
    anchor = anchor_path(root, alias.target)
    rest = path[len(alias_path) :]
    return ThroughAlias(
        format_path(path),
        alias_path,
        alias.name,
        format_path(anchor) if anchor is not None else None,
        format_path((*anchor, *rest)) if anchor is not None else None,
        in_flow=alias.in_flow,
    )


def anchor_path(root: Node, target: Node) -> Path | None:
    """The path at which `target` is written (not reached through an alias or a merge key), if any."""
    stack: list[tuple[Node, Path]] = [(root, ())]
    while stack:
        node, path = stack.pop()
        if node is target:
            return path
        children: list[tuple[Node, Path]] = []
        if isinstance(node, MappingNode):
            children = [
                (e.value, (*path, e.key))
                for e in node.entries
                if e.alias is None and (node.written is None or node.written.get(e.key) is e)
            ]
        elif isinstance(node, SequenceNode):
            children = [(i.value, (*path, str(n))) for n, i in enumerate(node.items) if i.alias is None]
        stack.extend(reversed(children))
    return None


def new_key_target(root: Node, path: Path, value: Data, *, in_include: bool = False) -> Op:
    """Where the new key at `path` (whose parent mapping exists) is written.

    A key whose parent lies inside an included value, with no list item between the include and the
    parent, is written as an override of the nearest such include, in the file that holds the include's
    reference. Includes whose reference is itself in remote content are passed over, since that cannot be
    written. Anything else, and every key when `in_include` is set (`set --in-include`), goes into the
    parent mapping's own file: for a merged mapping, the innermost included one.
    """
    if in_include:
        return AddKey(path, value)
    anchor: int | None = 0 if root.include is not None else None  # length of the anchoring include's path
    node = root
    for depth, segment in enumerate(path[:-1], start=1):
        if isinstance(node, MappingNode):
            entry = node.get(segment)
            assert entry is not None, segment
            node = entry.value
        else:
            assert isinstance(node, SequenceNode), segment
            node = node.items[int(segment)].value
            anchor = None  # overrides cannot address list items
        if node.include is not None and node.include.string.file.url is None:
            anchor = depth  # an include whose reference can take an override: it is in a local file
    if anchor is None:
        return AddKey(path, value)
    return AddOverride(path, path[:anchor], value)


def nest(rest: Path, value: Data) -> Data:
    for segment in reversed(rest):
        value = {segment: value}
    return value


def _check_no_includes(node: Node, path: Path) -> None:
    if node.include is not None:
        raise WriteRefused(
            f"{format_path(path)}: its value comes from {node.include.target}; not replacing it"
        )
    # Below an alias nothing is rewritten: only the `*name` text goes.
    if isinstance(node, MappingNode):
        for entry in node.entries:
            if entry.alias is None:
                _check_no_includes(entry.value, (*path, entry.key))
    elif isinstance(node, SequenceNode):
        for index, item in enumerate(node.items):
            if item.alias is None:
                _check_no_includes(item.value, (*path, str(index)))


def _diff(
    root: Node, node: Node, value: Data, path: Path, ops: list[Op], in_include: bool, top: Path
) -> None:
    """Add the operations that turn `node` (at `path`) into `value`; `top` is the PATH being set."""
    where = format_path(path)
    include = node.include
    if include is not None and is_bare(include, value):
        return
    if isinstance(node, TextNode):
        if not isinstance(value, str):
            raise WriteRefused(f"{where}: is the text of {node.target.name}; VALUE must be a string")
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
                if merged_in(node, entry.key) is not None:
                    raise merge_supplied(top, (*path, entry.key))
                if entry.alias is None:
                    _check_no_includes(entry.value, (*path, entry.key))
                    _check_no_merge_keys(entry.value, (*path, entry.key), top)
                deletes.append(Delete((*path, entry.key)))
        for key, child in value.items():
            existing = node.get(key)
            if existing is not None and merged_in(node, key) is not None:
                if not same(to_data(existing.value), child):
                    raise merge_supplied(top, (*path, key))
            elif existing is None:
                adds.append(new_key_target(root, (*path, key), child, in_include=in_include))
            elif existing.alias is not None:
                if not same(to_data(existing.value), child):
                    raise through_alias(root, top, (*path, key), existing.alias)
            else:
                _diff(root, existing.value, child, (*path, key), ops, in_include, top)
        ops.extend(adds + deletes)
        return
    if isinstance(node, SequenceNode) and isinstance(value, list) and (value or not node.items):
        for index, (item, child) in enumerate(zip(node.items, value, strict=False)):
            if item.alias is None:
                _diff(root, item.value, child, (*path, str(index)), ops, in_include, top)
            elif not same(to_data(item.value), child):
                raise through_alias(root, top, (*path, str(index)), item.alias)
        for index in range(len(node.items), len(value)):
            ops.append(Append((*path, str(index)), value[index]))
        for index in reversed(range(len(value), len(node.items))):
            if node.items[index].alias is None:
                _check_no_includes(node.items[index].value, (*path, str(index)))
                _check_no_merge_keys(node.items[index].value, (*path, str(index)), top)
            ops.append(Delete((*path, str(index))))
        return
    if isinstance(node, ScalarNode) and same(node.value, value):
        return
    _check_no_includes(node, path)
    if same(to_data(node), value):
        return
    _check_no_merge_keys(node, path, top)
    ops.append(Replace(path, value))
