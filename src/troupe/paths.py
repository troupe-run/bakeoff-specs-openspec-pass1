"""Dotted configuration paths: `agents.coder.model`, `tools.0`."""

from troupe.errors import UsageError

type Path = tuple[str, ...]


def parse_path(text: str) -> Path:
    segments = tuple(text.split("."))
    if text == "" or any(s == "" for s in segments):
        raise UsageError(f"invalid path {text!r}: empty segment")
    return segments


def format_path(path: Path) -> str:
    return ".".join(path)


def is_index(segment: str) -> bool:
    return segment.isascii() and segment.isdigit()
