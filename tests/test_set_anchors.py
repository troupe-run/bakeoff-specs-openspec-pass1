"""Setting a value defined at an anchor changes it there, for every alias (config-set, step 6)."""

import json
from collections.abc import Callable

import pytest

from conftest import Result, Theatre

SHARED = "defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n"


def test_changing_the_anchor_changes_every_alias(make: Callable[[str], Theatre]) -> None:
    t = make(SHARED)
    t.run("history")  # import first, so the events below are the set's own
    r = t.run("set", "defaults.model", "sonnet")
    assert (r.code, r.out, r.err) == (0, "", "")
    assert t.read("troupe.yml") == SHARED.replace("opus", "sonnet")
    assert t.run("get", "coder.settings.model").out == "sonnet\n"
    assert t.run("get", "reviewer.settings.model").out == "sonnet\n"
    events = [json.loads(line) for line in t.run("history").out.splitlines() if '"via": "cli"' in line]
    assert [(e["op"], e["path"], e["old"], e["new"]) for e in events] == [
        ("set", "defaults.model", "opus", "sonnet"),
        ("set", "coder.settings.model", "opus", "sonnet"),
        ("set", "reviewer.settings.model", "opus", "sonnet"),
    ]
    assert len({e["change"] for e in events}) == 1


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param("a: &x 1\nb: *x\n", "a", "2", "a: &x 2\nb: *x\n", id="anchored-scalar"),
        pytest.param('a: &x  "q"\nb: *x\n', "a", "r", 'a: &x  "r"\nb: *x\n', id="quoted-scalar"),
        pytest.param(
            "a: &x 1\nb: *x\n", "a", "[1, 2]", "a: &x\n  - 1\n  - 2\nb: *x\n", id="scalar-replaced-by-a-list"
        ),
        pytest.param(
            "a: &x\n  k: 1\nb: *x\n", "a", "5", "a: &x 5\nb: *x\n", id="block-mapping-replaced-by-a-scalar"
        ),
        pytest.param(
            "a: &x # c\n  k: 1\nb: *x\n", "a", "5", "a: &x 5 # c\nb: *x\n", id="block-mapping-with-comment"
        ),
        pytest.param("a: &x\nb: *x\n", "a", "3", "a: &x 3\nb: *x\n", id="anchored-null"),
        pytest.param(
            "a: &x {k: 1}\nb: *x\n", "a.j", "2", "a: &x {k: 1, j: 2}\nb: *x\n", id="new-key-in-flow"
        ),
        pytest.param(
            "a: &x\n  k: 1\nb: *x\n", "a.j", "2", "a: &x\n  k: 1\n  j: 2\nb: *x\n", id="new-key-in-block"
        ),
        pytest.param(
            "l:\n  - &x 1\n  - *x\n", "l.0", "[a]", "l:\n  - &x\n    - a\n  - *x\n", id="anchored-list-item"
        ),
    ],
)
def test_anchor_stays_in_front_of_the_new_value(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


def test_alias_sees_the_value_set_at_a_replaced_anchor(make: Callable[[str], Theatre]) -> None:
    t = make("a: &x 1\nb: *x\n")
    assert t.run("set", "a", "[1, 2]").code == 0
    assert t.run("show", "b").out == "- 1\n- 2\n"


def test_deleting_an_anchor_that_is_still_used_is_refused(refused: Callable[..., Result]) -> None:
    r = refused("c:\n  a: &x 1\n  k: 2\nb: *x\n", "c", "{k: 2}")
    assert r.code == 3
    assert "c:" in r.err


def test_deleting_an_unused_anchor_is_allowed(set_file: Callable[..., str]) -> None:
    assert set_file("c:\n  a: &x 1\n  k: 2\n", "c", "{k: 2}") == "c:\n  k: 2\n"
