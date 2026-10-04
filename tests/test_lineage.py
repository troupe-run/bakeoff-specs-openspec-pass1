"""Lineage through the real CLI (config-lineage), on real theatres."""

import calendar
import re
import time
from collections.abc import Callable
from typing import Any

import pytest
from test_history import events

from conftest import TEST_LOGIN, Result, Theatre

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
UNKNOWN = {"kind": "unknown", "id": None}
LINEAGE_KEYS = ("actor", "via", "at", "reason", "change")


def history(t: Theatre) -> list[dict[str, Any]]:
    return events(t.run("history"))


def last(t: Theatre) -> dict[str, Any]:
    return history(t)[-1]


def as_seconds(stamp: str) -> float:
    """An `at` value read as UTC."""
    whole = calendar.timegm(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S"))
    return whole + float("0" + stamp[19:-1])


@pytest.fixture
def actor(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def _set(value: str) -> None:
        monkeypatch.setenv("TROUPE_ACTOR", value)

    return _set


# --- the fields ----------------------------------------------------------------------------------------------


def test_imported_event_has_unknown_actor_import_via_no_reason_and_a_utc_timestamp(
    make: Callable[[str], Theatre],
) -> None:
    [e] = history(make("a: 1\n"))
    assert (e["actor"], e["via"], e["reason"]) == (UNKNOWN, "import", None)
    assert isinstance(e["change"], str) and e["change"]
    assert TIMESTAMP.match(e["at"]), e["at"]


def test_at_is_the_utc_time_of_the_change_whatever_the_local_zone(
    make: Callable[[str], Theatre], monkeypatch: pytest.MonkeyPatch
) -> None:
    t = make("a: 1\n")
    t.run("history")
    monkeypatch.setenv("TZ", "Asia/Tokyo")  # UTC+9: a local-time stamp would be 9 hours off
    time.tzset()
    try:
        before = time.time()
        assert t.run("set", "a", "2").code == 0
        after = time.time()
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
    stamp = last(t)["at"]
    assert TIMESTAMP.match(stamp), stamp
    assert before - 0.001 <= as_seconds(stamp) <= after + 0.001


# --- actor of a CLI command ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("agent:planner-7", {"kind": "agent", "id": "planner-7"}),
        ("human:alice", {"kind": "human", "id": "alice"}),
        ("agent:claude:session-1", {"kind": "agent", "id": "claude:session-1"}),
    ],
)
def test_set_records_the_actor_from_troupe_actor(
    make: Callable[[str], Theatre], actor: Callable[[str], None], value: str, expected: dict[str, Any]
) -> None:
    t = make("model: a\n")
    actor(value)
    assert t.run("set", "model", "b").code == 0
    e = last(t)
    assert (e["path"], e["actor"], e["via"]) == ("model", expected, "cli")


def test_unset_troupe_actor_is_the_human_logged_in(
    make: Callable[[str], Theatre], monkeypatch: pytest.MonkeyPatch
) -> None:
    t = make("model: a\n")
    assert t.run("set", "model", "b").code == 0
    assert last(t)["actor"] == {"kind": "human", "id": TEST_LOGIN}
    monkeypatch.setenv("LOGNAME", "bob")
    assert t.run("set", "model", "c").code == 0
    assert last(t)["actor"] == {"kind": "human", "id": "bob"}


@pytest.mark.parametrize("value", ["robot:x", "alice", "human:", "Human:alice", ""])
def test_invalid_troupe_actor_exits_2_changing_and_recording_nothing(
    make: Callable[[str], Theatre], monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    t = make("model: a\n")
    before_events = t.run("history").out
    t.write("troupe.yml", "model: hand\n")  # a pending hand edit must not be reconciled either
    snapshot = t.snapshot()
    monkeypatch.setenv("TROUPE_ACTOR", value)
    r = t.run("set", "model", "b")
    assert (r.code, r.out) == (2, "")
    assert "TROUPE_ACTOR" in r.err
    monkeypatch.delenv("TROUPE_ACTOR")
    assert t.snapshot() == snapshot
    assert t.run("history").out == before_events


@pytest.mark.parametrize("args", [("get", "a"), ("show",), ("history",), ("watch",)])
def test_invalid_troupe_actor_is_refused_by_every_command_before_anything_is_stored(
    make: Callable[[str], Theatre], actor: Callable[[str], None], args: tuple[str, ...]
) -> None:
    t = make("a: 1\n")
    actor("robot:x")
    r = t.run(*args)
    assert (r.code, r.out) == (2, "")
    assert "TROUPE_ACTOR" in r.err
    assert not (t.dir / "events.sqlite").exists()


# --- imports and hand edits ----------------------------------------------------------------------------------


def test_import_ignores_troupe_actor(make: Callable[[str], Theatre], actor: Callable[[str], None]) -> None:
    t = make("model: a\n")
    actor("agent:a1")
    assert t.run("set", "model", "b").code == 0
    assert [(e["op"], e["actor"], e["via"]) for e in history(t)] == [
        ("import", UNKNOWN, "import"),
        ("set", {"kind": "agent", "id": "a1"}, "cli"),
    ]


def test_hand_edit_picked_up_by_set_is_unknown_and_file_and_the_set_is_cli(
    make: Callable[[str], Theatre], actor: Callable[[str], None]
) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    actor("human:alice")
    assert t.run("set", "a", "3").code == 0
    assert [(e["old"], e["new"], e["actor"], e["via"]) for e in history(t)[1:]] == [
        (1, 2, UNKNOWN, "file"),
        (2, 3, {"kind": "human", "id": "alice"}, "cli"),
    ]


@pytest.mark.parametrize("args", [("get", "a"), ("show",)])
def test_hand_edit_picked_up_by_a_read_is_unknown_and_file(
    make: Callable[[str], Theatre], actor: Callable[[str], None], args: tuple[str, ...]
) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    actor("agent:reader")
    assert t.run(*args).code == 0
    e = last(t)
    assert (e["op"], e["new"], e["actor"], e["via"], e["reason"]) == ("set", 2, UNKNOWN, "file", None)


# --- reason --------------------------------------------------------------------------------------------------


def test_reason_is_on_every_event_of_the_set(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("set", "a", "{b: 2, c: 3}", "--reason", "split a").code == 0
    assert [(e["op"], e["path"], e["reason"]) for e in history(t)[1:]] == [
        ("remove", "a", "split a"),
        ("set", "a.b", "split a"),
        ("set", "a.c", "split a"),
    ]


def test_reason_is_null_without_reason(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    assert t.run("set", "model", "b").code == 0
    assert last(t)["reason"] is None


def test_empty_reason_is_recorded_as_an_empty_string(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    assert t.run("set", "model", "b", "--reason", "").code == 0
    assert last(t)["reason"] == ""


def test_reason_does_not_attach_to_reconciled_hand_edits(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nb: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\nb: 1\n")
    assert t.run("set", "b", "5", "--reason", "tune").code == 0
    assert [(e["path"], e["new"], e["reason"]) for e in history(t)[2:]] == [("a", 2, None), ("b", 5, "tune")]


def test_unicode_multi_line_reason_stays_on_one_json_line(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    assert t.run("set", "model", "b", "--reason", "é\nsecond line").code == 0
    out = t.run("history").out
    assert out.count("\n") == 2  # two events, so no raw newline inside a line
    assert last(t)["reason"] == "é\nsecond line"


def test_set_that_changes_nothing_records_nothing_even_with_a_reason(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    assert t.run("set", "model", "a", "--reason", "why").code == 0
    assert len(history(t)) == 1


# --- change grouping -----------------------------------------------------------------------------------------


def same_lineage(lines: list[dict[str, Any]]) -> bool:
    return len({tuple(str(e[k]) for k in LINEAGE_KEYS) for e in lines}) == 1


def test_one_set_is_one_change_distinct_from_the_import(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("set", "a", "{b: 2, c: 3}").code == 0
    imported, *own = history(t)
    assert len(own) == 3 and same_lineage(own)
    assert own[0]["change"] != imported["change"]


def test_two_commands_are_two_changes(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("set", "a", "2").code == 0
    assert t.run("set", "a", "3").code == 0
    first, second = history(t)[1:]
    assert first["change"] != second["change"]


def test_the_import_is_one_change_with_one_timestamp(make: Callable[[str], Theatre]) -> None:
    lines = history(make("a: 1\nb: [x, y]\n"))
    assert len(lines) == 3 and same_lineage(lines)


def test_a_reconcile_is_its_own_change(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nb: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\nb: 2\n")
    assert t.run("set", "c", "3").code == 0
    set_a, set_b, set_c = history(t)[2:]
    assert [e["path"] for e in (set_a, set_b, set_c)] == ["a", "b", "c"]
    assert same_lineage([set_a, set_b])
    assert set_c["change"] != set_a["change"]


def test_change_ids_differ_across_theatres(
    theatre: Theatre, run: Callable[..., Result], tmp_path_factory: pytest.TempPathFactory
) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    other = Theatre(tmp_path_factory.mktemp("other"), run)
    other.write("troupe.yml", "a: 1\n")
    assert history(theatre)[0]["change"] != history(other)[0]["change"]


# --- persistence ---------------------------------------------------------------------------------------------


def test_lineage_survives_restarts_and_does_not_depend_on_the_reader(
    make: Callable[[str], Theatre], actor: Callable[[str], None]
) -> None:
    t = make("model: a\n")
    actor("agent:a1")
    assert t.run("set", "model", "b", "--reason", "r").code == 0
    first = t.run("history").out
    actor("human:other")
    assert t.run("history").out == first
    e = events(t.run("history"))[-1]
    assert (e["actor"], e["via"], e["reason"]) == ({"kind": "agent", "id": "a1"}, "cli", "r")
