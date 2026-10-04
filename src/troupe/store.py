"""The event-sourced record of a theatre's configuration, persisted in SQLite under `.troupe/`.

One aggregate per theatre holds the leaf projection `{path: value}`. Its `Created` event marks the theatre
as imported; every later event concerns one leaf, carries the lineage of the change it belongs to, and is
reported by `history` with `seq` = its position among leaf events.

Leaf events are at class version 2 (with lineage). Version-1 events, written before lineage existed, are
upcast when read; nothing on disk is rewritten.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from eventsourcing.application import AggregateNotFoundError, Application
from eventsourcing.domain import Aggregate, event

from troupe.lineage import Actor, ActorKind, Lineage, Via, format_timestamp
from troupe.schema import Scalar

DB_NAME = "events.sqlite"

LEGACY_IMPORT_CHANGE = "legacy-import"


def _seq(originator_version: int) -> int:
    """An event's position among leaf events (version 1 is `Created`)."""
    return originator_version - 1


def _legacy_lineage(state: dict[str, Any], via: Via) -> None:
    """Fill in the lineage of a version-1 event: unknown actor, its stored time, one change per event.

    The old imports were one change, so they share one id. Old set/remove events cannot be told apart
    (CLI or reconcile, which batch), so each is its own change and is reported as `file`, the only
    `via` that goes with an unknown actor.
    """
    timestamp: datetime = state["timestamp"]
    state.update(
        actor_kind="unknown",
        actor_id=None,
        via=via,
        at=format_timestamp(timestamp),
        reason=None,
        change=LEGACY_IMPORT_CHANGE if via == "import" else f"legacy-{_seq(state['originator_version'])}",
    )


class LeafEvent(Aggregate.Event):
    """A change to one leaf, with the lineage of the change it belongs to."""

    class_version: ClassVar[int] = 2
    path: str
    actor_kind: str
    actor_id: str | None
    via: str
    at: str
    reason: str | None
    change: str

    @property
    def lineage(self) -> Lineage:
        return Lineage(
            Actor(cast(ActorKind, self.actor_kind), self.actor_id),
            cast(Via, self.via),
            self.at,
            self.reason,
            self.change,
        )


def _lineage_kwargs(lineage: Lineage) -> dict[str, Any]:
    return {
        "actor_kind": lineage.actor.kind,
        "actor_id": lineage.actor.id,
        "via": lineage.via,
        "at": lineage.at,
        "reason": lineage.reason,
        "change": lineage.change,
    }


class TheatreConfig(Aggregate):
    # The class names are the stored topics (`troupe.store:TheatreConfig.LeafSet`, …): do not rename.
    class Imported(LeafEvent):
        new: Scalar

        @staticmethod
        def upcast_v1_v2(state: dict[str, Any]) -> None:
            _legacy_lineage(state, "import")

        def apply(self, aggregate: Any) -> None:
            aggregate.leaves[self.path] = self.new

    class LeafSet(LeafEvent):
        old: Scalar
        new: Scalar

        @staticmethod
        def upcast_v1_v2(state: dict[str, Any]) -> None:
            _legacy_lineage(state, "file")

        def apply(self, aggregate: Any) -> None:
            aggregate.leaves[self.path] = self.new

    class LeafRemoved(LeafEvent):
        old: Scalar

        @staticmethod
        def upcast_v1_v2(state: dict[str, Any]) -> None:
            _legacy_lineage(state, "file")

        def apply(self, aggregate: Any) -> None:
            aggregate.leaves.pop(self.path, None)

    @staticmethod
    def create_id() -> UUID:
        return uuid5(NAMESPACE_URL, "troupe:theatre-config")

    @event("Created")
    def __init__(self) -> None:
        self.leaves: dict[str, Scalar] = {}


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
    lineage: Lineage


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

    def import_leaves(self, leaves: dict[str, Scalar], lineage: Lineage) -> None:
        """Mark the theatre imported and record one event per leaf, all in one save and one change."""
        aggregate = TheatreConfig()
        tag = _lineage_kwargs(lineage)
        for path, value in leaves.items():
            aggregate.trigger_event(TheatreConfig.Imported, path=path, new=value, **tag)
        self.app.save(aggregate)

    def record(self, changes: Iterable[Change], lineage: Lineage) -> None:
        """Record `changes` in one save, all as part of the one change `lineage` describes."""
        aggregate = self._get()
        assert aggregate is not None, "theatre must be imported first"
        tag = _lineage_kwargs(lineage)
        for c in changes:
            if c.op == "set":
                aggregate.trigger_event(TheatreConfig.LeafSet, path=c.path, old=c.old, new=c.new, **tag)
            elif c.op == "remove":
                aggregate.trigger_event(TheatreConfig.LeafRemoved, path=c.path, old=c.old, **tag)
            else:
                raise ValueError(c.op)
        self.app.save(aggregate)

    def history(self) -> Iterator[Record]:
        for domain_event in self.app.events.get(self.id):
            if not isinstance(domain_event, LeafEvent):
                continue
            op = _OPS[type(domain_event).__name__]
            old: Scalar = getattr(domain_event, "old", None)
            new: Scalar = getattr(domain_event, "new", None)
            change = Change(op, domain_event.path, old, new)
            yield Record(
                seq=_seq(domain_event.originator_version), change=change, lineage=domain_event.lineage
            )

    def projection(self) -> dict[str, Scalar]:
        aggregate = self._get()
        return dict(aggregate.leaves) if aggregate is not None else {}
