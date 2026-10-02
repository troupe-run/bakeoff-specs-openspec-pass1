"""The `troupe config` subcommands: show, set and history."""

import json
import math
from pathlib import Path as FsPath

from troupe.edit.apply import compute_set
from troupe.errors import PathError
from troupe.leaves import leaves
from troupe.loader import Config, load, state_dir
from troupe.paths import Path, format_path, is_index
from troupe.schema import Data, Scalar, show_text
from troupe.store import ConfigStore
from troupe.tree import MappingNode, Node, ScalarNode, SequenceNode, TextNode, to_data


def open_theatre(theatre: FsPath) -> tuple[Config, ConfigStore]:
    """Load the configuration, then import it into the event store if this is the first command."""
    config = load(theatre)
    store = ConfigStore(state_dir(theatre))
    if not store.is_imported():
        store.import_leaves(leaves(to_data(config.root)))
    return config, store


def find(root: Node, path: Path) -> Node:
    node = root
    for i, segment in enumerate(path):
        where = format_path(path)
        if isinstance(node, MappingNode):
            entry = node.get(segment)
            if entry is None:
                raise PathError(f"{where}: not found")
            node = entry.value
        elif isinstance(node, SequenceNode):
            if not is_index(segment) or int(segment) >= len(node.items):
                raise PathError(
                    f"{where}: not found ({format_path(path[:i])} is a list of {len(node.items)})"
                )
            node = node.items[int(segment)].value
        else:
            raise PathError(f"{where}: not found ({format_path(path[:i])} is a scalar)")
    return node


def show(theatre: FsPath, path: Path) -> str:
    config, _ = open_theatre(theatre)
    node = find(config.root, path)
    if not isinstance(node, ScalarNode | TextNode):
        kind = "mapping" if isinstance(node, MappingNode) else "list"
        raise PathError(f"{format_path(path)}: is a {kind}, not a scalar")
    return show_text(node.value)


def set_value(theatre: FsPath, path: Path, value: Data) -> None:
    config, store = open_theatre(theatre)
    result = compute_set(theatre, config, path, value)
    for file, text in result.writes.items():
        with file.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
    if result.changes:
        store.record(result.changes)


def _json_value(value: Scalar) -> Scalar:
    if isinstance(value, float) and not math.isfinite(value):
        return ".nan" if math.isnan(value) else (".inf" if value > 0 else "-.inf")
    return value


def history(theatre: FsPath, path: Path | None) -> str:
    _, store = open_theatre(theatre)
    prefix = format_path(path) if path is not None else None
    lines = []
    for record in store.history():
        c = record.change
        if prefix is not None and not (c.path == prefix or c.path.startswith(prefix + ".")):
            continue
        obj = {
            "seq": record.seq,
            "op": c.op,
            "path": c.path,
            "old": _json_value(c.old),
            "new": _json_value(c.new),
        }
        lines.append(json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n")
    return "".join(lines)
