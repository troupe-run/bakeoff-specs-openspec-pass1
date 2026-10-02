"""Parsing a command-line VALUE as a single YAML 1.2 flow node."""

from pathlib import Path

from troupe.errors import LoadError, UsageError
from troupe.schema import Data
from troupe.source import SourceFile
from troupe.tree import MappingNode, Node, ScalarNode, SequenceNode, build_tree, to_data


def parse_value(text: str) -> Data:
    try:
        root = build_tree(SourceFile(Path("VALUE"), text))
    except LoadError as e:
        raise UsageError(f"invalid VALUE {text!r}: {_reason(e)}") from None
    if root is None:
        return None
    if not _is_flow(root):
        raise UsageError(f"invalid VALUE {text!r}: must be a single flow node (quote it to make a string)")
    return to_data(root)


def _is_flow(node: Node) -> bool:
    if isinstance(node, ScalarNode):
        return node.style not in ("|", ">")
    if isinstance(node, MappingNode | SequenceNode):
        return node.flow_style
    return False


def _reason(error: LoadError) -> str:
    return str(error).split(": ", 1)[-1]
