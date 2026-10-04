"""`troupe config watch`, run as a real process (config-sync: Watch command and the requirements after it)."""

import fcntl
import os
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from test_history import events

from conftest import Theatre
from troupe.store import ConfigStore

DEADLINE = 2.0  # the contract: reconciled within 2 seconds of a change
QUIET = 2.5  # how long to wait before concluding that nothing was recorded
STARTUP_TIMEOUT = 30.0


class Watch:
    """A running `watch` process on a theatre."""

    def __init__(self, t: Theatre) -> None:
        self.t = t
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "troupe.cli", "config", "watch", "--theatre", str(t.root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self.proc.stdout is not None
        self.line = _readline(self.proc.stdout, STARTUP_TIMEOUT)

    def stop(self, signum: int = signal.SIGTERM) -> tuple[int, str, str]:
        self.proc.send_signal(signum)
        out, err = self.proc.communicate(timeout=10)
        return self.proc.returncode, self.line + out.decode(), err.decode()

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.communicate()


def _readline(stream: Any, timeout: float) -> str:
    """Read one line from a pipe, failing the test rather than hanging if it does not come."""
    selector = selectors.DefaultSelector()
    selector.register(stream, selectors.EVENT_READ)
    data = b""
    end = time.monotonic() + timeout
    while not data.endswith(b"\n"):
        if not selector.select(max(0.0, end - time.monotonic())):
            pytest.fail(f"no line from watch within {timeout}s (got {data!r})")
        chunk = os.read(stream.fileno(), 1)
        if not chunk:
            break
        data += chunk
    return data.decode()


@pytest.fixture
def watching(theatre: Theatre) -> Iterator[Callable[[], Watch]]:
    started: list[Watch] = []

    def _start() -> Watch:
        w = Watch(theatre)
        started.append(w)
        return w

    yield _start
    for w in started:
        w.kill()


def brief(t: Theatre) -> list[tuple[Any, ...]]:
    return [(e["op"], e["path"], e["old"], e["new"]) for e in events(t.run("history"))]


def recorded_within(t: Theatre, since: int, expected: list[tuple[Any, ...]], start: float) -> None:
    """Assert that the events after the first `since` become `expected` within DEADLINE of `start`."""
    while True:
        got = brief(t)[since:]
        if got == expected:
            assert time.monotonic() - start <= DEADLINE
            return
        if time.monotonic() - start > DEADLINE:
            pytest.fail(f"after {DEADLINE}s the new events are {got}, expected {expected}")
        time.sleep(0.05)


def nothing_recorded(t: Theatre, since: int) -> None:
    time.sleep(QUIET)
    assert brief(t)[since:] == []


# --- startup and stopping ----------------------------------------------------------------------------------


def test_watch_prints_the_ready_line_and_keeps_running(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    w = watching()
    assert w.line == f"watching {theatre.root}\n"
    time.sleep(0.5)
    assert w.proc.poll() is None


def test_watch_imports_and_reconciles_at_startup(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    theatre.run("history")
    theatre.write("troupe.yml", "a: 2\n")
    watching()
    assert brief(theatre) == [("import", "a", None, 1), ("set", "a", 1, 2)]


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_watch_exits_0_on_signal_with_only_the_ready_line(
    theatre: Theatre, watching: Callable[[], Watch], signum: int
) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    w = watching()
    assert w.stop(signum) == (0, f"watching {theatre.root}\n", "")


def test_watch_on_an_unloadable_theatre_exits_4_and_creates_nothing(theatre: Theatre) -> None:
    theatre.root.mkdir(exist_ok=True)
    r = subprocess.run(
        [sys.executable, "-m", "troupe.cli", "config", "watch", "--theatre", str(theatre.root)],
        capture_output=True,
        timeout=STARTUP_TIMEOUT,
        check=False,
    )
    assert (r.returncode, r.stdout) == (4, b"")
    assert b"troupe.yml" in r.stderr
    assert list(theatre.root.iterdir()) == []


# --- live edits --------------------------------------------------------------------------------------------


def test_live_edit_is_reconciled_within_2_seconds(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    watching()
    start = time.monotonic()
    theatre.write("troupe.yml", "a: 2\n")
    recorded_within(theatre, 1, [("set", "a", 1, 2)], start)


def test_edit_to_an_included_file_is_reconciled(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m1\n")
    watching()
    start = time.monotonic()
    theatre.write("agents/coder.yaml", "model: m2  # bigger\n")
    recorded_within(theatre, 1, [("set", "agents.coder.model", "m1", "m2")], start)


def test_save_by_rename_is_reconciled(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    watching()
    start = time.monotonic()
    theatre.write("troupe.yml.swp", "a: 2\n")
    os.replace(theatre.dir / "troupe.yml.swp", theatre.dir / "troupe.yml")
    recorded_within(theatre, 1, [("set", "a", 1, 2)], start)


def test_comment_only_live_edit_records_nothing(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "a: 1  # old\n")
    watching()
    theatre.write("troupe.yml", "# new heading\na:   1  # new\n")
    nothing_recorded(theatre, 1)


def test_watch_leaves_user_files_untouched(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "a: 1  # c\np: file:p.md\n")
    theatre.write("p.md", "text\r\n")
    w = watching()
    start = time.monotonic()
    theatre.write("p.md", "new\r\n")
    recorded_within(theatre, 2, [("set", "p", "text\r\n", "new\r\n")], start)
    expected = theatre.snapshot()
    assert w.stop()[0] == 0
    assert theatre.snapshot() == expected
    assert {p.name for p in theatre.dir.iterdir()} - {"troupe.yml", "p.md"} <= {
        "events.sqlite",
        "events.sqlite-journal",
        "events.sqlite-wal",
        "events.sqlite-shm",
    }


# --- configuration that does not load while watching ------------------------------------------------------


def test_broken_then_fixed_file_reports_once_and_reconciles_only_the_fix(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    w = watching()
    theatre.write("troupe.yml", "a: [1\n")
    time.sleep(1.5)
    assert w.proc.poll() is None
    start = time.monotonic()
    theatre.write("troupe.yml", "a: 2\n")
    recorded_within(theatre, 1, [("set", "a", 1, 2)], start)
    code, out, err = w.stop()
    assert (code, out) == (0, f"watching {theatre.root}\n")
    assert len(err.splitlines()) == 1 and "troupe.yml" in err


def test_missing_include_target_then_created(theatre: Theatre, watching: Callable[[], Watch]) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    w = watching()
    theatre.write("troupe.yml", "a: 1\np: file:p.md\n")
    time.sleep(1.0)
    start = time.monotonic()
    theatre.write("p.md", "hello\n")
    recorded_within(theatre, 1, [("set", "p", None, "hello\n")], start)
    _, _, err = w.stop()
    assert len(err.splitlines()) == 1 and "p.md" in err


# --- troupe's own write-backs ------------------------------------------------------------------------------


def test_set_while_watch_runs_adds_exactly_its_own_event(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "model: a\n")
    watching()
    assert theatre.run("set", "model", "b").code == 0
    time.sleep(QUIET)
    assert brief(theatre) == [("import", "model", None, "a"), ("set", "model", "a", "b")]


def test_watch_records_hand_edits_as_unknown_file_and_a_concurrent_set_as_its_own_actor(
    theatre: Theatre, watching: Callable[[], Watch], monkeypatch: pytest.MonkeyPatch
) -> None:
    theatre.write("troupe.yml", "a: 1\nb: 1\n")
    monkeypatch.setenv("TROUPE_ACTOR", "agent:w")  # watch's own actor must not be given to hand edits
    watching()
    start = time.monotonic()
    theatre.write("troupe.yml", "a: 2\nb: 1\n")
    recorded_within(theatre, 2, [("set", "a", 1, 2)], start)
    monkeypatch.setenv("TROUPE_ACTOR", "human:setter")
    assert theatre.run("set", "b", "5").code == 0
    lines = events(theatre.run("history"))[2:]
    assert [(e["path"], e["actor"], e["via"]) for e in lines] == [
        ("a", {"kind": "unknown", "id": None}, "file"),
        ("b", {"kind": "human", "id": "setter"}, "cli"),
    ]


def test_set_into_an_included_file_while_watch_runs_adds_exactly_its_own_event(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m1\n")
    watching()
    assert theatre.run("set", "agents.coder.model", "m2").code == 0
    time.sleep(QUIET)
    assert brief(theatre)[1:] == [("set", "agents.coder.model", "m1", "m2")]


def test_watch_reconciles_only_while_holding_the_theatre_lock(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    """A `set` holds the lock from reading the files until its events are saved, so watch never sees it half done."""
    theatre.write("troupe.yml", "a: 1\n")
    watching()
    fd = os.open(theatre.dir, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        theatre.write("troupe.yml", "a: 2\n")
        time.sleep(QUIET)
        # `history` would wait for the lock too, so read the store directly.
        assert [r.change.op for r in ConfigStore(theatre.dir).history()] == ["import"]
    finally:
        os.close(fd)
    recorded_within(theatre, 1, [("set", "a", 1, 2)], time.monotonic())


def test_hand_edit_after_a_set_while_watching_starts_from_the_set_value(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "model: a\n")
    watching()
    assert theatre.run("set", "model", "b").code == 0
    time.sleep(1.0)
    start = time.monotonic()
    theatre.write("troupe.yml", "model: c\n")
    recorded_within(theatre, 2, [("set", "model", "b", "c")], start)


# --- includes added by hand --------------------------------------------------------------------------------


def test_include_added_by_hand_is_followed_and_then_watched(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "agents: {}\n")
    theatre.write("agents/tester.yaml", "model: t1\n")
    watching()
    start = time.monotonic()
    theatre.write("troupe.yml", "agents:\n  tester: file:agents/tester.yaml\n")
    recorded_within(theatre, 0, [("set", "agents.tester.model", None, "t1")], start)
    start = time.monotonic()
    theatre.write("agents/tester.yaml", "model: t2\n")
    recorded_within(theatre, 1, [("set", "agents.tester.model", "t1", "t2")], start)


def test_include_removed_by_hand_is_no_longer_watched(
    theatre: Theatre, watching: Callable[[], Watch]
) -> None:
    theatre.write("troupe.yml", "p: file:p.md\n")
    theatre.write("p.md", "x\n")
    watching()
    start = time.monotonic()
    theatre.write("troupe.yml", "q: 1\n")
    recorded_within(theatre, 1, [("remove", "p", "x\n", None), ("set", "q", None, 1)], start)
    theatre.write("p.md", "y\n")
    nothing_recorded(theatre, 3)


def test_include_added_while_nothing_runs_is_picked_up_by_show(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.run("history")
    t.write("prompt.md", "Hello\n")
    t.write("troupe.yml", "a: 1\nprompt: file:prompt.md\n")
    assert t.run("show", "prompt").out == "Hello\n"
    assert brief(t)[1:] == [("set", "prompt", None, "Hello\n")]
