"""Loading a theatre's configuration: locating the config file and following `file:` includes."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from troupe.errors import LoadError
from troupe.overrides import REF_KEY, merge, override_entries, ref_entry
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
    include_target,
)

CONFIG_DIR = ".troupe"
CONFIG_NAMES = ("troupe.yml", "troupe.yaml")
YAML_SUFFIXES = (".yml", ".yaml")


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


def is_yaml_target(target: str | Path) -> bool:
    return str(target).endswith(YAML_SUFFIXES)


@dataclass(eq=False)
class Config:
    root: Node
    config_path: Path
    files: dict[Path, SourceFile] = field(default_factory=dict)  # every file read, by resolved path


def load(theatre: Path, overlay: Mapping[Path, str] | None = None) -> Config:
    """Load the configuration. `overlay` maps resolved paths to text used instead of the file on disk."""
    loader = _Loader(overlay or {})
    path = find_config(theatre)
    src = loader.read(path)
    root = build_tree(src)
    if root is None:
        root = MappingNode(
            file=src, start=len(src.text), end=len(src.text), in_flow=False, owner_col=-1, flow_style=False
        )
    root = loader.expand(root, path.parent, (path.resolve(),))
    return Config(root=root, config_path=path, files=loader.files)


class _Loader:
    def __init__(self, overlay: Mapping[Path, str]) -> None:
        self.overlay = overlay
        self.files: dict[Path, SourceFile] = {}
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

    def expand(self, node: Node, base: Path, stack: tuple[Path, ...]) -> Node:
        done = self.expanded.get(id(node))
        if done is None:
            done = self.expanded[id(node)] = self._expand(node, base, stack)
        return done

    def _expand(self, node: Node, base: Path, stack: tuple[Path, ...]) -> Node:
        match node:
            case ScalarNode():
                target = include_target(node)
                if target is None:
                    return node
                return self.include(node, base / target, stack)
            case MappingNode():
                ref = ref_entry(node)
                for entry in node.entries:
                    if entry is not ref:
                        entry.value = self.expand(entry.value, base, stack)
                if ref is not None:
                    return self.include_mapping(node, ref, base, stack)
            case SequenceNode():
                for item in node.items:
                    item.value = self.expand(item.value, base, stack)
        return node

    def include_mapping(self, mapping: MappingNode, ref: Entry, base: Path, stack: tuple[Path, ...]) -> Node:
        """A mapping-form include: the included content deep-merged with the mapping's other entries."""
        string = ref.value
        assert isinstance(string, ScalarNode)
        target = include_target(string)
        assert target is not None
        path = base / target
        root = self.include(string, path, stack)
        entries = override_entries(mapping)
        if entries:
            if isinstance(root, TextNode):
                raise LoadError(
                    f"{mapping.file.path}: {REF_KEY} {path} is not a YAML file, so it cannot have other keys"
                )
            if not isinstance(root, MappingNode):
                raise LoadError(
                    f"{mapping.file.path}: {REF_KEY} {path} is not a mapping, so it cannot have other keys"
                )
            root = merge(root, mapping, entries)
        root.include = Include(string=string, target=path, overrides=mapping)
        root.in_flow = mapping.in_flow
        return root

    def include(self, string: ScalarNode, path: Path, stack: tuple[Path, ...]) -> Node:
        key = path.resolve()
        if key in stack:
            raise LoadError(f"{path}: include cycle ({' -> '.join(str(p) for p in (*stack, key))})")
        if key not in self.overlay and not path.exists():
            raise LoadError(f"{path}: included file not found (from {string.file.path})")
        src = self.read(path)
        if not is_yaml_target(path):
            return TextNode(
                file=string.file,
                start=string.start,
                end=string.end,
                in_flow=string.in_flow,
                owner_col=string.owner_col,
                value=src.text,
                target=src,
                include=Include(string=string, target=path),
            )
        root = build_tree(src)
        if root is None:
            root = ScalarNode(file=src, start=0, end=0, in_flow=False, owner_col=-1, value=None, style=None)
        root = self.expand(root, path.parent, (*stack, key))
        root.include = Include(string=string, target=path)
        root.in_flow = string.in_flow
        return root
