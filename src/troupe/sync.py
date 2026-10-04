"""Reconciling: bringing the recorded configuration (the event projection) in line with the files."""

from troupe import lineage
from troupe.leaves import diff_leaves, leaves
from troupe.loader import Config
from troupe.store import Change, ConfigStore
from troupe.tree import to_data


def reconcile(config: Config, store: ConfigStore) -> list[Change]:
    """Record a `remove`/`set` event for each leaf where the loaded files differ from the projection.

    The events are saved in one atomic save, as one change made through the files by an unknown actor;
    nothing is saved when nothing differs.
    """
    changes = diff_leaves(store.projection(), leaves(to_data(config.root)))
    if changes:
        store.record(changes, lineage.for_file())
    return changes
