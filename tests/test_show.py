from collections.abc import Callable

import pytest

from conftest import Theatre


def test_show_prints_a_plain_scalar(make: Callable[[str], Theatre]) -> None:
    r = make("model: claude-opus-5-5\n").run("show", "model")
    assert (r.code, r.out, r.err) == (0, "claude-opus-5-5\n", "")


@pytest.mark.parametrize(
    ("yaml", "printed"),
    [
        ("v: hi\n", "hi\n"),
        ('v: "hi\\n"\n', "hi\n"),
        ("v: |\n  a\n  b\n", "a\nb\n"),
        ("v: |-\n  a\n  b\n", "a\nb\n"),
        ("v: true\n", "true\n"),
        ("v: ~\n", "null\n"),
        ("v:\n", "null\n"),
        ("v: 0x1F\n", "31\n"),
        ("v: 0.2\n", "0.2\n"),
        ("v: .inf\n", "inf\n"),
        ("v: 1e3\n", "1000.0\n"),
        ("v: '0.2'\n", "0.2\n"),
        ("v: >\n  folded\n  text\n", "folded text\n"),
    ],
)
def test_show_prints_each_scalar_type_per_contract(
    make: Callable[[str], Theatre], yaml: str, printed: str
) -> None:
    assert make(yaml).run("show", "v").out == printed


def test_show_follows_yaml_includes(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "temperature: 0.2\n")
    assert theatre.run("show", "agents.coder.temperature").out == "0.2\n"


def test_show_prints_a_text_include_as_a_string(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "p: file:p.txt\n")
    theatre.write("p.txt", "no newline")
    assert theatre.run("show", "p").out == "no newline\n"


def test_show_indexes_lists(make: Callable[[str], Theatre]) -> None:
    t = make("tools: [a, b]\nnested:\n  - - x\n    - y\n")
    assert t.run("show", "tools.1").out == "b\n"
    assert t.run("show", "nested.0.1").out == "y\n"


def test_show_sees_hand_edits(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    assert t.run("show", "model").out == "a\n"
    t.write("troupe.yml", "model: b\n")
    assert t.run("show", "model").out == "b\n"


@pytest.mark.parametrize("path", ["agents", "tools", "agents.coder"])
def test_show_of_a_collection_exits_5_naming_the_path(make: Callable[[str], Theatre], path: str) -> None:
    r = make("agents:\n  coder: {model: m}\ntools: [a]\n").run("show", path)
    assert (r.code, r.out) == (5, "")
    assert path in r.err


@pytest.mark.parametrize("path", ["nope", "agents.nobody", "tools.5", "tools.x", "model.x", "model.0"])
def test_show_of_a_missing_path_exits_5_naming_it(make: Callable[[str], Theatre], path: str) -> None:
    r = make("agents: {}\ntools: [a]\nmodel: m\n").run("show", path)
    assert (r.code, r.out) == (5, "")
    assert path in r.err
