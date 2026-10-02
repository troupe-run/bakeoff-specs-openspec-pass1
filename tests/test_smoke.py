"""End-to-end: the real `uv run troupe config …` command from the repository root."""

import json
import shutil
import subprocess
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


def troupe(theatre: Path, *args: str) -> Run:
    r = subprocess.run(
        ["uv", "run", "--quiet", "troupe", "config", *args, "--theatre", str(theatre)],
        cwd=REPO,
        capture_output=True,
        check=False,
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


@pytest.mark.parametrize(
    ("args", "code"),
    [(("show", "agents"), 5), (("set", "agents.coder", "x"), 3), (("show", "a..b"), 2), (("bogus",), 2)],
)
def test_exit_codes_through_uv_run(theatre: Path, args: tuple[str, ...], code: int) -> None:
    r = troupe(theatre, *args)
    assert (r.returncode, r.stdout) == (code, "")
    assert r.stderr


def test_missing_config_exits_4_through_uv_run(tmp_path: Path) -> None:
    r = troupe(tmp_path, "history")
    assert (r.returncode, r.stdout) == (4, "")
    assert "troupe.yml" in r.stderr
