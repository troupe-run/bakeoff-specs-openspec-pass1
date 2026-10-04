"""End-to-end: the real `uv run troupe config …` command from the repository root."""

import json
import os
import selectors
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")


@dataclass
class Run:
    returncode: int
    stdout: str  # decoded exactly, without newline translation
    stderr: str


def troupe(theatre: Path, *args: str, **env: str) -> Run:
    """Run troupe with the test environment (conftest's known actor), plus `env`."""
    r = subprocess.run(
        ["uv", "run", "--quiet", "troupe", "config", *args, "--theatre", str(theatre)],
        cwd=REPO,
        capture_output=True,
        check=False,
        env={**os.environ, **env},
    )
    return Run(r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8"))


@pytest.fixture
def theatre(tmp_path: Path) -> Path:
    d = tmp_path / ".troupe"
    (d / "agents").mkdir(parents=True)
    (d / "troupe.yml").write_bytes(
        b"# The demo theatre\n"
        b"name: demo   # shown in the UI\n"
        b"agents:\n"
        b"  coder: file:agents/coder.yaml\n"
        b"  reviewer:\n"
        b"    model: 'small'\n"
        b"    tools: [read]\n"
        b"  # more agents here\n"
        b"\n"
        b"# global settings\n"
        b"limits:\n"
        b"  tokens: 1000\n"
    )
    (d / "agents" / "coder.yaml").write_bytes(b"model: big  # strongest\nprompt: file:coder.md\n")
    (d / "agents" / "coder.md").write_bytes(b"You write code.\r\nBe brief.\r\n")
    return tmp_path


def test_show_set_and_history_through_uv_run(theatre: Path) -> None:
    r = troupe(theatre, "show", "agents.coder.prompt")
    assert (r.returncode, r.stdout) == (0, "You write code.\r\nBe brief.\r\n")

    assert troupe(theatre, "set", "agents.coder.model", "bigger").returncode == 0
    assert (
        theatre / ".troupe/agents/coder.yaml"
    ).read_bytes() == b"model: bigger # strongest\nprompt: file:coder.md\n"

    assert troupe(theatre, "set", "agents.reviewer.tools.1", "lint").returncode == 0
    assert troupe(theatre, "set", "agents.tester.model", "tiny").returncode == 0
    assert (theatre / ".troupe/troupe.yml").read_bytes() == (
        b"# The demo theatre\n"
        b"name: demo   # shown in the UI\n"
        b"agents:\n"
        b"  coder: file:agents/coder.yaml\n"
        b"  reviewer:\n"
        b"    model: 'small'\n"
        b"    tools: [read, lint]\n"
        b"  # more agents here\n"
        b"  tester:\n"
        b"    model: tiny\n"
        b"\n"
        b"# global settings\n"
        b"limits:\n"
        b"  tokens: 1000\n"
    )

    assert troupe(theatre, "set", "agents.coder.prompt", '"Write tests.\\n"').returncode == 0
    assert (theatre / ".troupe/agents/coder.md").read_bytes() == b"Write tests.\r\n"

    r = troupe(theatre, "history", "agents.coder")
    lines = [json.loads(line) for line in r.stdout.splitlines()]
    assert [(e["op"], e["path"]) for e in lines] == [
        ("import", "agents.coder.model"),
        ("import", "agents.coder.prompt"),
        ("set", "agents.coder.model"),
        ("set", "agents.coder.prompt"),
    ]
    assert lines[-1]["old"] == "You write code.\r\nBe brief.\r\n" and lines[-1]["new"] == "Write tests.\r\n"


def test_get_and_show_sources_through_uv_run(theatre: Path) -> None:
    r = troupe(theatre, "get", "agents.coder.model")
    assert (r.returncode, r.stdout, r.stderr) == (0, "big\n", "")
    r = troupe(theatre, "show", "agents.coder", "--sources")
    assert (r.returncode, r.stderr) == (0, "")
    assert r.stdout == (
        "model: big # from .troupe/agents/coder.yaml\n"
        'prompt: "You write code.\\r\\nBe brief.\\r\\n" # from .troupe/agents/coder.md\n'
    )


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (("get", "agents"), 5),
        (("show", "nope"), 5),
        (("set", "agents.coder", "x"), 3),
        (("show", "a..b"), 2),
        (("bogus",), 2),
    ],
)
def test_exit_codes_through_uv_run(theatre: Path, args: tuple[str, ...], code: int) -> None:
    r = troupe(theatre, *args)
    assert (r.returncode, r.stdout) == (code, "")
    assert r.stderr


def test_lineage_through_uv_run_survives_between_processes(theatre: Path) -> None:
    r = troupe(
        theatre, "set", "agents.coder.model", "small", "--reason", "cheaper", TROUPE_ACTOR="agent:smoke"
    )
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    r = troupe(theatre, "history", "agents.coder.model", TROUPE_ACTOR="human:auditor")
    imported, changed = (json.loads(line) for line in r.stdout.splitlines())
    assert (imported["actor"], imported["via"]) == ({"kind": "unknown", "id": None}, "import")
    assert (changed["new"], changed["actor"], changed["via"], changed["reason"]) == (
        "small",
        {"kind": "agent", "id": "smoke"},
        "cli",
        "cheaper",
    )
    assert changed["at"].endswith("Z") and changed["change"] != imported["change"]


def test_invalid_actor_exits_2_through_uv_run(theatre: Path) -> None:
    r = troupe(theatre, "set", "name", "x", TROUPE_ACTOR="robot:x")
    assert (r.returncode, r.stdout) == (2, "")
    assert "TROUPE_ACTOR" in r.stderr


def test_missing_config_exits_4_through_uv_run(tmp_path: Path) -> None:
    r = troupe(tmp_path, "history")
    assert (r.returncode, r.stdout) == (4, "")
    assert "troupe.yml" in r.stderr


def test_watch_through_uv_run_records_a_hand_edit_and_stops_on_sigterm(theatre: Path) -> None:
    proc = subprocess.Popen(
        ["uv", "run", "--quiet", "troupe", "config", "watch", "--theatre", str(theatre)],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=60), "watch did not print its line"
        line = proc.stdout.readline()
        assert line == f"watching {theatre}\n".encode()

        start = time.monotonic()
        (theatre / ".troupe/agents/coder.yaml").write_bytes(
            b"model: huge  # strongest\nprompt: file:coder.md\n"
        )
        while True:
            r = troupe(theatre, "history", "agents.coder.model")
            if '"new": "huge"' in r.stdout:
                break
            assert time.monotonic() - start < 10, r.stdout
            time.sleep(0.1)
        assert json.loads(r.stdout.splitlines()[-1])["old"] == "big"

        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=20)
        assert (proc.returncode, out, err) == (0, b"", b"")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
