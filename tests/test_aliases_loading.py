"""Loading anchors, aliases and merge keys (config-loading, "Anchors, aliases and merge keys")."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import Theatre
from troupe.loader import load
from troupe.tree import MappingNode

SHARED = "defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n"
MERGED = "base: &b\n  model: opus\n  temperature: 0.2\ncoder:\n  <<: *b\n  temperature: 0.5\n  top_p: 1\n"


def history(t: Theatre) -> list[dict[str, object]]:
    r = t.run("history")
    assert r.code == 0, r.err
    return [json.loads(line) for line in r.out.splitlines()]


def test_alias_of_an_anchored_mapping_has_its_value(make: Callable[[str], Theatre]) -> None:
    t = make(SHARED)
    assert t.run("get", "coder.settings.model").out == "opus\n"
    assert t.run("get", "reviewer.settings.model").out == "opus\n"
    assert t.run("show", "coder").out == "settings:\n  model: opus\n"


def test_alias_of_an_anchored_scalar_has_its_value(make: Callable[[str], Theatre]) -> None:
    assert make("a: &x 1\nb: *x\n").run("get", "b").out == "1\n"


def test_alias_of_a_quoted_scalar_with_space_after_the_anchor(make: Callable[[str], Theatre]) -> None:
    assert make('a: &x  "q r"\nb: *x\n').run("get", "b").out == "q r\n"


def test_merge_key_adds_entries_and_own_keys_win(make: Callable[[str], Theatre]) -> None:
    assert make(MERGED).run("show", "coder").out == "model: opus\ntemperature: 0.5\ntop_p: 1\n"


def test_merged_entries_take_the_merge_key_position(make: Callable[[str], Theatre]) -> None:
    t = make("base: &b {model: opus}\ncoder:\n  first: 1\n  <<: *b\n  last: 2\n")
    assert t.run("show", "coder").out == "first: 1\nmodel: opus\nlast: 2\n"


def test_merge_key_list_earlier_source_wins(make: Callable[[str], Theatre]) -> None:
    t = make("a: &a {x: 1, y: 1}\nb: &b {y: 2, z: 2}\nc:\n  <<: [*a, *b]\n")
    assert t.run("show", "c").out == "x: 1\ny: 1\nz: 2\n"


def test_merge_key_with_an_inline_mapping(make: Callable[[str], Theatre]) -> None:
    assert make("c:\n  <<: {x: 1}\n  y: 2\n").run("show", "c").out == "x: 1\ny: 2\n"


def test_quoted_merge_key_is_an_ordinary_key(make: Callable[[str], Theatre]) -> None:
    assert make('a: &a {x: 1}\nc:\n  "<<": *a\n').run("get", "c.<<.x").out == "1\n"


def test_import_records_aliased_values_at_every_path(make: Callable[[str], Theatre]) -> None:
    t = make("defaults: &d\n  model: opus\ncoder:\n  settings: *d\n")
    events = [(e["op"], e["path"], e["new"], e["via"]) for e in history(t)]
    assert events == [
        ("import", "defaults.model", "opus", "import"),
        ("import", "coder.settings.model", "opus", "import"),
    ]


def test_hand_edit_at_the_anchor_is_reconciled_at_every_alias(make: Callable[[str], Theatre]) -> None:
    t = make(SHARED)
    t.run("history")
    t.write("troupe.yml", SHARED.replace("opus", "sonnet"))
    assert t.run("get", "defaults.model").out == "sonnet\n"
    edits = [(e["path"], e["old"], e["new"]) for e in history(t) if e["via"] == "file"]
    assert edits == [
        ("defaults.model", "opus", "sonnet"),
        ("coder.settings.model", "opus", "sonnet"),
        ("reviewer.settings.model", "opus", "sonnet"),
    ]
    assert len({e["change"] for e in history(t) if e["via"] == "file"}) == 1


def test_anchored_include_is_expanded_once_and_shared(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: &x file:inc.yaml\nb: *x\n")
    theatre.write("inc.yaml", "k: 1\n")
    config = load(Path(theatre.root))
    assert isinstance(config.root, MappingNode)
    a, b = config.root.get("a"), config.root.get("b")
    assert a is not None and b is not None
    assert a.value is b.value
    assert theatre.run("show", "b", "--sources").out == "k: 1 # from .troupe/inc.yaml\n"


@pytest.mark.parametrize(
    "config",
    [
        pytest.param("a: *nothing\n", id="undefined-alias"),
        pytest.param("a: &a\n  b: *a\n", id="alias-inside-its-own-anchor"),
        pytest.param("c:\n  <<: 1\n", id="merge-key-with-a-scalar"),
        pytest.param("c:\n  <<: [1]\n", id="merge-key-with-a-list-of-scalars"),
        pytest.param("a: 1\n&k b: 2\n", id="anchored-key"),
        pytest.param("a: &k b\n*k : 2\n", id="alias-key"),
    ],
)
def test_bad_anchors_aliases_and_merge_keys_fail_to_load(make: Callable[[str], Theatre], config: str) -> None:
    t = make(config)
    for args in (("show",), ("get", "a"), ("history",), ("set", "z", "1")):
        r = t.run(*args)
        assert (r.code, r.out) == (4, ""), args
        assert "troupe.yml" in r.err


def test_merge_key_naming_an_include_fails_to_load(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: &x file:inc.yaml\nc:\n  <<: *x\n")
    theatre.write("inc.yaml", "k: 1\n")
    r = theatre.run("show")
    assert r.code == 4 and "troupe.yml" in r.err


def test_anchors_do_not_cross_files(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "shared: file:shared.yaml\ncoder: *d\n")
    theatre.write("shared.yaml", "&d {model: opus}\n")
    r = theatre.run("show")
    assert r.code == 4 and "troupe.yml" in r.err
