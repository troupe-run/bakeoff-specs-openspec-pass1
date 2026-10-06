from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import Theatre
from troupe.errors import LoadError
from troupe.loader import load
from troupe.tree import to_data


def test_troupe_yaml_extension_is_found(theatre: Theatre) -> None:
    theatre.write("troupe.yaml", "model: x\n")
    assert theatre.run("show", "model").out == "x\n"


def test_both_config_files_present_exits_4_naming_both(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    theatre.write("troupe.yaml", "a: 1\n")
    for args in (("show", "a"), ("set", "a", "2"), ("history",)):
        r = theatre.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "troupe.yml" in r.err and "troupe.yaml" in r.err


def test_missing_config_file_exits_4_naming_it_and_creates_nothing(theatre: Theatre) -> None:
    theatre.root.mkdir(exist_ok=True)
    for args in (("show", "a"), ("set", "a", "1"), ("history",)):
        r = theatre.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "troupe.yml" in r.err
    assert list(theatre.root.iterdir()) == []


def test_files_load_with_the_core_schema(make: Callable[[str], Theatre]) -> None:
    t = make("a: yes\nb: 2001-01-01\nc: 0o17\nd: on\n")
    assert t.run("show", "a").out == "yes\n"
    assert t.run("show", "b").out == "2001-01-01\n"
    assert t.run("show", "c").out == "15\n"
    assert t.run("show", "d").out == "on\n"


def test_invalid_yaml_exits_4_naming_the_file(make: Callable[[str], Theatre]) -> None:
    t = make("a: [1, 2\n")
    for args in (("show", "a"), ("history",)):
        r = t.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "troupe.yml" in r.err


def test_invalid_utf8_exits_4(theatre: Theatre) -> None:
    (theatre.dir).mkdir(parents=True)
    (theatre.dir / "troupe.yml").write_bytes(b"a: \xff\n")
    r = theatre.run("show", "a")
    assert r.code == 4 and "troupe.yml" in r.err


@pytest.mark.parametrize("text", ["", "# only a comment\n"])
def test_empty_file_is_an_empty_mapping(make: Callable[[str], Theatre], text: str) -> None:
    t = make(text)
    assert (t.run("history").code, t.run("history").out) == (0, "")
    assert t.run("show", "a").code == 5


def test_yaml_include_is_embedded(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m1\n")
    assert theatre.run("show", "agents.coder.model").out == "m1\n"


def test_quoted_include_strings_are_includes_too(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: 'file:x.yml'\nb: \"file:x.yml\"\n")
    theatre.write("x.yml", "v: 1\n")
    assert theatre.run("show", "a.v").out == "1\n"
    assert theatre.run("show", "b.v").out == "1\n"


def test_text_include_is_the_exact_file_text(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "prompt: file:prompt.md\n")
    theatre.write("prompt.md", "Hello\r\nWorld\n\n")
    assert theatre.run("show", "prompt").out == "Hello\r\nWorld\n\n"


def test_nested_include_is_relative_to_its_own_file(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "prompt: file:coder.md\n")
    theatre.write("agents/coder.md", "be brief")
    assert theatre.run("show", "agents.coder.prompt").out == "be brief\n"


def test_missing_include_target_exits_4_naming_it(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: file:nope.yaml\n")
    for args in (("show", "a"), ("history",), ("set", "b", "1")):
        r = theatre.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "nope.yaml" in r.err
    assert not (theatre.dir / "events.sqlite").exists()


def test_invalid_yaml_creates_no_state(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: [1\n")
    for args in (("show", "a"), ("set", "a", "1"), ("history",)):
        assert theatre.run(*args).code == 4
    assert sorted(p.name for p in theatre.dir.iterdir()) == ["troupe.yml"]


def test_include_cycle_exits_4(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: file:a.yaml\n")
    theatre.write("a.yaml", "b: file:b.yaml\n")
    theatre.write("b.yaml", "a: file:a.yaml\n")
    r = theatre.run("show", "a.b.a")
    assert (r.code, r.out) == (4, "")
    assert "a.yaml" in r.err and "cycle" in r.err


def test_self_include_of_the_main_file_is_a_cycle(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: file:troupe.yml\n")
    assert theatre.run("history").code == 4


def test_same_file_included_twice_is_not_a_cycle(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: file:common.yaml\nb: file:common.yaml\n")
    theatre.write("common.yaml", "x: 1\n")
    assert theatre.run("show", "a.x").out == "1\n"
    assert theatre.run("show", "b.x").out == "1\n"


def test_duplicate_keys_are_refused_at_load(make: Callable[[str], Theatre]) -> None:
    assert make("a: 1\na: 2\n").run("show", "a").code == 4


def test_load_reads_overlay_text_instead_of_disk(theatre: Theatre) -> None:
    path = theatre.write("troupe.yml", "a: 1\n")
    config = load(theatre.root, overlay={path.resolve(): "a: 2\n"})
    assert to_data(config.root) == {"a": 2}


def test_directory_as_include_target_is_a_load_error(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: file:sub\n")
    (theatre.dir / "sub").mkdir()
    with pytest.raises(LoadError):
        load(Path(theatre.root))
