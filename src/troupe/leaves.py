"""Flattening configuration data into leaves (`{dotted path: scalar}`, document order) and diffing them."""

from troupe.schema import Data, Scalar, same
from troupe.store import Change


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


def diff_leaves(old: dict[str, Scalar], new: dict[str, Scalar]) -> list[Change]:
    """The events that turn `old` into `new`: removes in `old`'s order, then sets in `new`'s order.

    This one rule decides what both `set` and reconcile record. Values compare strictly (`schema.same`).
    """
    removed = [Change("remove", p, v, None) for p, v in old.items() if p not in new]
    changed = [Change("set", p, old.get(p), v) for p, v in new.items() if p not in old or not same(old[p], v)]
    return removed + changed
