"""Loading a theatre's configuration: locating the config file and following includes (files and URLs)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from troupe.errors import LoadError
from troupe.includes import Location, include_string, is_yaml, resolve
from troupe.overrides import REF_KEY, merge, override_entries, ref_entry
from troupe.remote import Fetcher
from troupe.schema_file import Position, Schema
from troupe.source import SourceFile, read_source
from troupe.tree import (
    Entry,
    Include,
    MappingNode,
    Node,
    ScalarNode,
    SequenceNode,
    TextNode,
    build_tree,
    to_data,
)

CONFIG_DIR = ".troupe"
CONFIG_NAMES = ("troupe.yml", "troupe.yaml")


def state_dir(theatre: Path) -> Path:
    return theatre / CONFIG_DIR


def find_config(theatre: Path) -> Path:
    candidates = [state_dir(theatre) / name for name in CONFIG_NAMES]
    present = [p for p in candidates if p.is_file()]
    if not present:
        raise LoadError(f"{candidates[0]}: no configuration file (expected {' or '.join(CONFIG_NAMES)})")
    if len(present) > 1:
        raise LoadError(f"{present[0]} and {present[1]}: both exist; keep only one")
    return present[0]


@dataclass(eq=False)
class Config:
    root: Node
    config_path: Path
    files: dict[Path, SourceFile] = field(default_factory=dict)  # every local file read, by resolved path
    # Remote content, by URL. Never in `files`, so nothing built from `files` (overlays, write-back, the
    # files `watch` polls) can touch a URL.
    remote: dict[str, SourceFile] = field(default_factory=dict)
    fetcher: Fetcher = field(default_factory=Fetcher)  # reuse it to see the same remote content again
    schema: Schema | None = None  # the theatre's `.troupe/troupe.schema.json`, if it has one


def load(
    theatre: Path,
    overlay: Mapping[Path, str] | None = None,
    fetcher: Fetcher | None = None,
    *,
    validate: bool = True,
) -> Config:
    """Load the configuration. `overlay` maps resolved paths to text used instead of the file on disk.

    Remote content comes from `fetcher` (a new one fetches afresh), so a reload sees what the last load saw.
    With `validate`, the result must be valid against the schema; `set` checks only its final result.
    """
    path = find_config(theatre)
    schema = Schema.read(state_dir(theatre))
    loader = _Loader(overlay or {}, fetcher or Fetcher(), schema)
    src = loader.read(path)
    root = build_tree(src)
    if root is None:
        root = MappingNode(
            file=src, start=len(src.text), end=len(src.text), in_flow=False, owner_col=-1, flow_style=False
        )
    root = loader.expand(root, path.parent, (path.resolve(),), ())
    if validate and schema is not None:
        schema.validate(to_data(root))
    return Config(
        root=root,
        config_path=path,
        files=loader.files,
        remote=loader.remote,
        fetcher=loader.fetcher,
        schema=schema,
    )


type _Key = Path | str  # a resolved local path, or a URL: what include cycles are detected by


class _Loader:
    def __init__(self, overlay: Mapping[Path, str], fetcher: Fetcher, schema: Schema | None) -> None:
        self.overlay = overlay
        self.fetcher = fetcher
        self.schema = schema
        self.files: dict[Path, SourceFile] = {}
        self.remote: dict[str, SourceFile] = {}
        # Each node expanded so far, by identity: a node reached again through an alias is expanded once.
        self.expanded: dict[int, Node] = {}

    def read(self, path: Path) -> SourceFile:
        key = path.resolve()
        if key in self.overlay:
            src = SourceFile(path, self.overlay[key])
        elif path.is_dir():
            raise LoadError(f"{path}: is a directory, not a file")
        else:
            src = read_source(path)
        self.files[key] = src
        return src

    def fetch(self, url: str, string: ScalarNode) -> SourceFile:
        src = SourceFile(Path(urlsplit(url).path), self.fetcher.text(url), url=url, included_by=string)
        self.remote[url] = src
        return src

    def expand(self, node: Node, base: Location, stack: tuple[_Key, ...], position: Position) -> Node:
        """Expand the includes in `node`, which is at `position` in the configuration; `base` is the directory
        (or URL) its includes are relative to.

        A node reached again through an alias is not expanded again, so it is judged where it is first
        reached: where its anchor is written.
        """
        done = self.expanded.get(id(node))
        if done is None:
            done = self.expanded[id(node)] = self._expand(node, base, stack, position)
        return done

    def mark_literal(self, node: Node, position: Position) -> None:
        """Mark an include-looking string at a position the schema says is a URI: it is a literal."""
        if (
            isinstance(node, ScalarNode)
            and self.schema is not None
            and include_string(node) is not None
            and self.schema.is_uri(position)
        ):
            node.literal = True

    def _expand(self, node: Node, base: Location, stack: tuple[_Key, ...], position: Position) -> Node:
        match node:
            case ScalarNode():
                self.mark_literal(node, position)
                string = include_string(node)
                if string is None:
                    return node
                return self.include(node, resolve(base, string), stack, position)
            case MappingNode():
                written_ref = node.get(REF_KEY)
                if written_ref is not None:
                    self.mark_literal(written_ref.value, (*position, REF_KEY))
                ref = ref_entry(node)
                for entry in node.entries:
                    if entry is not ref:
                        entry.value = self.expand(entry.value, base, stack, (*position, entry.key))
                if ref is not None:
                    return self.include_mapping(node, ref, base, stack, position)
            case SequenceNode():
                for index, item in enumerate(node.items):
                    item.value = self.expand(item.value, base, stack, (*position, index))
        return node

    def include_mapping(
        self, mapping: MappingNode, ref: Entry, base: Location, stack: tuple[_Key, ...], position: Position
    ) -> Node:
        """A mapping-form include: the included content deep-merged with the mapping's other entries."""
        string = ref.value
        assert isinstance(string, ScalarNode)
        include = include_string(string)
        assert include is not None
        target = resolve(base, include)
        root = self.include(string, target, stack, position)
        entries = override_entries(mapping)
        if entries:
            if isinstance(root, TextNode):
                raise LoadError(
                    f"{mapping.file.name}: {REF_KEY} {target} is not a YAML file, "
                    "so it cannot have other keys"
                )
            if not isinstance(root, MappingNode):
                raise LoadError(
                    f"{mapping.file.name}: {REF_KEY} {target} is not a mapping, so it cannot have other keys"
                )
            root = merge(root, mapping, entries)
        root.include = Include(string=string, target=target, overrides=mapping)
        root.in_flow = mapping.in_flow
        return root

    def include(
        self, string: ScalarNode, target: Location, stack: tuple[_Key, ...], position: Position
    ) -> Node:
        key: _Key = target if isinstance(target, str) else target.resolve()
        if key in stack:
            raise LoadError(f"{target}: include cycle ({' -> '.join(str(p) for p in (*stack, key))})")
        base: Location
        if isinstance(target, str):
            src = self.fetch(target, string)
            base = target
        else:
            if target.resolve() not in self.overlay and not target.exists():
                raise LoadError(f"{target}: included file not found (from {string.file.name})")
            src = self.read(target)
            base = target.parent
        if not is_yaml(target):
            return TextNode(
                file=string.file,
                start=string.start,
                end=string.end,
                in_flow=string.in_flow,
                owner_col=string.owner_col,
                value=src.text,
                target=src,
                include=Include(string=string, target=target),
            )
        root = build_tree(src)
        if root is None:
            root = ScalarNode(file=src, start=0, end=0, in_flow=False, owner_col=-1, value=None, style=None)
        root = self.expand(root, base, (*stack, key), position)
        root.include = Include(string=string, target=target)
        root.in_flow = string.in_flow
        return root
