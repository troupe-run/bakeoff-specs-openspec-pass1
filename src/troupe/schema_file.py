"""The theatre's JSON Schema, `.troupe/troupe.schema.json`: reading it, finding the schema of a position in
the configuration, and validating the configuration against it.

The schema is read under draft 2020-12 whatever its `$schema` says, `format` is an annotation (not checked),
and nothing is ever fetched: a `$ref` to anything outside the schema's own document fails to load.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, best_match
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable

from troupe.errors import LoadError
from troupe.schema import Data

SCHEMA_NAME = "troupe.schema.json"

# A position in the configuration: mapping keys as strings, list indexes as ints.
type Position = Sequence[str | int]

_REF_KEYWORDS = ("$ref", "$dynamicRef")
# Keywords whose value maps names to subschemas: the names are not keywords.
_SCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
# Keywords whose value is data, not schemas.
_DATA = ("enum", "const", "examples", "default", "required", "dependentRequired")


def _never_retrieve(uri: str) -> Resource:
    raise NoSuchResource(uri)


class Schema:
    def __init__(self, path: Path, text: str, document: object) -> None:
        self.path = path
        self.text = text  # as read, so `watch` compares against exactly what was loaded
        self.document = document
        registry: Registry[object] = Registry(retrieve=_never_retrieve)  # type: ignore[call-arg]
        self._validator = Draft202012Validator(document, registry=registry)  # type: ignore[arg-type]

    @classmethod
    def read(cls, state_dir: Path) -> "Schema | None":
        """The schema in `state_dir`, or None if there is none. LoadError if it is not a usable schema."""
        path = state_dir / SCHEMA_NAME
        if not path.exists():
            return None
        try:
            text = path.read_bytes().decode("utf-8")
            document = json.loads(text)
        except UnicodeDecodeError as e:
            raise LoadError(f"{path}: not valid UTF-8 ({e.reason})") from None
        except json.JSONDecodeError as e:
            raise LoadError(f"{path}: invalid JSON (line {e.lineno}, column {e.colno}): {e.msg}") from None
        except OSError as e:
            raise LoadError(f"{path}: cannot read ({e.strerror})") from None
        try:
            Draft202012Validator.check_schema(document)
        except SchemaError as e:
            raise LoadError(f"{path}: not a valid JSON Schema (draft 2020-12): {e.message}") from None
        outside = _outside_refs(document)
        if outside:
            raise LoadError(
                f"{path}: refers to {outside[0]!r}, outside this file; troupe never fetches schemas"
            )
        return cls(path, text, document)

    def at(self, position: Position) -> object | None:
        """The schema of `position`: through `properties` then `additionalProperties` for a mapping key, and
        `items` for a list index. Nothing else is followed. None where there is no such schema."""
        node: object = self.document
        for segment in position:
            if not isinstance(node, dict):
                return None
            if isinstance(segment, int):
                node = node.get("items")
            else:
                properties = node.get("properties")
                if isinstance(properties, dict) and segment in properties:
                    node = properties[segment]
                else:
                    node = node.get("additionalProperties")
        return node if isinstance(node, dict | bool) else None

    def is_uri(self, position: Position) -> bool:
        """Whether the schema marks the string at `position` as a URI: a literal, not an include."""
        node = self.at(position)
        return isinstance(node, dict) and node.get("format") == "uri"

    def validate(self, data: Data) -> None:
        """LoadError naming the schema file and a failing path if `data` is not valid against the schema."""
        try:
            error = best_match(self._validator.iter_errors(data))
        except Unresolvable as e:
            raise LoadError(f"{self.path}: cannot resolve {e}") from None
        if error is not None:
            where = ".".join(str(s) for s in error.absolute_path) or "the root"
            raise LoadError(f"{self.path}: the configuration is not valid at {where}: {error.message}")


def _outside_refs(node: object) -> list[str]:
    """Every `$ref`/`$dynamicRef` in the schema that points outside its own document."""
    found: list[str] = []

    def schema(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                schema(item)
            return
        if not isinstance(value, dict):
            return
        for key, sub in value.items():
            if key in _REF_KEYWORDS and isinstance(sub, str) and not sub.startswith("#"):
                found.append(sub)
            elif key in _SCHEMA_MAPS and isinstance(sub, dict):
                for named in sub.values():
                    schema(named)
            elif key not in _DATA:
                schema(sub)

    schema(node)
    return found
