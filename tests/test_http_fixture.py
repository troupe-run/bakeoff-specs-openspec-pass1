"""The test HTTP server serves exactly what it is given, so remote-include tests see real HTTP responses."""

import urllib.request
from urllib.error import HTTPError

import pytest

from conftest import HttpServer


def test_serves_bytes_unchanged_and_counts_requests(http_server: HttpServer) -> None:
    url = http_server.serve("/a.md", b"one\r\ntwo\n")
    with urllib.request.urlopen(url) as response:
        assert response.read() == b"one\r\ntwo\n"
    assert http_server.requests["/a.md"] == 1


def test_answers_404_for_unknown_paths(http_server: HttpServer) -> None:
    with pytest.raises(HTTPError) as e:
        urllib.request.urlopen(http_server.url("/nothing"))
    assert e.value.code == 404
