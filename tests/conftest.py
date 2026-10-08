"""Shared fixtures: real theatres on disk and the real CLI entry point, run in-process."""

import socket
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


@dataclass
class Route:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class HttpServer:
    """A real HTTP server on 127.0.0.1 serving `routes` (by request path, query included) and counting requests.

    Paths it has no route for get 404.
    """

    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.requests: Counter[str] = Counter()
        routes, requests = self.routes, self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests[self.path] += 1
                route = routes.get(self.path, Route(404, b"not found"))
                self.send_response(route.status)
                for name, value in route.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(route.body)))
                self.end_headers()
                self.wfile.write(route.body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, args=(0.02,), daemon=True)
        self._thread.start()

    def url(self, path: str) -> str:
        return self.base + path

    def serve(
        self, path: str, body: str | bytes, status: int = 200, headers: dict[str, str] | None = None
    ) -> str:
        """Serve `body` at `path`; returns its URL."""
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.routes[path] = Route(status, data, headers or {})
        return self.url(path)

    def redirect(self, path: str, location: str) -> str:
        return self.serve(path, b"", 302, {"Location": location})

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def closed_port_url(path: str) -> str:
    """A URL on 127.0.0.1 where nothing listens: a port that was bound and then released."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}{path}"


@pytest.fixture
def http_server() -> Iterator[HttpServer]:
    server = HttpServer()
    yield server
    server.close()
