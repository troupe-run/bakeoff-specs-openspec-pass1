"""Flattening configuration data into leaves: `{dotted path: scalar}` in document order."""

from troupe.schema import Data, Scalar


def leaves(data: Data, prefix: str = "") -> dict[str, Scalar]:
    out: dict[str, Scalar] = {}
    _walk(data, prefix, out)
    return out


def _walk(data: Data, path: str, out: dict[str, Scalar]) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            _walk(value, f"{path}.{key}" if path else key, out)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            _walk(value, f"{path}.{index}" if path else str(index), out)
    else:
        out[path] = data
