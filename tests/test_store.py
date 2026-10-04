import math
import os
from pathlib import Path

from troupe.lineage import UNKNOWN, Actor, Lineage, for_file, for_import
from troupe.store import Change, ConfigStore


def test_events_persist_across_store_instances(tmp_path: Path) -> None:
    ConfigStore(tmp_path).import_leaves({"a": 1, "b": "x"}, for_import())
    ConfigStore(tmp_path).record([Change("set", "a", 1, 2)], for_file())
    records = list(ConfigStore(tmp_path).history())
    assert [(r.seq, r.change) for r in records] == [
        (1, Change("import", "a", None, 1)),
        (2, Change("import", "b", None, "x")),
        (3, Change("set", "a", 1, 2)),
    ]


def test_projection_follows_the_events(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    store.import_leaves({"a": 1, "b": 2}, for_import())
    store.record([Change("remove", "b", 2, None), Change("set", "c", None, 3.5)], for_file())
    assert ConfigStore(tmp_path).projection() == {"a": 1, "c": 3.5}


def test_values_keep_their_types_through_storage(tmp_path: Path) -> None:
    ConfigStore(tmp_path).import_leaves(
        {"i": 1, "f": 1.0, "b": True, "n": None, "s": "é\n", "inf": math.inf}, for_import()
    )
    new = {r.change.path: r.change.new for r in ConfigStore(tmp_path).history()}
    assert [type(v) for v in new.values()] == [int, float, bool, type(None), str, float]
    assert new["s"] == "é\n" and new["inf"] == math.inf


def test_store_is_not_imported_until_import(tmp_path: Path) -> None:
    assert not ConfigStore(tmp_path).is_imported()
    ConfigStore(tmp_path).import_leaves({}, for_import())
    assert ConfigStore(tmp_path).is_imported()


def test_store_does_not_change_the_process_environment(tmp_path: Path) -> None:
    before = dict(os.environ)
    ConfigStore(tmp_path).import_leaves({"a": 1}, for_import())
    assert dict(os.environ) == before


def test_lineage_round_trips_through_storage_with_nulls_and_empty_strings(tmp_path: Path) -> None:
    imported = Lineage(UNKNOWN, "import", "2026-01-02T03:04:05.000006Z", None, "c-import")
    no_login = Lineage(Actor("human", None), "cli", "2026-01-02T03:04:06.000000Z", "", "c-1")
    agent = Lineage(Actor("agent", "a:1"), "cli", "2026-01-02T03:04:07.123456Z", "é\nwhy", "c-2")
    ConfigStore(tmp_path).import_leaves({"a": 1}, imported)
    ConfigStore(tmp_path).record([Change("set", "a", 1, 2)], no_login)
    ConfigStore(tmp_path).record([Change("remove", "a", 2, None)], agent)
    assert [r.lineage for r in ConfigStore(tmp_path).history()] == [imported, no_login, agent]


def test_every_event_of_one_save_has_the_lineage_given(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    store.import_leaves({"a": 1, "b": 2}, imported := for_import())
    store.record([Change("remove", "a", 1, None), Change("set", "c", None, 3)], recorded := for_file())
    assert [r.lineage for r in ConfigStore(tmp_path).history()] == [imported, imported, recorded, recorded]
