"""The configuration tree: YAML nodes that remember where they are in which source file.

`build_tree` turns one file's text into nodes using the parser's events and marks. Scalars are resolved
with the core schema in `troupe.schema`, not with the parser's own resolver.

An alias is not a node of its own: the entry or item holding it records the `Alias`, and its value is the
anchored node object itself, so every reader sees the anchored value. A node's span never includes its
anchor (`&name`), so replacing the value keeps the anchor. A mapping with a merge key (`<<`) is resolved into
the merged mapping, which keeps the mapping as written in `written`.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.events import (
    AliasEvent,
    DocumentEndEvent,
    DocumentStartEvent,
    Event,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
    StreamEndEvent,
    StreamStartEvent,
)

from troupe.blockscalar import BlockLayout, parse_block
from troupe.errors import LoadError
from troupe.schema import LITERAL_TAG, Data, Scalar, key_text, resolve_plain, resolve_tagged
from troupe.source import SourceFile


@dataclass(eq=False, kw_only=True)
class Include:
    """How a node came into the tree through an include: the include string and the file or URL it names."""

    string: "ScalarNode"
    target: Path | str  # a local file, or a URL
    overrides: "MappingNode | None" = None  # mapping form: the `$ref` mapping, as written where it is


@dataclass(eq=False, kw_only=True)
class Anchor:
    """The `&name` written in front of a node: its name and where the text is."""

    name: str
    start: int
    end: int


@dataclass(eq=False, kw_only=True)
class Tag:
    """A `!literal` tag written in front of a scalar: where its text is (outside the scalar's span)."""

    start: int
    end: int


@dataclass(eq=False, kw_only=True)
class Node:
    file: SourceFile
    start: int
    end: int  # end of the node's own text (for block scalars: of the last content line)
    in_flow: bool  # the node sits inside a flow collection
    owner_col: int  # column of the key or `-` that owns this node (-1 for a document root)
    include: Include | None = None  # set on the root node of an included YAML file
    anchor: Anchor | None = None  # the node's `&name`, outside its span


@dataclass(eq=False, kw_only=True)
class Alias:
    """A `*name` written as an entry's or item's value; the value is then `target`, the anchored node."""

    name: str
    start: int
    end: int
    in_flow: bool  # the alias sits inside a flow collection
    target: Node


@dataclass(eq=False, kw_only=True)
class ScalarNode(Node):
    value: Scalar
    style: str | None  # None (plain), "'", '"', "|" or ">"
    tagged: bool = False
    literal_tag: Tag | None = None  # a `!literal` tag, outside the span, so replacing a string keeps it
    block: BlockLayout | None = None
    opaque: bool = False  # we could not reproduce its layout; refuse to edit it
    literal: bool = False  # set by the loader where the schema says the string is a URI, not an include


@dataclass(eq=False, kw_only=True)
class TextNode(Node):
    """A text include. Its span is that of the include string; the value is the target file's text."""

    value: str
    target: SourceFile


@dataclass(eq=False, kw_only=True)
class Entry:
    key: str
    key_node: ScalarNode
    value: Node
    alias: Alias | None = None


@dataclass(eq=False, kw_only=True)
class MappingNode(Node):
    flow_style: bool
    entries: list[Entry] = field(default_factory=list)
    # For a mapping merged from included content and overrides: the mappings as written, included first.
    # Empty for a mapping as written in one file.
    layers: list["MappingNode"] = field(default_factory=list)
    # For a mapping with a merge key: the mapping as written (its own entries and the `<<` entry).
    written: "MappingNode | None" = None

    def get(self, key: str) -> Entry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None


@dataclass(eq=False, kw_only=True)
class Item:
    value: Node
    dash: int | None  # offset of the `-` for block sequences
    alias: Alias | None = None


@dataclass(eq=False, kw_only=True)
class SequenceNode(Node):
    flow_style: bool
    items: list[Item] = field(default_factory=list)


MERGE_KEY = "<<"


def is_merge_key(key_node: ScalarNode) -> bool:
    """Whether a key is a merge key: a plain, untagged `<<`."""
    return key_node.style is None and not key_node.tagged and key_node.value == MERGE_KEY


def merged_in(mapping: MappingNode, key: str) -> Entry | None:
    """The `<<` entry if the mapping's value at `key` is supplied by a merge key, else None."""
    written = mapping.written
    if written is None or written.get(key) is not None or mapping.get(key) is None:
        return None
    return next(e for e in written.entries if is_merge_key(e.key_node))


def to_data(node: Node) -> Data:
    match node:
        case ScalarNode() | TextNode():
            return node.value
        case MappingNode():
            return {e.key: to_data(e.value) for e in node.entries}
        case SequenceNode():
            return [to_data(i.value) for i in node.items]
    raise TypeError(node)


def parse_events(src: SourceFile) -> list[Event]:
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    try:
        return list(yaml.parse(src.text))
    except MarkedYAMLError as e:
        mark = e.problem_mark or e.context_mark
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark is not None else ""
        raise LoadError(f"{src.name}: invalid YAML{where}: {e.problem or e.context}") from None
    except YAMLError as e:
        raise LoadError(f"{src.name}: invalid YAML: {e}") from None


def build_tree(src: SourceFile) -> Node | None:
    """The document's root node, or None for a file with no document (empty or only comments)."""
    events = parse_events(src)
    builder = _Builder(src, iter(events))
    return builder.stream()


class _Builder:
    def __init__(self, src: SourceFile, events: Iterator[Event]) -> None:
        self.src = src
        self.events = events
        self.peeked: Event | None = None
        self.anchors: dict[str, Node] = {}  # the latest complete node with each anchor name
        self.building: set[str] = set()  # anchor names of nodes still being built

    def next(self) -> Event:
        if self.peeked is not None:
            event, self.peeked = self.peeked, None
            return event
        return next(self.events)

    def peek(self) -> Event:
        if self.peeked is None:
            self.peeked = next(self.events)
        return self.peeked

    def fail(self, event: Event, message: str) -> LoadError:
        mark = event.start_mark
        return LoadError(f"{self.src.name} (line {mark.line + 1}, column {mark.column + 1}): {message}")

    def stream(self) -> Node | None:
        assert isinstance(self.next(), StreamStartEvent)
        root: Node | None = None
        documents = 0
        while not isinstance(self.peek(), StreamEndEvent):
            event = self.next()
            assert isinstance(event, DocumentStartEvent)
            documents += 1
            if documents > 1:
                raise self.fail(event, "multiple documents are not supported")
            root = self.node(in_flow=False, owner_col=-1)
            assert isinstance(self.next(), DocumentEndEvent)
        return root

    def value(self, *, in_flow: bool, owner_col: int) -> tuple[Node, Alias | None]:
        """The next value, and the alias it was written as (None for a node written in place)."""
        event = self.peek()
        if not isinstance(event, AliasEvent):
            return self.node(in_flow=in_flow, owner_col=owner_col), None
        self.next()
        name = str(event.anchor)
        target = self.anchors.get(name)
        if target is None:
            inside = name in self.building
            problem = "is inside the node it refers to" if inside else "has no anchor before it"
            raise self.fail(event, f"alias *{name} {problem}")
        alias = Alias(
            name=name, start=event.start_mark.index, end=event.end_mark.index, in_flow=in_flow, target=target
        )
        return target, alias

    def node(self, *, in_flow: bool, owner_col: int) -> Node:
        event = self.next()
        if isinstance(event, AliasEvent):
            raise self.fail(event, f"unexpected alias *{event.anchor}")
        name: str | None = getattr(event, "anchor", None)
        if name is not None:
            self.building.add(name)
        node: Node
        if isinstance(event, ScalarEvent):
            node = self.scalar(event, in_flow=in_flow, owner_col=owner_col)
        elif isinstance(event, MappingStartEvent):
            node = self.mapping(event, in_flow=in_flow, owner_col=owner_col)
        elif isinstance(event, SequenceStartEvent):
            node = self.sequence(event, in_flow=in_flow, owner_col=owner_col)
        else:
            raise self.fail(event, f"unexpected {type(event).__name__}")
        if name is not None:
            self.building.discard(name)
            self.anchors[name] = node
        return node

    def anchor_of(self, event: Event) -> Anchor | None:
        name: str | None = getattr(event, "anchor", None)
        if name is None:
            return None
        start = self.src.text.find("&" + name, event.start_mark.index)
        assert start >= 0, name
        return Anchor(name=name, start=start, end=start + 1 + len(name))

    def after_anchor(self, anchor: Anchor) -> int:
        """The offset where the anchored node's own text starts: past spaces, comments and line breaks."""
        return self.after_properties(anchor.end)

    def after_properties(self, pos: int) -> int:
        """The offset past spaces, comments and line breaks from `pos` (the end of an anchor or tag)."""
        text = self.src.text
        while pos < len(text):
            ch = text[pos]
            if ch in " \t\r\n":
                pos += 1
            elif ch == "#":
                pos = self.src.next_line(pos)
            else:
                break
        return pos

    def scalar(self, event: ScalarEvent, *, in_flow: bool, owner_col: int) -> ScalarNode:
        style = event.style or None
        text: str = event.value
        tagged = False
        value: Scalar
        if style is None and event.implicit[0]:
            value = resolve_plain(text)
        elif style is not None and event.implicit[1]:
            value = text
        else:
            tagged = True
            try:
                value = resolve_tagged(text, str(event.tag))
            except ValueError as e:
                raise self.fail(event, str(e)) from None
        start, end = event.start_mark.index, event.end_mark.index
        anchor = self.anchor_of(event)
        if anchor is not None and anchor.start == start:
            # A tag before the anchor stays in the (never rewritten) span; an empty scalar ends at its anchor.
            start = min(self.after_properties(anchor.end), end)
        literal_tag: Tag | None = None
        if tagged and str(event.tag) == LITERAL_TAG and self.src.text.startswith(LITERAL_TAG, start):
            literal_tag = Tag(start=start, end=start + len(LITERAL_TAG))
            start = min(self.after_properties(literal_tag.end), end)
            if anchor is not None and anchor.start == start:
                start = min(self.after_properties(anchor.end), end)
        node = ScalarNode(
            file=self.src,
            start=start,
            end=end,
            in_flow=in_flow,
            owner_col=owner_col,
            value=value,
            style=style,
            tagged=tagged,
            literal_tag=literal_tag,
            anchor=anchor,
        )
        if style in ("|", ">"):
            layout = parse_block(self.src, start, owner_col)
            node.block = layout
            node.end = layout.content_end
            node.opaque = (
                (tagged and literal_tag is None)
                or layout.value() != text
                or (style == ">" and layout.more_indented)
            )
        return node

    def collection_tag_ok(self, event: MappingStartEvent | SequenceStartEvent, kind: str) -> None:
        if event.tag is not None and not event.implicit and event.tag != f"tag:yaml.org,2002:{kind}":
            raise self.fail(event, f"unsupported tag {event.tag!r}")

    def mapping(self, event: MappingStartEvent, *, in_flow: bool, owner_col: int) -> MappingNode:
        self.collection_tag_ok(event, "map")
        flow = bool(event.flow_style)
        anchor = self.anchor_of(event)
        start = self.after_anchor(anchor) if anchor is not None else event.start_mark.index
        node = MappingNode(
            file=self.src,
            start=start,
            end=start,
            in_flow=in_flow,
            owner_col=owner_col,
            flow_style=flow,
            anchor=anchor,
        )
        merges: list[tuple[Entry, list[MappingNode]]] = []
        while not isinstance(self.peek(), MappingEndEvent):
            key_event = self.peek()
            if isinstance(key_event, AliasEvent) or getattr(key_event, "anchor", None) is not None:
                raise self.fail(key_event, "anchors and aliases cannot be mapping keys")
            if not isinstance(key_event, ScalarEvent):
                raise self.fail(key_event, "only scalar mapping keys are supported")
            key_node = self.node(in_flow=in_flow or flow, owner_col=owner_col)
            assert isinstance(key_node, ScalarNode)
            key = key_text(key_node.value)
            if node.get(key) is not None:
                raise self.fail(key_event, f"duplicate key {key!r}")
            value_event = self.peek()
            value, alias = self.value(in_flow=in_flow or flow, owner_col=self.src.column(key_node.start))
            entry = Entry(key=key, key_node=key_node, value=value, alias=alias)
            node.entries.append(entry)
            node.end = max(alias.end if alias is not None else value.end, key_node.end)
            if is_merge_key(key_node):
                merges.append((entry, self.merge_sources(value_event, value)))
        end_event = self.next()
        if flow:
            node.end = end_event.end_mark.index
        elif node.entries:
            node.start = node.entries[0].key_node.start
        return node if not merges else _resolve_merges(node, merges)

    def merge_sources(self, event: Event, value: Node) -> list[MappingNode]:
        """The mappings a merge key's value names: a mapping, or a list of mappings."""
        if isinstance(value, MappingNode):
            return [value]
        if isinstance(value, SequenceNode) and all(isinstance(i.value, MappingNode) for i in value.items):
            return [i.value for i in value.items if isinstance(i.value, MappingNode)]
        raise self.fail(event, f"the value of merge key {MERGE_KEY} must be a mapping or a list of mappings")

    def sequence(self, event: SequenceStartEvent, *, in_flow: bool, owner_col: int) -> SequenceNode:
        self.collection_tag_ok(event, "seq")
        flow = bool(event.flow_style)
        anchor = self.anchor_of(event)
        start = self.after_anchor(anchor) if anchor is not None else event.start_mark.index
        node = SequenceNode(
            file=self.src,
            start=start,
            end=start,
            in_flow=in_flow,
            owner_col=owner_col,
            flow_style=flow,
            anchor=anchor,
        )
        dash_col = self.src.column(start)
        prev_end = start
        while not isinstance(self.peek(), SequenceEndEvent):
            dash: int | None = None
            if not flow:
                dash = (
                    start
                    if not node.items
                    else self.find_dash(prev_end, self.peek().start_mark.index, dash_col)
                )
            col = self.src.column(dash) if dash is not None else owner_col
            value, alias = self.value(in_flow=in_flow or flow, owner_col=col)
            value_end = alias.end if alias is not None else value.end
            node.items.append(Item(value=value, dash=dash, alias=alias))
            prev_end = node.end = max(value_end, dash + 1 if dash is not None else value_end)
        end_event = self.next()
        if flow:
            node.end = end_event.end_mark.index
        return node

    def find_dash(self, lo: int, hi: int, col: int) -> int:
        text = self.src.text
        pos = hi - 1
        while pos >= lo:
            if (
                text[pos] == "-"
                and self.src.column(pos) == col
                and text[self.src.line_start(pos) : pos].strip(" ") == ""
            ):
                return pos
            pos -= 1
        raise LoadError(f"{self.src.name}: cannot locate a sequence entry before offset {hi}")


def _resolve_merges(written: MappingNode, merges: list[tuple[Entry, list[MappingNode]]]) -> MappingNode:
    """The mapping `written` with its merge keys applied.

    Its own keys win, then earlier merge sources. Merged-in entries take the `<<` entry's position.
    """
    own = {e.key for e in written.entries if not is_merge_key(e.key_node)}
    sources = {id(entry): mappings for entry, mappings in merges}
    seen: set[str] = set()
    entries: list[Entry] = []
    for entry in written.entries:
        if id(entry) not in sources:
            entries.append(entry)
            continue
        for mapping in sources[id(entry)]:
            for merged in mapping.entries:
                if merged.key not in own and merged.key not in seen:
                    seen.add(merged.key)
                    entries.append(merged)
    return MappingNode(
        file=written.file,
        start=written.start,
        end=written.end,
        in_flow=written.in_flow,
        owner_col=written.owner_col,
        flow_style=written.flow_style,
        anchor=written.anchor,
        entries=entries,
        written=written,
    )
