"""`set --expand-alias`: give one user of an anchor its own copy (config-set, "Expanding an alias on request").

Each test checks the whole file byte for byte, and that the result loads with the intended values.
"""

import json
from collections.abc import Callable

import pytest

from conftest import Theatre

SHARED = "defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n"


def expand(t: Theatre, *args: str) -> str:
    r = t.run("set", "--expand-alias", *args)
    assert (r.code, r.out, r.err) == (0, "", ""), r.err
    return t.read("troupe.yml")


def test_giving_one_agent_its_own_copy(make: Callable[[str], Theatre]) -> None:
    t = make(SHARED)
    t.run("history")
    assert expand(t, "coder.settings.model", "sonnet") == (
        "defaults: &d\n  model: opus\ncoder:\n  settings:  # expanded from *d by troupe\n    model: sonnet\n"
        "reviewer:\n  settings: *d\n"
    )
    assert t.run("get", "coder.settings.model").out == "sonnet\n"
    assert t.run("get", "reviewer.settings.model").out == "opus\n"
    assert t.run("get", "defaults.model").out == "opus\n"
    events = [json.loads(line) for line in t.run("history").out.splitlines()]
    assert [(e["op"], e["path"], e["old"], e["new"]) for e in events if e["via"] == "cli"] == [
        ("set", "coder.settings.model", "opus", "sonnet")
    ]


@pytest.mark.parametrize(
    ("before", "args", "after"),
    [
        pytest.param(
            "a: &x 1\nb: *x\n", ("b", "2"), "a: &x 1\nb: 2  # expanded from *x by troupe\n", id="scalar-alias"
        ),
        pytest.param(
            "d: &d {model: 'opus', limits: {tokens: 0x10}}\nc: *d\n",
            ("c.limits.calls", "5"),
            "d: &d {model: 'opus', limits: {tokens: 0x10}}\nc:  # expanded from *d by troupe\n  model: 'opus'\n"
            "  limits:\n    tokens: 0x10\n    calls: 5\n",
            id="copy-keeps-written-text-in-block-style",
        ),
        pytest.param(
            "t: &t [read]\nd: &d\n  model: opus\n  tools: *t\nc: *d\n",
            ("c.model", "sonnet"),
            "t: &t [read]\nd: &d\n  model: opus\n  tools: *t\nc:  # expanded from *d by troupe\n  model: sonnet\n"
            "  tools: *t\n",
            id="nested-aliases-stay-aliases",
        ),
        pytest.param(
            "t: &t\n  - read\nd: &d\n  tools: *t\nc: *d\n",
            ("c.tools.1", "write"),
            "t: &t\n  - read\nd: &d\n  tools: *t\nc:  # expanded from *d by troupe\n"
            "  tools:  # expanded from *t by troupe\n    - read\n    - write\n",
            id="nested-alias-on-the-way-is-expanded-too",
        ),
        pytest.param(
            "d: &d\n  model: opus\nc: *d  # shared\n",
            ("c.model", "sonnet"),
            "d: &d\n  model: opus\nc:  # shared  # expanded from *d by troupe\n  model: sonnet\n",
            id="existing-comment-is-kept",
        ),
        pytest.param(
            "d: &d\n  model: opus\nagents:\n  - *d\n  - *d\n",
            ("agents.0.model", "sonnet"),
            "d: &d\n  model: opus\nagents:\n  -  # expanded from *d by troupe\n    model: sonnet\n  - *d\n",
            id="alias-as-a-list-item",
        ),
        pytest.param(
            SHARED,
            ("coder", "{settings: {model: sonnet}}"),
            "defaults: &d\n  model: opus\ncoder:\n  settings:  # expanded from *d by troupe\n    model: sonnet\n"
            "reviewer:\n  settings: *d\n",
            id="mapping-value-reaching-into-an-alias",
        ),
        pytest.param(
            "d: &d\n  model: opus\n  tags: [a, b]\n  list:\n  - x\n  - k: 1\n    j: 2\nc: *d\n",
            ("c.model", "sonnet"),
            "d: &d\n  model: opus\n  tags: [a, b]\n  list:\n  - x\n  - k: 1\n    j: 2\n"
            "c:  # expanded from *d by troupe\n  model: sonnet\n  tags:\n  - a\n  - b\n  list:\n  - x\n  - k: 1\n"
            "    j: 2\n",
            id="lists-follow-the-file-layout",
        ),
        pytest.param(
            "d: &d {a: {}, b: []}\nc: *d\n",
            ("c.z", "1"),
            "d: &d {a: {}, b: []}\nc:  # expanded from *d by troupe\n  a: {}\n  b: []\n  z: 1\n",
            id="empty-collections",
        ),
        pytest.param(
            "d: &d\n  p: |\n    line one\n    line two\n  k: 1\nc: *d\n",
            ("c.k", "2"),
            "d: &d\n  p: |\n    line one\n    line two\n  k: 1\nc:  # expanded from *d by troupe\n  p: |\n"
            "    line one\n    line two\n  k: 2\n",
            id="multi-line-scalar",
        ),
        pytest.param(
            "d: &d\n  m: &m 1\n  n: *m\nc: *d\n",
            ("c.n", "2"),
            "d: &d\n  m: &m 1\n  n: *m\nc:  # expanded from *d by troupe\n  m: 1\n  n: 2  # expanded from *m by troupe\n",
            id="anchors-inside-the-copy-are-not-copied",
        ),
        pytest.param(
            "a: &x\n  k: 1\nb:\n  *x\n",
            ("b.k", "2"),
            "a: &x\n  k: 1\nb:  # expanded from *x by troupe\n  k: 2\n",
            id="alias-below-its-key",
        ),
        pytest.param("a:\n  b: 1\n", ("a.b", "2"), "a:\n  b: 2\n", id="nothing-to-expand"),
    ],
)
def test_expansion(make: Callable[[str], Theatre], before: str, args: tuple[str, ...], after: str) -> None:
    assert expand(make(before), *args) == after


def test_expanded_files_read_back_as_intended(make: Callable[[str], Theatre]) -> None:
    t = make("t: &t\n  - read\nd: &d\n  tools: *t\nc: *d\n")
    expand(t, "c.tools.1", "write")
    assert (
        t.run("show").out == "t:\n  - read\nd:\n  tools:\n    - read\nc:\n  tools:\n    - read\n    - write\n"
    )


def test_unchanged_value_expands_nothing(make: Callable[[str], Theatre]) -> None:
    t = make("d: &d\n  model: opus\nc: *d\n")
    before = t.snapshot()
    expand(t, "c.model", "opus")
    assert t.snapshot() == before


def test_alias_in_a_flow_collection_is_not_expanded(make: Callable[[str], Theatre]) -> None:
    t = make("d: &d {model: opus}\nc: {settings: *d}\n")
    before = t.snapshot()
    r = t.run("set", "--expand-alias", "c.settings.model", "sonnet")
    assert (r.code, r.out) == (3, "")
    assert "*d" in r.err and "flow" in r.err
    assert t.snapshot() == before


def test_copy_that_would_hold_a_merge_key_is_refused(make: Callable[[str], Theatre]) -> None:
    t = make("b: &b {m: 1}\nd: &d\n  <<: *b\n  k: 1\nc: *d\n")
    before = t.snapshot()
    r = t.run("set", "--expand-alias", "c.k", "2")
    assert (r.code, r.out) == (3, "")
    assert "<<" in r.err and "*d" in r.err
    assert t.snapshot() == before


def test_anchored_include_string_is_copied_as_the_include(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: &x file:inc.yaml\nb: *x\n")
    theatre.write("inc.yaml", "k: 1\n")
    expand(theatre, "b.j", "2")
    assert theatre.read("troupe.yml") == (
        "a: &x file:inc.yaml\nb:  # expanded from *x by troupe\n  $ref: file:inc.yaml\n  j: 2\n"
    )
    assert theatre.read("inc.yaml") == "k: 1\n"
    assert theatre.run("show", "a").out == "k: 1\n"


def test_crlf_file(make: Callable[[str], Theatre]) -> None:
    t = make("d: &d\r\n  model: opus\r\nc: *d\r\n")
    assert expand(t, "c.model", "sonnet") == (
        "d: &d\r\n  model: opus\r\nc:  # expanded from *d by troupe\r\n  model: sonnet\r\n"
    )
