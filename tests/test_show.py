"""`show [PATH]`: a scalar as `get` prints it, anything else as block YAML (config-show)."""

from collections.abc import Callable

import pytest

from conftest import Theatre

WHOLE = (
    "model: claude-opus-5-5\n"
    "agents:\n"
    "  coder:\n"
    "    model: m1\n"
    "    temperature: 0.2\n"
    "prompt: |\n"
    "  Hello\n"
    "  World\n"
    "tools:\n"
    "  - read\n"
    "  - write\n"
)


def test_show_without_path_prints_the_whole_configuration_with_includes_resolved(full: Theatre) -> None:
    r = full.run("show")
    assert (r.code, r.out, r.err) == (0, WHOLE, "")


def test_show_of_a_section_prints_it_as_yaml(full: Theatre) -> None:
    r = full.run("show", "agents")
    assert (r.code, r.out, r.err) == (0, "coder:\n  model: m1\n  temperature: 0.2\n", "")


def test_show_of_a_list_prints_block_items(full: Theatre) -> None:
    assert full.run("show", "tools").out == "- read\n- write\n"


def test_show_of_a_list_of_mappings_uses_compact_items(make: Callable[[str], Theatre]) -> None:
    out = make("steps:\n  - {name: a, n: 1}\n  - name: b\n").run("show", "steps").out
    assert out == "- name: a\n  n: 1\n- name: b\n"


def test_show_writes_nested_lists_compactly(make: Callable[[str], Theatre]) -> None:
    out = make("a: [[x, y], [], [{b: c}]]\n").run("show").out
    assert out == "a:\n  - - x\n    - y\n  - []\n  - - b: c\n"


def test_show_writes_a_one_line_text_include_as_a_literal_block(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "p: file:p.txt\n")
    theatre.write("p.txt", "no newline")
    assert theatre.run("show").out == "p: |-\n  no newline\n"


def test_show_writes_other_multi_line_strings_as_literal_blocks(make: Callable[[str], Theatre]) -> None:
    out = make('a: "x\\ny\\n\\n"\nl: ["one\\ntwo"]\n').run("show").out
    assert out == "a: |+\n  x\n  y\n\nl:\n  - |-\n    one\n    two\n"


def test_show_double_quotes_a_text_include_a_literal_block_cannot_hold(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "p: file:p.txt\n")
    theatre.write("p.txt", "crlf\r\n")
    assert theatre.run("show").out == 'p: "crlf\\r\\n"\n'


def test_show_quotes_strings_that_would_read_back_as_something_else(make: Callable[[str], Theatre]) -> None:
    out = make('a: "true"\nb: \'0.2\'\nc: ""\nd: "x: y"\n').run("show").out
    assert out == "a: 'true'\nb: '0.2'\nc: ''\nd: 'x: y'\n"


def test_show_writes_scalars_in_canonical_form_keeping_their_types(make: Callable[[str], Theatre]) -> None:
    out = make("a: 0x1F\nb: 1e3\nc: ~\nd: .inf\ne: TRUE\n").run("show").out
    assert out == "a: 31\nb: 1000.0\nc: null\nd: .inf\ne: true\n"


def test_show_writes_empty_collections_in_flow_form(make: Callable[[str], Theatre]) -> None:
    assert make("agents: {}\ntools: []\n").run("show").out == "agents: {}\ntools: []\n"


@pytest.mark.parametrize("config", ["", "# only a comment\n"])
def test_show_of_an_empty_configuration_prints_an_empty_mapping(
    make: Callable[[str], Theatre], config: str
) -> None:
    r = make(config).run("show")
    assert (r.code, r.out, r.err) == (0, "{}\n", "")


def test_show_keeps_the_files_key_order(make: Callable[[str], Theatre]) -> None:
    assert make("z: 1\na: 2\nm: {y: 3, b: 4}\n").run("show").out == "z: 1\na: 2\nm:\n  y: 3\n  b: 4\n"


@pytest.mark.parametrize("path", ["model", "prompt", "agents.coder.temperature", "tools.1"])
def test_show_of_a_scalar_prints_what_get_prints(full: Theatre, path: str) -> None:
    shown, got = full.run("show", path), full.run("get", path)
    assert (shown.code, shown.out, shown.err) == (got.code, got.out, got.err)
    assert shown.code == 0


def test_show_of_a_text_include_prints_its_text(full: Theatre) -> None:
    assert full.run("show", "prompt").out == "Hello\nWorld\n"


def test_show_sees_hand_edits(make: Callable[[str], Theatre]) -> None:
    t = make("model: a\n")
    assert t.run("show").out == "model: a\n"
    t.write("troupe.yml", "model: b\n")
    assert t.run("show", "model").out == "b\n"
    assert t.run("show").out == "model: b\n"


@pytest.mark.parametrize("path", ["nope", "agents.nobody", "tools.5", "tools.x", "model.x", "model.0"])
def test_show_of_a_missing_path_exits_5_naming_it(make: Callable[[str], Theatre], path: str) -> None:
    for args in (("show", path), ("show", path, "--sources")):
        r = make("agents: {}\ntools: [a]\nmodel: m\n").run(*args)
        assert (r.code, r.out) == (5, "")
        assert path in r.err
