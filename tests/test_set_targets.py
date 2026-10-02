"""Where `set` writes, and when it refuses: path resolution, includes, verification."""

import os
from collections.abc import Callable

import pytest

from conftest import Result, Theatre


def test_existing_value_changes_only_its_bytes(set_file: Callable[..., str]) -> None:
    before = "# top\nmodel:   'a'   # pick\nother: 1\n"
    assert set_file(before, "model", "b") == "# top\nmodel:   'b'   # pick\nother: 1\n"


def test_noop_set_leaves_the_file_and_its_mtime_alone(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    path = t.dir / "troupe.yml"
    os.utime(path, (1_000_000, 1_000_000))
    r = t.run("set", "model", "a")
    assert (r.code, r.out) == (0, "")
    assert path.stat().st_mtime == 1_000_000
    assert t.read("troupe.yml") == "model: a\n"


def test_value_inside_an_included_file_changes_only_that_file(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml  # the coder\n")
    theatre.write("agents/coder.yaml", "model: m1   # pinned\ntemperature: 0.2\n")
    r = theatre.run("set", "agents.coder.model", "m2")
    assert r.code == 0, r.err
    assert theatre.read("troupe.yml") == "agents:\n  coder: file:agents/coder.yaml  # the coder\n"
    assert theatre.read("agents/coder.yaml") == "model: m2   # pinned\ntemperature: 0.2\n"


def test_new_key_inside_an_included_mapping_goes_into_that_file(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m\n")
    assert theatre.run("set", "agents.coder.temperature", "0.2").code == 0
    assert theatre.read("troupe.yml") == "agents:\n  coder: file:agents/coder.yaml\n"
    assert theatre.read("agents/coder.yaml") == "model: m\ntemperature: 0.2\n"


def test_text_include_content_becomes_value_exactly(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "prompt: file:prompt.md\n")
    theatre.write("prompt.md", "Old\n")
    assert theatre.run("set", "prompt", '"New\\ntext\\n"').code == 0
    assert theatre.read("prompt.md") == "New\ntext\n"
    assert theatre.read("troupe.yml") == "prompt: file:prompt.md\n"
    assert theatre.run("set", "prompt", '"no newline"').code == 0
    assert theatre.read("prompt.md") == "no newline"


def test_text_include_with_crlf_keeps_crlf(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "prompt: file:prompt.md\n")
    theatre.write("prompt.md", "a\r\nb\r\n")
    assert theatre.run("set", "prompt", '"x\\ny\\r\\nz\\n"').code == 0
    assert theatre.read("prompt.md") == "x\r\ny\r\nz\r\n"


@pytest.mark.parametrize("value", ["5", "{a: 1}", "[x]", "true", "null"])
def test_non_string_into_a_text_include_is_refused(theatre: Theatre, value: str) -> None:
    theatre.write("troupe.yml", "prompt: file:prompt.md\n")
    theatre.write("prompt.md", "x")
    snapshot = theatre.snapshot()
    r = theatre.run("set", "prompt", value)
    assert (r.code, r.out) == (3, "")
    assert "prompt" in r.err
    assert theatre.snapshot() == snapshot


def _with_coder(theatre: Theatre) -> Theatre:
    theatre.write(
        "troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n  other: 1\nlimit: file:limit.yaml\n"
    )
    theatre.write("agents/coder.yaml", "model: m\n")
    theatre.write("limit.yaml", "5\n")
    return theatre


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("agents.coder", "{model: x}"),
        ("agents.coder", "{model: m, extra: 1}"),
        ("agents.coder", "scalar"),
        ("limit", "6"),
        ("agents", "{coder: {model: x}, other: 1}"),
        ("agents", "{other: 1}"),
        ("agents", "x"),
    ],
)
def test_replacing_or_deleting_a_yaml_include_is_refused(theatre: Theatre, path: str, value: str) -> None:
    t = _with_coder(theatre)
    snapshot = t.snapshot()
    r = t.run("set", path, value)
    assert (r.code, r.out) == (3, "")
    assert path in r.err
    assert t.snapshot() == snapshot


def test_ancestor_set_that_leaves_the_include_equal_is_allowed(theatre: Theatre) -> None:
    t = _with_coder(theatre)
    assert t.run("set", "agents", "{coder: {model: m}, other: 2}").code == 0
    assert (
        t.read("troupe.yml")
        == "agents:\n  coder: file:agents/coder.yaml\n  other: 2\nlimit: file:limit.yaml\n"
    )
    assert t.read("agents/coder.yaml") == "model: m\n"


def test_setting_an_include_to_its_own_string_is_a_noop(theatre: Theatre) -> None:
    t = _with_coder(theatre)
    snapshot = t.snapshot()
    assert t.run("set", "agents.coder", "file:agents/coder.yaml").code == 0
    assert t.snapshot() == snapshot


def test_new_string_value_starting_file_becomes_an_include(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    theatre.write("p.md", "hello\n")
    assert theatre.run("set", "prompt", "file:p.md").code == 0
    assert theatre.read("troupe.yml") == "a: 1\nprompt: file:p.md\n"
    assert theatre.run("show", "prompt").out == "hello\n"


def test_include_value_to_a_missing_file_is_refused(refused: Callable[..., Result]) -> None:
    r = refused("a: 1\n", "prompt", "file:nope.md")
    assert r.code == 3 and "prompt" in r.err


@pytest.mark.parametrize(
    ("before", "path"),
    [
        ("model: m\n", "model.x"),
        ("agents:\n", "agents.coder"),
        ("a: {}\n", "a.b.0"),
        ("a: {}\n", "a.0"),
        ("tools:\n  - a\n  - b\n", "tools.3"),
        ("tools: [a]\n", "tools.x"),
        ("tools: [a]\n", "tools.1.name"),
    ],
)
def test_impossible_paths_exit_5_and_change_nothing(
    refused: Callable[..., Result], before: str, path: str
) -> None:
    r = refused(before, path, "1")
    assert r.code == 5
    assert path in r.err


def test_descending_into_a_text_include_exits_5(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "p: file:p.md\n")
    theatre.write("p.md", "x")
    assert theatre.run("set", "p.x", "1").code == 5


def test_unloadable_configuration_exits_4_on_set(make: Callable[[str], Theatre]) -> None:
    t = make("a: [\n")
    assert t.run("set", "a", "1").code == 4


def test_edit_that_does_not_read_back_as_intended_is_refused(
    make: Callable[[str], Theatre], monkeypatch: pytest.MonkeyPatch
) -> None:
    from troupe.edit import ops
    from troupe.edit.text import Edit

    def wrong_edit(slot: ops.Slot, value: object, where: str) -> ops.FileEdits:
        return slot.node.file, [Edit(slot.node.start, slot.node.end, "not-what-was-asked")]

    monkeypatch.setattr(ops, "replace", wrong_edit)
    t = make("a: x\n")
    snapshot = t.snapshot()
    r = t.run("set", "a", "y")
    assert (r.code, r.out) == (3, "")
    assert "a" in r.err
    assert t.snapshot() == snapshot
