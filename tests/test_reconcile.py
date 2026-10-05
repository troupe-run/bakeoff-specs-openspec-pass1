"""Reconciling the recorded configuration with the files (config-sync: Reconcile)."""

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_history import events

from conftest import Theatre
from troupe.leaves import leaves
from troupe.lineage import for_import
from troupe.loader import load
from troupe.store import Change, ConfigStore
from troupe.sync import reconcile
from troupe.tree import to_data


def write(theatre: Path, text: str, name: str = "troupe.yml") -> None:
    path = theatre / ".troupe" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def imported(theatre: Path, text: str) -> ConfigStore:
    """A theatre whose files are `text`, imported into a fresh store."""
    write(theatre, text)
    store = ConfigStore(theatre / ".troupe")
    store.import_leaves(leaves(to_data(load(theatre).root)), for_import())
    return store


def recorded(store: ConfigStore) -> list[Change]:
    return [r.change for r in store.history() if r.change.op != "import"]


# --- reconcile() itself --------------------------------------------------------------------------


def test_reconcile_records_nothing_when_the_files_match(tmp_path: Path) -> None:
    store = imported(tmp_path, "a: 1\nb: [x, y]\n")
    assert reconcile(load(tmp_path), store) == []
    assert recorded(store) == []


def test_reconcile_lists_removes_in_recorded_order_then_sets_in_document_order(tmp_path: Path) -> None:
    store = imported(tmp_path, "a: 1\nb: 2\nc: 3\nd: 4\n")
    write(tmp_path, "z: 9\nd: 5\ny: 8\nb: 2\n")
    expected = [
        Change("remove", "a", 1, None),
        Change("remove", "c", 3, None),
        Change("set", "z", None, 9),
        Change("set", "d", 4, 5),
        Change("set", "y", None, 8),
    ]
    assert reconcile(load(tmp_path), store) == expected
    assert recorded(ConfigStore(tmp_path / ".troupe")) == expected


def test_reconcile_saves_its_events_so_the_projection_matches_the_files(tmp_path: Path) -> None:
    store = imported(tmp_path, "a: 1\n")
    write(tmp_path, "a: 2\nb: x\n")
    reconcile(load(tmp_path), store)
    assert ConfigStore(tmp_path / ".troupe").projection() == {"a": 2, "b": "x"}
    assert reconcile(load(tmp_path), store) == []


def test_values_round_trip_through_storage_so_reconcile_after_import_records_nothing(tmp_path: Path) -> None:
    store = imported(
        tmp_path,
        "i: 1\nf: 1.0\nb: true\ns: '1'\nn: null\ninf: .inf\nninf: -.inf\nnan: .nan\nm: |\n  two\n  lines\n",
    )
    projection = ConfigStore(tmp_path / ".troupe").projection()
    assert [type(v) for v in projection.values()] == [
        int,
        float,
        bool,
        str,
        type(None),
        float,
        float,
        float,
        str,
    ]
    assert projection["inf"] == math.inf and projection["ninf"] == -math.inf
    assert math.isnan(projection["nan"])  # type: ignore[arg-type]
    assert projection["m"] == "two\nlines\n"
    assert reconcile(load(tmp_path), ConfigStore(tmp_path / ".troupe")) == []
    assert recorded(store) == []


# --- through the CLI: a hand edit made while nothing runs is reconciled by the next command ---------------


def added(t: Theatre, before: int) -> list[tuple[Any, ...]]:
    """The events after the first `before` ones, as (op, path, old, new)."""
    return [(e["op"], e["path"], e["old"], e["new"]) for e in events(t.run("history"))[before:]]


def test_hand_edit_becomes_a_set_event(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("history").code == 0
    t.write("troupe.yml", "a: 2\n")
    assert t.run("show", "a").out == "2\n"
    assert added(t, 1) == [("set", "a", 1, 2)]


def test_removed_and_added_leaves_become_remove_then_set(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nb: 2\n")
    t.run("history")
    t.write("troupe.yml", "b: 2\nc: [x]\n")
    t.run("show", "b")
    assert added(t, 2) == [("remove", "a", 1, None), ("set", "c.0", None, "x")]


def test_scalar_replaced_by_a_mapping_by_hand(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a:\n  b: 2\n")
    t.run("show", "a.b")
    assert added(t, 1) == [("remove", "a", 1, None), ("set", "a.b", None, 2)]


def test_type_change_by_hand_is_a_change(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: '1'\n")
    t.run("show", "a")
    assert added(t, 1) == [("set", "a", 1, "1")]


def test_formatting_and_comment_only_edits_record_nothing(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nb: x\n")
    t.run("history")
    t.write("troupe.yml", '# note\nb:   "x"   # c\na: 1\n')
    assert t.run("show", "a").code == 0
    assert added(t, 2) == []


def test_edit_inside_an_included_text_file_is_reconciled(make: Callable[[str], Theatre]) -> None:
    t = make("prompt: file:prompt.md\n")
    t.write("prompt.md", "Hi\n")
    t.run("history")
    t.write("prompt.md", "Bye\n")
    t.run("show", "prompt")
    assert added(t, 1) == [("set", "prompt", "Hi\n", "Bye\n")]


# --- which commands reconcile first (config-sync: Commands reconcile first) ------------------------------


def test_set_after_a_hand_edit_records_the_reconcile_event_then_its_own(
    make: Callable[[str], Theatre],
) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run("set", "a", "3").code == 0
    assert added(t, 1) == [("set", "a", 1, 2), ("set", "a", 2, 3)]


def test_reconcile_persists_when_the_command_then_fails(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run("show", "nope").code == 5
    assert added(t, 1) == [("set", "a", 1, 2)]


@pytest.mark.parametrize("command", [("get", "a"), ("show", "a"), ("show",), ("show", "--sources")])
def test_get_and_show_reconcile_a_hand_edit_once(
    make: Callable[[str], Theatre], command: tuple[str, ...]
) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run(*command).code == 0
    assert t.run(*command).code == 0
    assert added(t, 1) == [("set", "a", 1, 2)]


def test_reconcile_persists_when_get_then_fails(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run("get", "nope").code == 5
    assert added(t, 1) == [("set", "a", 1, 2)]


def test_reconcile_persists_when_set_is_refused(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nprompt: file:p.md\n")
    t.write("p.md", "x\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\nprompt: file:p.md\n")
    assert t.run("set", "prompt", "5").code == 3
    assert added(t, 2) == [("set", "a", 1, 2)]


def test_history_does_not_reconcile_but_a_later_show_does(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert added(t, 1) == []
    assert added(t, 1) == []
    t.run("show", "a")
    assert added(t, 1) == [("set", "a", 1, 2)]


def test_invalid_command_line_records_nothing(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run("set", "a", "[x").code == 2
    assert t.run("show", "a..b").code == 2
    assert added(t, 1) == []


def test_unloadable_configuration_records_nothing(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: [2\n")
    assert t.run("show", "a").code == 4
    assert t.run("set", "a", "3").code == 4
    t.write("troupe.yml", "a: 1\n")
    assert added(t, 1) == []


# --- mapping-form includes ---------------------------------------------------------------------------------


def test_override_added_by_hand_is_recorded_as_a_file_edit(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "temperature: 0.2\n")
    theatre.run("history")
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n")
    assert theatre.run("get", "coder.temperature").out == "0.3\n"
    new = events(theatre.run("history"))[1:]
    assert [(e["op"], e["path"], e["old"], e["new"], e["via"]) for e in new] == [
        ("set", "coder.temperature", 0.2, 0.3, "file")
    ]


def test_converting_an_include_to_mapping_form_records_nothing(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "temperature: 0.2\n")
    theatre.run("history")
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n")
    assert theatre.run("show").code == 0
    assert added(theatre, 1) == []


def test_set_of_a_new_override_records_one_cli_event(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m\n")
    assert theatre.run("set", "coder.temperature", "0.3").code == 0
    new = events(theatre.run("history"))[1:]
    assert [(e["op"], e["path"], e["old"], e["new"], e["via"]) for e in new] == [
        ("set", "coder.temperature", None, 0.3, "cli")
    ]


def test_set_after_a_hand_added_override_changes_the_override_and_records_both(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "temperature: 0.2\n")
    theatre.run("history")
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n  extra: 1\n")
    assert theatre.run("set", "coder.extra", "2").code == 0
    assert theatre.read("agents/coder.yaml") == "temperature: 0.2\n"
    assert added(theatre, 1) == [("set", "coder.extra", None, 1), ("set", "coder.extra", 1, 2)]
