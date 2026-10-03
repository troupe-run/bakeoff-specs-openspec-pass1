"""The `troupe config` subcommands: get, show, set, history and watch."""

import fcntl
import json
import math
import os
import signal
import sys
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path as FsPath
from typing import TextIO

from troupe.edit.apply import compute_set
from troupe.errors import LoadError, PathError
from troupe.leaves import leaves
from troupe.loader import CONFIG_NAMES, Config, find_config, load, state_dir
from troupe.paths import Path, format_path, is_index
from troupe.render import render
from troupe.schema import Data, Scalar, show_text
from troupe.source import read_source
from troupe.store import ConfigStore
from troupe.sync import reconcile
from troupe.tree import MappingNode, Node, ScalarNode, SequenceNode, TextNode, to_data

# Every command reconciles before its own work, except `history`, which reports only what has been recorded.
RECONCILING_COMMANDS = frozenset({"get", "show", "set", "watch"})


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
def theatre_session(
    theatre: FsPath, command: str, store: ConfigStore | None = None
) -> Iterator[tuple[Config, ConfigStore]]:
    """Under the theatre lock: load, import on the first command, reconcile if `command` does, then run.

    The config file is located before locking, so a theatre with none exits 4 without anything created.
    The store is opened only once the configuration has loaded; a long-running command may pass its own.
    """
    find_config(theatre)
    with theatre_lock(theatre):
        config = load(theatre)
        if store is None:
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


def get(theatre: FsPath, path: Path) -> str:
    """The scalar at `path`, printed; a mapping or list is refused with a pointer to `show`."""
    with theatre_session(theatre, "get") as (config, _):
        node = find(config.root, path)
    if not isinstance(node, ScalarNode | TextNode):
        kind = "mapping" if isinstance(node, MappingNode) else "list"
        where = format_path(path)
        raise PathError(f"{where}: is a {kind}, not a scalar (use `troupe config show {where}` to print it)")
    return show_text(node.value)


def show(theatre: FsPath, path: Path | None, sources: bool) -> str:
    """The value at `path` (or the whole configuration): a scalar as `get` prints it, anything else as YAML.

    With `sources`, the output is always YAML, with each scalar's file in an end-of-line comment.
    """
    with theatre_session(theatre, "show") as (config, _):
        node = config.root if path is None else find(config.root, path)
    if isinstance(node, ScalarNode | TextNode) and not sources:
        return show_text(node.value)
    return render(node, theatre, sources=sources)


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


# --- watch -------------------------------------------------------------------------------------------------

POLL_INTERVAL = 0.2  # seconds between reads of the watched files
SETTLE_POLLS = 2  # a change is reconciled once the files read the same on this many consecutive polls


class _Unreadable:
    """A watched file that exists but cannot be read as UTF-8 text."""


_UNREADABLE = _Unreadable()

# What each watched file holds: its text, None if it does not exist, or _UNREADABLE.
Snapshot = dict[FsPath, str | _Unreadable | None]


def _read_files(paths: Iterable[FsPath]) -> Snapshot:
    snapshot: Snapshot = {}
    for path in paths:
        if not path.exists():
            snapshot[path] = None
            continue
        try:
            snapshot[path] = read_source(path).text
        except LoadError:
            snapshot[path] = _UNREADABLE
    return snapshot


def _baseline(theatre: FsPath, config: Config) -> Snapshot:
    """The watched files as they were when `config` was loaded: every file it read, plus both config names.

    Using the loader's own texts means no edit can slip in between loading and starting to watch.
    """
    snapshot: Snapshot = {path: src.text for path, src in config.files.items()}
    for name in CONFIG_NAMES:
        snapshot.setdefault((state_dir(theatre) / name).resolve(), None)
    return snapshot


class _Watcher:
    def __init__(self, theatre: FsPath) -> None:
        self.theatre = theatre
        self.store: ConfigStore | None = None
        self.baseline: Snapshot | None = None  # None while the configuration does not load
        self.last_error: str | None = None
        self.pending: Snapshot | None = None
        self.stable = 0

    def start(self) -> None:
        """Load, import and reconcile; a load failure here propagates (exit 4)."""
        with theatre_session(self.theatre, "watch") as (config, store):
            self.store = store
            self.baseline = _baseline(self.theatre, config)

    def poll(self) -> None:
        if self.baseline is None:
            self.reconcile()  # nothing loaded to compare with: retry the whole load every poll
            return
        current = _read_files(self.baseline)
        if current == self.baseline:
            self.pending, self.stable = None, 0
            return
        if current != self.pending:
            self.pending, self.stable = current, 0
        self.stable += 1
        if self.stable >= SETTLE_POLLS:
            self.pending, self.stable = None, 0
            self.reconcile()

    def reconcile(self) -> None:
        try:
            with theatre_session(self.theatre, "watch", self.store) as (config, store):
                self.store = store
                self.baseline = _baseline(self.theatre, config)
        except LoadError as e:
            self.baseline = None
            if str(e) != self.last_error:
                self.last_error = str(e)
                print(f"troupe: {e}", file=sys.stderr, flush=True)
        else:
            self.last_error = None


def watch(theatre: FsPath, display: str, out: TextIO) -> None:
    """Reconcile now and whenever the config file or an included file changes, until SIGINT or SIGTERM.

    The signal handlers only set a flag, checked between cycles, so a reconcile in progress always finishes.
    """
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda _signum, _frame: stop.set())
    watcher = _Watcher(theatre)
    watcher.start()
    out.write(f"watching {display}\n")
    out.flush()
    while not stop.wait(POLL_INTERVAL):
        watcher.poll()
