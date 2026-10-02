"""The event-sourced record of a theatre's configuration, persisted in SQLite under `.troupe/`.

One aggregate per theatre holds the leaf projection `{path: value}`. Its `Created` event marks the theatre
as imported; every later event concerns one leaf and is reported by `history` with `seq` = its position
among leaf events.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from eventsourcing.application import AggregateNotFoundError, Application
from eventsourcing.domain import Aggregate, event

from troupe.schema import Scalar

DB_NAME = "events.sqlite"


class TheatreConfig(Aggregate):
    @staticmethod
    def create_id() -> UUID:
        return uuid5(NAMESPACE_URL, "troupe:theatre-config")

    @event("Created")
    def __init__(self) -> None:
        self.leaves: dict[str, Scalar] = {}

    @event("Imported")
    def imported(self, path: str, new: Scalar) -> None:
        self.leaves[path] = new

    @event("LeafSet")
    def leaf_set(self, path: str, old: Scalar, new: Scalar) -> None:
        self.leaves[path] = new

    @event("LeafRemoved")
    def leaf_removed(self, path: str, old: Scalar) -> None:
        self.leaves.pop(path, None)


@dataclass(frozen=True)
class Change:
    op: str  # "import", "set" or "remove"
    path: str
    old: Scalar
    new: Scalar


@dataclass(frozen=True)
class Record:
    seq: int
    change: Change


_OPS = {"Imported": "import", "LeafSet": "set", "LeafRemoved": "remove"}


class ConfigStore:
    def __init__(self, state_dir: Path) -> None:
        self.app: Application[UUID] = Application(
            env={"PERSISTENCE_MODULE": "eventsourcing.sqlite", "SQLITE_DBNAME": str(state_dir / DB_NAME)}
        )
        self.id = TheatreConfig.create_id()

    def _get(self) -> TheatreConfig | None:
        try:
            aggregate: Aggregate = self.app.repository.get(self.id)
        except AggregateNotFoundError:
            return None
        assert isinstance(aggregate, TheatreConfig)
        return aggregate

    def is_imported(self) -> bool:
        return self._get() is not None

    def import_leaves(self, leaves: dict[str, Scalar]) -> None:
        aggregate = TheatreConfig()
        for path, value in leaves.items():
            aggregate.imported(path, value)
        self.app.save(aggregate)

    def record(self, changes: Iterable[Change]) -> None:
        aggregate = self._get()
        assert aggregate is not None, "theatre must be imported first"
        for c in changes:
            if c.op == "set":
                aggregate.leaf_set(c.path, c.old, c.new)
            elif c.op == "remove":
                aggregate.leaf_removed(c.path, c.old)
            else:
                raise ValueError(c.op)
        self.app.save(aggregate)

    def history(self) -> Iterator[Record]:
        for domain_event in self.app.events.get(self.id):
            op = _OPS.get(type(domain_event).__name__)
            if op is None:
                continue
            path: str = getattr(domain_event, "path")  # noqa: B009
            old: Scalar = getattr(domain_event, "old", None)
            new: Scalar = getattr(domain_event, "new", None)
            yield Record(seq=domain_event.originator_version - 1, change=Change(op, path, old, new))

    def projection(self) -> dict[str, Scalar]:
        aggregate = self._get()
        return dict(aggregate.leaves) if aggregate is not None else {}
