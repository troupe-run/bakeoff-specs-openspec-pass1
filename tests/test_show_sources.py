"""`show [PATH] --sources`: the same YAML, each scalar's line naming the file it comes from (config-show)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from test_render import read_back

from conftest import Result, Theatre
from troupe.loader import load
from troupe.tree import to_data

T = " # from .troupe/troupe.yml"
C = " # from .troupe/agents/coder.yaml"
WHOLE = (
    f"model: claude-opus-5-5{T}\n"
    "agents:\n"
    "  coder:\n"
    f"    model: m1{C}\n"
    f"    temperature: 0.2{C}\n"
    "prompt: | # from .troupe/prompt.md\n"
    "  Hello\n"
    "  World\n"
    "tools:\n"
    f"  - read{T}\n"
    f"  - write{T}\n"
)


def test_sources_name_each_scalars_file_across_includes(full: Theatre) -> None:
    r = full.run("show", "--sources")
    assert (r.code, r.out, r.err) == (0, WHOLE, "")


def test_sources_output_is_show_output_plus_comments(full: Theatre) -> None:
    plain = full.run("show").out.splitlines()
    commented = full.run("show", "--sources").out.splitlines()
    assert [line.split(" # from ")[0] for line in commented] == plain


def test_sources_output_reads_back_as_the_same_data(full: Theatre) -> None:
    assert read_back(full.run("show", "--sources").out) == to_data(load(full.root).root)


def test_sources_for_a_section(full: Theatre) -> None:
    assert full.run("show", "agents.coder", "--sources").out == f"model: m1{C}\ntemperature: 0.2{C}\n"


@pytest.mark.parametrize(
    "args", [("show", "--sources", "agents.coder"), ("show", "agents.coder", "--sources")]
)
def test_sources_flag_may_come_before_or_after_the_path(full: Theatre, args: tuple[str, ...]) -> None:
    assert full.run(*args).out == f"model: m1{C}\ntemperature: 0.2{C}\n"


def test_sources_for_a_scalar_print_it_as_yaml_with_the_comment(full: Theatre) -> None:
    assert full.run("show", "model", "--sources").out == f"claude-opus-5-5{T}\n"


def test_sources_for_a_text_include_name_the_included_file(full: Theatre) -> None:
    assert full.run("show", "prompt", "--sources").out == "| # from .troupe/prompt.md\n  Hello\n  World\n"


def test_sources_for_a_quoted_string_scalar(make: Callable[[str], Theatre]) -> None:
    assert make("a: 'true'\n").run("show", "a", "--sources").out == f"'true'{T}\n"


def test_sources_for_an_empty_included_yaml_file(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "")
    assert theatre.run("show", "agents", "--sources").out == f"coder: null{C}\n"


def test_sources_normalise_an_include_through_a_parent_directory(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: file:sub/a.yaml\n")
    theatre.write("sub/a.yaml", "b: file:../b.yaml\n")
    theatre.write("b.yaml", "c: 1\n")
    assert theatre.run("show", "--sources").out == "a:\n  b:\n    c: 1 # from .troupe/b.yaml\n"


def test_sources_name_troupe_yaml_when_that_is_the_config_file(theatre: Theatre) -> None:
    theatre.write("troupe.yaml", "a: 1\n")
    assert theatre.run("show", "--sources").out == "a: 1 # from .troupe/troupe.yaml\n"


def test_sources_put_no_comment_on_empty_collections(make: Callable[[str], Theatre]) -> None:
    assert make("a: {}\nb: []\nc: [x]\n").run("show", "--sources").out == f"a: {{}}\nb: []\nc:\n  - x{T}\n"


def test_sources_with_a_relative_theatre(
    theatre: Theatre, monkeypatch: pytest.MonkeyPatch, run: Callable[..., Result]
) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    monkeypatch.chdir(theatre.root.parent)
    r = run("show", "--sources", "--theatre", Path(theatre.root.name).as_posix())
    assert r.out == f"a: 1{T}\n"


def test_sources_name_the_overriding_file_for_overridden_values(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n")
    theatre.write("agents/coder.yaml", "model: m1\ntemperature: 0.2\n")
    r = theatre.run("show", "--sources")
    assert (r.code, r.err) == (0, "")
    assert r.out == (
        "coder:\n  model: m1 # from .troupe/agents/coder.yaml\n  temperature: 0.3 # from .troupe/troupe.yml\n"
    )
