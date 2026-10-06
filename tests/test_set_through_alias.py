"""Setting a value reached through an alias is refused (config-set, "Refusing to set through an alias").

Each refusal checks that no file in the theatre changed, so a write through the anchor fails the test.
"""

import json
from collections.abc import Callable

import pytest

from conftest import Result, Theatre

SHARED = "defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n"


def cli_events(t: Theatre) -> list[dict[str, object]]:
    events = [json.loads(line) for line in t.run("history").out.splitlines()]
    return [e for e in events if e["via"] == "cli"]


def test_setting_one_user_of_a_shared_anchor_is_refused(make: Callable[[str], Theatre]) -> None:
    t = make(SHARED)
    before = t.snapshot()
    r = t.run("set", "coder.settings.model", "sonnet")
    assert (r.code, r.out) == (3, "")
    for text in ("coder.settings.model", "*d", "--expand-alias", "defaults.model"):
        assert text in r.err
    assert t.snapshot() == before
    assert cli_events(t) == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param("coder.settings", "{model: sonnet}", id="the-alias-itself"),
        pytest.param("coder.settings.temperature", "0.3", id="new-key-below-the-alias"),
        pytest.param("coder", "{settings: {model: sonnet}}", id="mapping-value-reaching-into-it"),
        pytest.param("coder", "{settings: {model: opus, extra: 1}}", id="mapping-value-adding-below-it"),
    ],
)
def test_writes_through_an_alias_are_refused(refused: Callable[..., Result], path: str, value: str) -> None:
    r = refused(SHARED, path, value)
    assert r.code == 3
    assert "*d" in r.err and "--expand-alias" in r.err


def test_alias_as_a_list_item_is_refused(refused: Callable[..., Result]) -> None:
    r = refused("d: &d {m: 1}\nl:\n  - *d\n", "l.0.m", "2")
    assert r.code == 3 and "l.0" in r.err


def test_unchanged_value_through_an_alias_changes_nothing(make: Callable[[str], Theatre]) -> None:
    t = make(SHARED)
    before = t.snapshot()
    mtime = (t.dir / "troupe.yml").stat().st_mtime_ns
    r = t.run("set", "coder.settings.model", "opus")
    assert (r.code, r.out, r.err) == (0, "", "")
    assert t.snapshot() == before
    assert (t.dir / "troupe.yml").stat().st_mtime_ns == mtime
    assert t.run("set", "coder", "{settings: {model: opus}}").code == 0
    assert t.snapshot() == before


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param(
            "defaults: &d\n  model: opus\ncoder:\n  settings: *d\n  model: x\n",
            "coder",
            "{model: x}",
            "defaults: &d\n  model: opus\ncoder:\n  model: x\n",
            id="remove-an-alias-entry",
        ),
        pytest.param(
            "d: &d {m: 1}\nl: {a: *d, b: 1}\n",
            "l",
            "{b: 1}",
            "d: &d {m: 1}\nl: {b: 1}\n",
            id="remove-in-flow",
        ),
        pytest.param(
            "d: &d\n  m: 1\nc:\n  k: x\n  s: *d\nz: 1\n",
            "c.t",
            "1",
            "d: &d\n  m: 1\nc:\n  k: x\n  s: *d\n  t: 1\nz: 1\n",
            id="new-key-after-an-alias-entry",
        ),
        pytest.param(
            "d: &d {m: 1}\nl: [*d]\n", "l.1", "2", "d: &d {m: 1}\nl: [*d, 2]\n", id="append-after-alias"
        ),
    ],
)
def test_writes_next_to_an_alias_are_allowed(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


def test_alias_inside_an_included_file_is_refused(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "d: &d {m: 1}\ns: *d\n")
    before = theatre.snapshot()
    for path, value in (("coder.s.m", "2"), ("coder.s.x", "1")):
        r = theatre.run("set", path, value)
        assert r.code == 3 and "coder.s" in r.err and "--expand-alias" in r.err
        assert theatre.snapshot() == before


def test_alias_in_the_included_layer_of_a_mapping_form_include_is_refused(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n  s:\n    x: 1\n")
    theatre.write("agents/coder.yaml", "d: &d {m: 1}\ns: *d\n")
    before = theatre.snapshot()
    for path, value in (("coder.s.m", "3"), ("coder.s.y", "2")):
        r = theatre.run("set", path, value)
        assert r.code == 3 and "*d" in r.err
        assert theatre.snapshot() == before
