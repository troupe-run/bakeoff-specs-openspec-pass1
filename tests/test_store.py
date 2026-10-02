import math
import os
from pathlib import Path

from troupe.store import Change, ConfigStore


def test_events_persist_across_store_instances(tmp_path: Path) -> None:
    ConfigStore(tmp_path).import_leaves({"a": 1, "b": "x"})
    ConfigStore(tmp_path).record([Change("set", "a", 1, 2)])
    records = list(ConfigStore(tmp_path).history())
    assert [(r.seq, r.change) for r in records] == [
        (1, Change("import", "a", None, 1)),
        (2, Change("import", "b", None, "x")),
        (3, Change("set", "a", 1, 2)),
    ]


def test_projection_follows_the_events(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    store.import_leaves({"a": 1, "b": 2})
    store.record([Change("remove", "b", 2, None), Change("set", "c", None, 3.5)])
    assert ConfigStore(tmp_path).projection() == {"a": 1, "c": 3.5}


def test_values_keep_their_types_through_storage(tmp_path: Path) -> None:
    ConfigStore(tmp_path).import_leaves({"i": 1, "f": 1.0, "b": True, "n": None, "s": "é\n", "inf": math.inf})
    new = {r.change.path: r.change.new for r in ConfigStore(tmp_path).history()}
    assert [type(v) for v in new.values()] == [int, float, bool, type(None), str, float]
    assert new["s"] == "é\n" and new["inf"] == math.inf


def test_store_is_not_imported_until_import(tmp_path: Path) -> None:
    assert not ConfigStore(tmp_path).is_imported()
    ConfigStore(tmp_path).import_leaves({})
    assert ConfigStore(tmp_path).is_imported()


def test_store_does_not_change_the_process_environment(tmp_path: Path) -> None:
    before = dict(os.environ)
    ConfigStore(tmp_path).import_leaves({"a": 1})
    assert dict(os.environ) == before
