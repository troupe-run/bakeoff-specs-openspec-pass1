"""What is an include, and where an include string points (the one place both are decided).

A string scalar starting `file:` names a file relative to the file that holds it, and one starting `https://`
or `http://` names a URL. A tagged scalar (`!literal`, or any other tag) is never an include, and neither is a
string the loader marked as a literal because the schema says it is a URI.
"""

from pathlib import Path
from urllib.parse import urljoin, urlsplit

from troupe.tree import ScalarNode

FILE_PREFIX = "file:"
URL_PREFIXES = ("https://", "http://")
INCLUDE_PREFIXES = (FILE_PREFIX, *URL_PREFIXES)
LITERAL_TAG = "!literal"
YAML_SUFFIXES = (".yml", ".yaml")

# Where included content lives: a local file's path, or a URL.
type Location = Path | str


def looks_like_include(value: str) -> bool:
    """Whether a string would be read as an include if it were written untagged."""
    return value.startswith(INCLUDE_PREFIXES)


def include_string(node: ScalarNode) -> str | None:
    """The include string if the scalar is an include, else None."""
    value = node.value
    if not isinstance(value, str) or node.tagged or node.literal or not looks_like_include(value):
        return None
    return value


def is_url(location: Location) -> bool:
    return isinstance(location, str)


def resolve(base: Location, string: str) -> Location:
    """The location an include string names, from the content at `base` (a local directory, or a URL)."""
    if string.startswith(URL_PREFIXES):
        return string
    target = string[len(FILE_PREFIX) :]
    if isinstance(base, str):
        return urljoin(base, target)
    return base / target


def is_yaml(location: Location) -> bool:
    """Whether included content is YAML: the name (for a URL, its path) ends `.yml` or `.yaml`."""
    name = urlsplit(location).path if isinstance(location, str) else str(location)
    return name.endswith(YAML_SUFFIXES)
