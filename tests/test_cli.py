from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import Result, Theatre


def test_theatre_defaults_to_the_current_directory(
    make: Callable[[str], Theatre], run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    t = make("model: x\n")
    monkeypatch.chdir(t.root)
    r = run("show", "model")
    assert (r.code, r.out) == (0, "x\n")


def test_theatre_defaults_to_troupe_theatre_but_the_option_wins(
    tmp_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    env, opt = Theatre(tmp_path / "env", run), Theatre(tmp_path / "opt", run)
    env.write("troupe.yml", "model: env\n")
    opt.write("troupe.yml", "model: opt\n")
    monkeypatch.setenv("TROUPE_THEATRE", str(env.root))
    assert run("show", "model").out == "env\n"
    assert run("--theatre", str(opt.root), "show", "model").out == "opt\n"
    monkeypatch.setenv("TROUPE_THEATRE", "")
    monkeypatch.chdir(opt.root)
    assert run("show", "model").out == "opt\n"


def test_theatre_option_may_come_before_the_subcommand(
    make: Callable[[str], Theatre], run: Callable[..., Result]
) -> None:
    t = make("model: x\n")
    assert run("--theatre", str(t.root), "show", "model").out == "x\n"


@pytest.mark.parametrize(
    "args",
    [
        ("frobnicate",),
        ("set", "model"),
        ("get",),
        ("get", "a", "b"),
        ("show", "a", "b"),
        ("get", "a", "--sources"),
        ("set", "model", "b", "--reason"),
        ("get", "model", "--reason", "x"),
        ("set", "model", "b", "--in-include", "x"),
        ("get", "model", "--in-include"),
    ],
)
def test_bad_command_lines_exit_2_with_empty_stdout(
    make: Callable[[str], Theatre], args: tuple[str, ...]
) -> None:
    r = make("model: x\n").run(*args)
    assert (r.code, r.out) == (2, "")
    assert r.err


@pytest.mark.parametrize(
    "args",
    [("set", "model", "b", "--reason", "why"), ("set", "--reason", "why", "model", "b")],
)
def test_set_takes_an_optional_reason_before_or_after_path_and_value(
    make: Callable[[str], Theatre], args: tuple[str, ...]
) -> None:
    t = make("model: x\n")
    r = t.run(*args)
    assert (r.code, r.out, r.err) == (0, "", "")
    assert t.read("troupe.yml") == "model: b\n"


@pytest.mark.parametrize(
    "args",
    [
        ("set", "a.x", "1", "--in-include"),
        ("set", "--in-include", "a.x", "1", "--reason", "why"),
        ("set", "--reason", "why", "a.x", "1", "--in-include"),
    ],
)
def test_set_takes_an_optional_in_include_anywhere(
    make: Callable[[str], Theatre], args: tuple[str, ...]
) -> None:
    t = make("a:\n  b: 1\n")
    r = t.run(*args)
    assert (r.code, r.out, r.err) == (0, "", "")
    assert t.read("troupe.yml") == "a:\n  b: 1\n  x: 1\n"


@pytest.mark.parametrize("args", [("show",), ("show", "--sources")])
def test_show_takes_an_optional_path(make: Callable[[str], Theatre], args: tuple[str, ...]) -> None:
    r = make("model: x\n").run(*args)
    assert r.code == 0
    assert r.out.startswith("model: x")


def test_bad_path_syntax_exits_2_naming_the_path(make: Callable[[str], Theatre]) -> None:
    r = make("a: 1\n").run("show", "a..b")
    assert (r.code, r.out) == (2, "")
    assert "a..b" in r.err


def test_bad_value_exits_2_naming_the_value_and_changes_nothing(make: Callable[[str], Theatre]) -> None:
    t = make("model: x\n")
    r = t.run("set", "model", "[a, b")
    assert (r.code, r.out) == (2, "")
    assert "[a, b" in r.err
    assert t.read("troupe.yml") == "model: x\n"


def test_read_commands_leave_every_user_file_untouched(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a: 1  # c\np: file:p.md\nx: file:x.yaml\n")
    theatre.write("p.md", "text\r\n")
    theatre.write("x.yaml", "k: v\n")
    (theatre.root / "outside.txt").write_text("o")
    before = theatre.snapshot()
    for args in (
        ("get", "a"),
        ("show", "a"),
        ("show",),
        ("show", "--sources"),
        ("history",),
        ("show", "nope"),
    ):
        theatre.run(*args)
    assert theatre.snapshot() == before
    new = {p.name for p in theatre.root.rglob("*")} - {Path(k).name for k in before} - {"agents", ".troupe"}
    assert all(name.startswith("events.sqlite") for name in new)
    assert all(p.parent == theatre.dir for p in theatre.root.rglob("events.sqlite*"))


def test_failures_print_only_to_stderr(make: Callable[[str], Theatre]) -> None:
    r = make("agents: {a: 1}\n").run("show", "agents.nobody")
    assert (r.code, r.out) == (5, "")
    assert "agents.nobody" in r.err
