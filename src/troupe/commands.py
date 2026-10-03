"""The `troupe config` subcommands: show, set and history."""

import fcntl
import json
import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path as FsPath

from troupe.edit.apply import compute_set
from troupe.errors import LoadError, PathError
from troupe.leaves import leaves
from troupe.loader import Config, find_config, load, state_dir
from troupe.paths import Path, format_path, is_index
from troupe.schema import Data, Scalar, show_text
from troupe.store import ConfigStore
from troupe.sync import reconcile
from troupe.tree import MappingNode, Node, ScalarNode, SequenceNode, TextNode, to_data

# Every command reconciles before its own work, except `history`, which reports only what has been recorded.
RECONCILING_COMMANDS = frozenset({"show", "set", "watch"})


@contextmanager
def theatre_lock(theatre: FsPath) -> Iterator[None]:
    """Hold an exclusive lock on the theatre's `.troupe/` directory, so commands never interleave.

    The lock is on the directory itself, so it creates no file; the OS releases it if the process dies.
    """
    directory = state_dir(theatre)
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError as e:
        raise LoadError(f"{directory}: cannot open for locking ({e.strerror})") from e
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as e:
            raise LoadError(f"{directory}: cannot lock ({e.strerror})") from e
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


@contextmanager
def theatre_session(theatre: FsPath, command: str) -> Iterator[tuple[Config, ConfigStore]]:
    """Under the theatre lock: load, import on the first command, reconcile if `command` does, then run.

    The config file is located before locking, so a theatre with none exits 4 without anything created.
    """
    find_config(theatre)
    with theatre_lock(theatre):
        config = load(theatre)
        store = ConfigStore(state_dir(theatre))
        if not store.is_imported():
            store.import_leaves(leaves(to_data(config.root)))
        if command in RECONCILING_COMMANDS:
            reconcile(config, store)
        yield config, store


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
    with theatre_session(theatre, "show") as (config, _):
        node = find(config.root, path)
    if not isinstance(node, ScalarNode | TextNode):
        kind = "mapping" if isinstance(node, MappingNode) else "list"
        raise PathError(f"{format_path(path)}: is a {kind}, not a scalar")
    return show_text(node.value)


def set_value(theatre: FsPath, path: Path, value: Data) -> None:
    # The lock is held until the events are recorded, so no reconcile can see the written files first.
    with theatre_session(theatre, "set") as (config, store):
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
    with theatre_session(theatre, "history") as (_, store):
        records = list(store.history())
    prefix = format_path(path) if path is not None else None
    lines = []
    for record in records:
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
