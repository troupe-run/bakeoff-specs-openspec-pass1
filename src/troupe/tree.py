"""The configuration tree: YAML nodes that remember where they are in which source file.

`build_tree` turns one file's text into nodes using the parser's events and marks. Scalars are resolved
with the core schema in `troupe.schema`, not with the parser's own resolver.
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
from troupe.schema import Data, Scalar, key_text, resolve_plain, resolve_tagged
from troupe.source import SourceFile


@dataclass(eq=False, kw_only=True)
class Include:
    """How a node came into the tree through `file:`: the include string and the file it names."""

    string: "ScalarNode"
    target: Path


@dataclass(eq=False, kw_only=True)
class Node:
    file: SourceFile
    start: int
    end: int  # end of the node's own text (for block scalars: of the last content line)
    in_flow: bool  # the node sits inside a flow collection
    owner_col: int  # column of the key or `-` that owns this node (-1 for a document root)
    include: Include | None = None  # set on the root node of an included YAML file


@dataclass(eq=False, kw_only=True)
class ScalarNode(Node):
    value: Scalar
    style: str | None  # None (plain), "'", '"', "|" or ">"
    tagged: bool = False
    block: BlockLayout | None = None
    opaque: bool = False  # we could not reproduce its layout; refuse to edit it


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


@dataclass(eq=False, kw_only=True)
class MappingNode(Node):
    flow_style: bool
    entries: list[Entry] = field(default_factory=list)

    def get(self, key: str) -> Entry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None


@dataclass(eq=False, kw_only=True)
class Item:
    value: Node
    dash: int | None  # offset of the `-` for block sequences


@dataclass(eq=False, kw_only=True)
class SequenceNode(Node):
    flow_style: bool
    items: list[Item] = field(default_factory=list)


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
        raise LoadError(f"{src.path}: invalid YAML{where}: {e.problem or e.context}") from None
    except YAMLError as e:
        raise LoadError(f"{src.path}: invalid YAML: {e}") from None


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
        return LoadError(f"{self.src.path} (line {mark.line + 1}, column {mark.column + 1}): {message}")

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

    def node(self, *, in_flow: bool, owner_col: int) -> Node:
        event = self.next()
        if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
            raise self.fail(event, "anchors and aliases are not supported")
        if isinstance(event, ScalarEvent):
            return self.scalar(event, in_flow=in_flow, owner_col=owner_col)
        if isinstance(event, MappingStartEvent):
            return self.mapping(event, in_flow=in_flow, owner_col=owner_col)
        if isinstance(event, SequenceStartEvent):
            return self.sequence(event, in_flow=in_flow, owner_col=owner_col)
        raise self.fail(event, f"unexpected {type(event).__name__}")

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
        node = ScalarNode(
            file=self.src,
            start=start,
            end=end,
            in_flow=in_flow,
            owner_col=owner_col,
            value=value,
            style=style,
            tagged=tagged,
        )
        if style in ("|", ">"):
            layout = parse_block(self.src, start, owner_col)
            node.block = layout
            node.end = layout.content_end
            node.opaque = tagged or layout.value() != text or (style == ">" and layout.more_indented)
        return node

    def collection_tag_ok(self, event: MappingStartEvent | SequenceStartEvent, kind: str) -> None:
        if event.tag is not None and not event.implicit and event.tag != f"tag:yaml.org,2002:{kind}":
            raise self.fail(event, f"unsupported tag {event.tag!r}")

    def mapping(self, event: MappingStartEvent, *, in_flow: bool, owner_col: int) -> MappingNode:
        self.collection_tag_ok(event, "map")
        flow = bool(event.flow_style)
        node = MappingNode(
            file=self.src,
            start=event.start_mark.index,
            end=event.start_mark.index,
            in_flow=in_flow,
            owner_col=owner_col,
            flow_style=flow,
        )
        while not isinstance(self.peek(), MappingEndEvent):
            key_event = self.peek()
            if not isinstance(key_event, ScalarEvent):
                raise self.fail(key_event, "only scalar mapping keys are supported")
            key_node = self.node(in_flow=in_flow or flow, owner_col=owner_col)
            assert isinstance(key_node, ScalarNode)
            key = key_text(key_node.value)
            if node.get(key) is not None:
                raise self.fail(key_event, f"duplicate key {key!r}")
            value = self.node(in_flow=in_flow or flow, owner_col=self.src.column(key_node.start))
            node.entries.append(Entry(key=key, key_node=key_node, value=value))
            node.end = max(value.end, key_node.end)
        end_event = self.next()
        if flow:
            node.end = end_event.end_mark.index
        elif node.entries:
            node.start = node.entries[0].key_node.start
        return node

    def sequence(self, event: SequenceStartEvent, *, in_flow: bool, owner_col: int) -> SequenceNode:
        self.collection_tag_ok(event, "seq")
        flow = bool(event.flow_style)
        start = event.start_mark.index
        node = SequenceNode(
            file=self.src,
            start=start,
            end=start,
            in_flow=in_flow,
            owner_col=owner_col,
            flow_style=flow,
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
            value = self.node(in_flow=in_flow or flow, owner_col=col)
            node.items.append(Item(value=value, dash=dash))
            prev_end = node.end = max(value.end, dash + 1 if dash is not None else value.end)
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
        raise LoadError(f"{self.src.path}: cannot locate a sequence entry before offset {hi}")
