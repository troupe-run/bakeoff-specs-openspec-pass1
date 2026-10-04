import json
from collections.abc import Callable
from typing import Any

from conftest import Result, Theatre


def events(r: Result) -> list[dict[str, Any]]:
    assert r.code == 0, r.err
    return [json.loads(line) for line in r.out.splitlines()]


def brief(r: Result) -> list[tuple[Any, ...]]:
    return [(e["seq"], e["op"], e["path"], e["old"], e["new"]) for e in events(r)]


def test_first_history_imports_one_event_per_leaf(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nb: [x, y]\n")
    assert brief(t.run("history")) == [
        (1, "import", "a", None, 1),
        (2, "import", "b.0", None, "x"),
        (3, "import", "b.1", None, "y"),
    ]


def test_import_happens_once(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    first = t.run("history").out
    assert t.run("history").out == first
    assert t.run("show", "a").code == 0
    assert t.run("history").out == first


def test_any_command_imports_even_if_it_then_fails(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("show", "nope").code == 5
    assert brief(t.run("history")) == [(1, "import", "a", None, 1)]


def test_hand_edits_are_not_imported(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run("show", "a").code == 0
    assert brief(t.run("history")) == [(1, "import", "a", None, 1), (2, "set", "a", 1, 2)]


def test_set_records_old_value_from_the_files(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\n")
    assert t.run("set", "a", "3").code == 0
    assert brief(t.run("history"))[1:] == [(2, "set", "a", 1, 2), (3, "set", "a", 2, 3)]


def test_set_records_one_event_for_a_changed_scalar(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    t.run("set", "model", "b")
    assert brief(t.run("history")) == [(1, "import", "model", None, "a"), (2, "set", "model", "a", "b")]


def test_scalar_replaced_by_mapping_records_remove_then_sets(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("set", "a", "{b: 2, c: 3}").code == 0
    assert brief(t.run("history"))[1:] == [
        (2, "remove", "a", 1, None),
        (3, "set", "a.b", None, 2),
        (4, "set", "a.c", None, 3),
    ]


def test_unchanged_leaves_are_not_recorded(make: Callable[[str], Theatre]) -> None:
    t = make("a:\n  b: 1\n  c: 2\n")
    assert t.run("set", "a", "{b: 1, c: 5}").code == 0
    assert brief(t.run("history"))[2:] == [(3, "set", "a.c", 2, 5)]


def test_noop_set_records_nothing(make: Callable[[str], Theatre]) -> None:
    t = make("a: x\n")
    assert t.run("set", "a", "x").code == 0
    assert len(events(t.run("history"))) == 1


def test_refused_set_records_nothing(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:coder.yaml\n")
    theatre.write("coder.yaml", "model: m\n")
    assert theatre.run("set", "agents.coder", "{model: x}").code == 3
    assert [e["op"] for e in events(theatre.run("history"))] == ["import"]


def test_history_path_filters_by_exact_path_or_dotted_prefix(make: Callable[[str], Theatre]) -> None:
    t = make("agents:\n  coder:\n    model: m\n  coderx: 1\nmodel: z\n")
    assert [e["path"] for e in events(t.run("history", "agents.coder"))] == ["agents.coder.model"]
    assert [e["path"] for e in events(t.run("history", "model"))] == ["model"]
    assert [e["seq"] for e in events(t.run("history", "agents.coderx"))] == [2]


def test_history_path_matching_nothing_prints_nothing(make: Callable[[str], Theatre]) -> None:
    r = make("a: 1\n").run("history", "zzz")
    assert (r.code, r.out) == (0, "")


def test_history_lines_are_compact_json_with_unicode_and_escaped_newlines(
    make: Callable[[str], Theatre],
) -> None:
    t = make('a: "é\\n"\n')
    r = t.run("history")
    assert r.out.count("\n") == 1
    assert json.loads(r.out)["new"] == "é\n"


def test_non_finite_floats_are_json_strings(make: Callable[[str], Theatre]) -> None:
    t = make("a: .inf\nb: -.inf\nc: .nan\n")
    assert [e["new"] for e in events(t.run("history"))] == [".inf", "-.inf", ".nan"]


def test_text_include_leaf_is_its_text(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "p: file:p.md\n")
    theatre.write("p.md", "hi\n")
    assert brief(theatre.run("history")) == [(1, "import", "p", None, "hi\n")]


def test_usage_error_creates_no_state(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    assert t.run("show", "a..b").code == 2
    assert t.run("set", "a", "[x").code == 2
    assert not (t.dir / "events.sqlite").exists()


HISTORY_KEYS = ["seq", "op", "path", "old", "new", "actor", "via", "at", "reason", "change"]


def test_every_history_line_carries_lineage_with_or_without_a_path(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\nb: 1\n")
    t.run("history")
    t.write("troupe.yml", "a: 2\nb: 1\n")
    assert t.run("set", "b", "3", "--reason", "r").code == 0
    everything = events(t.run("history"))
    assert [e["via"] for e in everything] == ["import", "import", "file", "cli"]
    assert all(list(e) == HISTORY_KEYS for e in everything)
    filtered = events(t.run("history", "b"))
    assert filtered == [e for e in everything if e["path"] == "b"]
