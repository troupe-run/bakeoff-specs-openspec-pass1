"""YAML 1.2 core schema: resolving plain scalars and formatting scalars as text.

This module is the one place where scalar types are decided: what a plain scalar means when read, how a
scalar is printed by `show`, and how a non-string is written into a file.
"""

import math
import re

# A local tag meaning "this scalar is a string, taken literally": never an include.
LITERAL_TAG = "!literal"


class Literal(str):
    """A string to be written tagged `!literal`: it looks like an include but is meant as a string."""

    __slots__ = ()


type Scalar = bool | int | float | str | None
type Data = Scalar | dict[str, "Data"] | list["Data"]

_NULL = re.compile(r"null|Null|NULL|~|")
_TRUE = re.compile(r"true|True|TRUE")
_FALSE = re.compile(r"false|False|FALSE")
_INT10 = re.compile(r"[-+]?[0-9]+")
_INT8 = re.compile(r"0o[0-7]+")
_INT16 = re.compile(r"0x[0-9a-fA-F]+")
_FLOAT = re.compile(r"[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?")
_INF = re.compile(r"[-+]?(\.inf|\.Inf|\.INF)")
_NAN = re.compile(r"\.nan|\.NaN|\.NAN")


def resolve_plain(text: str) -> Scalar:
    """The value of a plain (unquoted) scalar under the core schema."""
    if _NULL.fullmatch(text):
        return None
    if _TRUE.fullmatch(text):
        return True
    if _FALSE.fullmatch(text):
        return False
    if _INT10.fullmatch(text):
        return int(text, 10)
    if _INT8.fullmatch(text):
        return int(text[2:], 8)
    if _INT16.fullmatch(text):
        return int(text[2:], 16)
    if _FLOAT.fullmatch(text):
        return float(text)
    if _INF.fullmatch(text):
        return -math.inf if text.startswith("-") else math.inf
    if _NAN.fullmatch(text):
        return math.nan
    return text


def resolve_tagged(text: str, tag: str) -> Scalar:
    """The value of a scalar with an explicit core-schema tag; ValueError for any other tag or mismatch."""
    short = tag.removeprefix("tag:yaml.org,2002:")
    if tag in ("!", LITERAL_TAG) or short == "str":
        return text
    value = resolve_plain(text)
    if short == "null" and value is None:
        return None
    if short == "bool" and isinstance(value, bool):
        return value
    if short == "int" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if short == "float" and isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise ValueError(f"unsupported tag {tag!r} for {text!r}")


def plain_text(value: Scalar) -> str:
    """The canonical plain text written into a file for a non-string scalar (and used for keys)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return ".nan"
        if math.isinf(value):
            return ".inf" if value > 0 else "-.inf"
        return repr(value)
    return value


def show_text(value: Scalar) -> str:
    """How `show` prints a scalar: strings exactly (newline-terminated), floats as Python repr()."""
    if isinstance(value, str):
        return value if value.endswith("\n") else value + "\n"
    if isinstance(value, float):
        return repr(value) + "\n"
    return plain_text(value) + "\n"


def key_text(value: Scalar) -> str:
    """The path segment naming a mapping key."""
    return value if isinstance(value, str) else plain_text(value)


def same(a: Data, b: Data) -> bool:
    """Strict equality: types must match (1, 1.0 and true differ), NaN equals NaN, key order is ignored."""
    if _kind(a) is not _kind(b):
        return False
    if isinstance(a, dict):
        assert isinstance(b, dict)
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        assert isinstance(b, list)
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def _kind(value: Data) -> type:
    """The type that equality compares: a `Literal` is a string."""
    return str if isinstance(value, str) else type(value)
