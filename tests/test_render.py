"""`show` output reads back as the same data, with and without sources (config-show: Show collections as YAML)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import Theatre
from troupe.loader import load
from troupe.render import render, source_label
from troupe.schema import same
from troupe.source import SourceFile
from troupe.tree import build_tree, to_data

CONFIGS = {
    "multi-line strings": 'a: "x\\ny"\nb: "x\\ny\\n"\nc: "x\\ny\\n\\n"\nd: "\\n"\ne: "\\n\\nx\\n"\n',
    "leading spaces": 'a: "  indented\\nnext\\n"\nb: "\\n  after blank\\n"\nc: " lead"\nd: "trail "\n',
    "carriage returns and controls": 'a: "x\\r\\ny\\n"\nb: "bell\\a"\nc: "tab\\tin"\nd: "line\\ttab\\n"\n',
    "special floats": "a: .nan\nb: -.inf\nc: .inf\nd: 1e3\ne: -0.0\nf: 0x1F\ng: 0o17\n",
    "strings that look like other things": (
        "a: 'true'\nb: '0.2'\nc: '- x'\nd: '#x'\ne: 'a: b'\nf: ''\ng: 'null'\nh: '~'\ni: \"it's\"\n"
        "j: '[x]'\nk: '{x}'\nl: '---'\nm: '@x'\nn: 'x #y'\no: ' '\np: '\"q\"'\nq: '-'\nr: '?'\n"
    ),
    "keys that need quoting": "'true': 1\n'1': 2\n'a: b': 3\n'#k': 4\n'': 5\n",
    "nested lists and mappings": (
        "a:\n  - - x\n    - - y\n      - []\n  - {b: {c: [1, {d: e}]}}\n  - {}\n  - - {f: g, h: [i]}\n"
    ),
    "unicode": '名前: 値\nemoji: 🎭\nnbsp: "a\\u00a0b"\n',
    "empty collections": "a: {}\nb: []\nc: [{}, []]\n",
    "nulls and booleans": "a:\nb: ~\nc: TRUE\nd: False\n",
}


def read_back(text: str) -> object:
    root = build_tree(SourceFile(Path("<show>"), text))
    assert root is not None
    return to_data(root)


def assert_round_trips(theatre: Theatre) -> None:
    config = load(theatre.root)
    expected = to_data(config.root)
    for sources in (False, True):
        out = render(config.root, theatre.root, sources=sources)
        assert same(read_back(out), expected), out  # type: ignore[arg-type]


@pytest.mark.parametrize("config", CONFIGS.values(), ids=CONFIGS.keys())
def test_show_output_reads_back_as_the_same_data(make: Callable[[str], Theatre], config: str) -> None:
    assert_round_trips(make(config))


@pytest.mark.parametrize(
    "text",
    [
        "Hello\nWorld\n",
        "no newline",
        "",
        "\n",
        "two\n\n",
        "  indented\n",
        "crlf\r\nline\r\n",
        "tab\there\n",
        "ü\n",
    ],
)
def test_text_includes_read_back_exactly(theatre: Theatre, text: str) -> None:
    theatre.write("troupe.yml", "p: file:p.txt\nl: [file:p.txt]\n")
    theatre.write("p.txt", text)
    assert_round_trips(theatre)


def test_includes_are_resolved_in_the_output(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\nl:\n  - file:item.yaml\n")
    theatre.write("agents/coder.yaml", "model: m1\nprompt: file:../p.md\n")
    theatre.write("item.yaml", "[x, y]\n")
    theatre.write("p.md", "be brief\n")
    out = render(load(theatre.root).root, theatre.root, sources=False)
    assert "file:" not in out
    assert_round_trips(theatre)


# --- source_label -------------------------------------------------------------------------------------------


def src(path: Path) -> SourceFile:
    return SourceFile(path, "")


def test_source_label_of_the_config_file(tmp_path: Path) -> None:
    assert source_label(src(tmp_path / ".troupe" / "troupe.yml"), tmp_path) == ".troupe/troupe.yml"


def test_source_label_of_a_nested_include(tmp_path: Path) -> None:
    label = source_label(src(tmp_path / ".troupe" / "agents" / "coder.yaml"), tmp_path)
    assert label == ".troupe/agents/coder.yaml"


def test_source_label_removes_parent_segments(tmp_path: Path) -> None:
    label = source_label(src(tmp_path / ".troupe" / "sub" / ".." / "b.yaml"), tmp_path)
    assert label == ".troupe/b.yaml"


def test_source_label_of_a_file_outside_the_theatre(tmp_path: Path) -> None:
    theatre = tmp_path / "t"
    assert source_label(src(theatre / ".troupe" / ".." / ".." / "shared.yaml"), theatre) == "../shared.yaml"


def test_source_label_with_a_relative_theatre(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert source_label(src(Path("t") / ".troupe" / "troupe.yml"), Path("t")) == ".troupe/troupe.yml"
