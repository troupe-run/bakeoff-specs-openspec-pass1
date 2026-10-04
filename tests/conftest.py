"""Shared fixtures: real theatres on disk and the real CLI entry point, run in-process."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from troupe.cli import main


@dataclass
class Result:
    code: int
    out: str
    err: str


class Theatre:
    """A theatre directory under tmp_path. File names are relative to `.troupe/`."""

    def __init__(self, root: Path, run: Callable[..., Result]) -> None:
        self.root = root
        self.dir = root / ".troupe"
        self._run = run

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def read(self, name: str) -> str:
        return (self.dir / name).read_bytes().decode("utf-8")

    def run(self, *args: str) -> Result:
        return self._run(*args, "--theatre", str(self.root))

    def snapshot(self) -> dict[str, bytes]:
        """Every file under the theatre (outside the event database), with its bytes."""
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in sorted(self.root.rglob("*"))
            if p.is_file() and not p.name.startswith("events.sqlite")
        }


TEST_LOGIN = "test-login"


@pytest.fixture(autouse=True)
def _known_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    """The developer's own TROUPE_ACTOR and login name must not change what the tests see."""
    monkeypatch.delenv("TROUPE_ACTOR", raising=False)
    monkeypatch.setenv("LOGNAME", TEST_LOGIN)
    monkeypatch.setenv("USER", TEST_LOGIN)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Result]:
    def _run(*args: str) -> Result:
        code = main(["config", *args])
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return _run


@pytest.fixture
def theatre(tmp_path: Path, run: Callable[..., Result]) -> Theatre:
    return Theatre(tmp_path, run)


@pytest.fixture
def make(theatre: Theatre) -> Callable[[str], Theatre]:
    """A theatre whose `troupe.yml` has the given text."""

    def _make(config: str) -> Theatre:
        theatre.write("troupe.yml", config)
        return theatre

    return _make


@pytest.fixture
def set_file(make: Callable[[str], Theatre]) -> Callable[..., str]:
    """Run `set` on a theatre whose troupe.yml is `before`; assert success and return the new file text."""

    def _set(before: str, path: str, value: str) -> str:
        t = make(before)
        r = t.run("set", path, value)
        assert (r.code, r.out, r.err) == (0, "", ""), r.err
        return t.read("troupe.yml")

    return _set


@pytest.fixture
def refused(make: Callable[[str], Theatre]) -> Callable[..., Result]:
    """Run `set` on a theatre whose troupe.yml is `before`; assert the file is unchanged."""

    def _refused(before: str, path: str, value: str) -> Result:
        t = make(before)
        snapshot = t.snapshot()
        r = t.run("set", path, value)
        assert r.code != 0 and r.out == ""
        assert t.snapshot() == snapshot
        return r

    return _refused


@pytest.fixture
def full(theatre: Theatre) -> Theatre:
    """The theatre from the config-show scenarios: a YAML include, a text include and a flow list."""
    theatre.write(
        "troupe.yml",
        "model: claude-opus-5-5\nagents:\n  coder: file:agents/coder.yaml\nprompt: file:prompt.md\n"
        "tools: [read, write]\n",
    )
    theatre.write("agents/coder.yaml", "model: m1\ntemperature: 0.2\n")
    theatre.write("prompt.md", "Hello\nWorld\n")
    return theatre
