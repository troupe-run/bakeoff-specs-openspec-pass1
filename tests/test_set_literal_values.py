"""`set` writes include-looking strings literally unless `--include` is given (config-set, "Values that are
includes" and "Writing literal strings"). Each test checks the files byte for byte."""

import json
from collections.abc import Callable

import pytest

from conftest import HttpServer, Theatre

ENDPOINT_URI = json.dumps({"properties": {"endpoint": {"type": "string", "format": "uri"}}})


def set_ok(t: Theatre, *args: str) -> str:
    r = t.run("set", *args)
    assert (r.code, r.out, r.err) == (0, "", ""), r.err
    return t.read("troupe.yml")


def set_refused(t: Theatre, *args: str) -> str:
    before = t.snapshot()
    r = t.run("set", *args)
    assert (r.code, r.out) == (3, ""), r.err
    assert t.snapshot() == before
    return r.err


@pytest.mark.parametrize(
    ("path", "value", "after"),
    [
        ("prompt", "file:p.md", "a: 1\nprompt: !literal file:p.md\n"),
        (
            "docs",
            "https://example.invalid/team.yaml",
            "a: 1\ndocs: !literal https://example.invalid/team.yaml\n",
        ),
        ("docs", "http://example.invalid/x", "a: 1\ndocs: !literal http://example.invalid/x\n"),
        (
            "links",
            "[https://example.invalid/a, plain]",
            "a: 1\nlinks:\n  - !literal https://example.invalid/a\n  - plain\n",
        ),
        ("m", "{u: 'file:x', v: y}", "a: 1\nm:\n  u: !literal file:x\n  v: y\n"),
        ("note", '"file:x\\nmore\\n"', "a: 1\nnote: !literal |\n  file:x\n  more\n"),
        ("plain", "hello", "a: 1\nplain: hello\n"),
    ],
)
def test_include_looking_strings_are_written_literally(
    make: Callable[[str], Theatre], path: str, value: str, after: str
) -> None:
    t = make("a: 1\n")
    assert set_ok(t, path, value) == after
    r = t.run("show")
    assert r.code == 0, r.err  # reads back without reading or fetching anything


def test_a_literal_string_reads_back_as_written(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    set_ok(t, "prompt", "file:p.md")
    assert t.run("get", "prompt").out == "file:p.md\n"


@pytest.mark.parametrize(
    ("before", "value", "after"),
    [
        ("docs: 'old'\n", "https://example.invalid/new", "docs: !literal 'https://example.invalid/new'\n"),
        ("docs: old  # c\n", "file:x", "docs: !literal file:x # c\n"),
        ("docs: [a]\n", "file:x", "docs: !literal file:x\n"),
        ("docs: {a: 1}\nb: 1\n", "file:x", "docs: !literal file:x\nb: 1\n"),
        ("docs: |\n  old\n", '"file:x\\ny\\n"', "docs: !literal |\n  file:x\n  y\n"),
        ("docs:\n", "file:x", "docs: !literal file:x\n"),
        ("docs: !literal file:a\n", "file:b", "docs: !literal file:b\n"),
        ("docs: !literal |\n  file:a\n", '"file:b\\n"', "docs: !literal |\n  file:b\n"),
    ],
)
def test_adding_or_keeping_the_tag_on_an_existing_value(
    make: Callable[[str], Theatre], before: str, value: str, after: str
) -> None:
    assert set_ok(make(before), "docs", value) == after


def test_a_path_the_schema_marks_as_a_uri_is_written_untagged(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.write("troupe.schema.json", ENDPOINT_URI)
    assert (
        set_ok(t, "endpoint", "https://api.example.invalid/v1")
        == "a: 1\nendpoint: https://api.example.invalid/v1\n"
    )
    assert t.run("get", "endpoint").out == "https://api.example.invalid/v1\n"


def test_include_writes_a_local_include(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.write("p.md", "hello\n")
    assert set_ok(t, "prompt", "file:p.md", "--include") == "a: 1\nprompt: file:p.md\n"
    assert t.run("get", "prompt").out == "hello\n"


def test_include_writes_a_remote_include(make: Callable[[str], Theatre], http_server: HttpServer) -> None:
    url = http_server.serve("/team.yaml", "model: m\n")
    t = make("a: 1\n")
    assert set_ok(t, "team", url, "--include") == f"a: 1\nteam: {url}\n"
    assert t.run("get", "team.model").out == "m\n"


def test_include_inside_a_collection_value(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.write("p.md", "hello\n")
    assert set_ok(t, "m", "{p: 'file:p.md'}", "--include") == "a: 1\nm:\n  p: file:p.md\n"
    assert t.run("get", "m.p").out == "hello\n"


def test_include_to_a_missing_file_is_refused(make: Callable[[str], Theatre]) -> None:
    assert "prompt" in set_refused(make("a: 1\n"), "prompt", "file:nope.md", "--include")


def test_include_whose_fetch_fails_is_refused(
    make: Callable[[str], Theatre], http_server: HttpServer
) -> None:
    url = http_server.url("/missing.yaml")
    err = set_refused(make("a: 1\n"), "team", url, "--include")
    assert "team" in err and url in err


def test_include_at_a_uri_path_is_refused(make: Callable[[str], Theatre]) -> None:
    t = make("a: 1\n")
    t.write("troupe.schema.json", ENDPOINT_URI)
    assert "endpoint" in set_refused(t, "endpoint", "https://api.example.invalid/v1", "--include")


def test_setting_an_include_to_its_own_string(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m\n")
    before = theatre.snapshot()
    assert theatre.run("set", "agents.coder", "file:agents/coder.yaml", "--include").code == 0
    assert theatre.snapshot() == before
    assert "agents.coder" in set_refused(theatre, "agents.coder", "file:agents/coder.yaml")


def test_text_written_into_a_text_include_is_not_tagged(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "prompt: file:prompt.md\n")
    theatre.write("prompt.md", "Hi\n")
    assert set_ok(theatre, "prompt", "https://example.invalid/x") == "prompt: file:prompt.md\n"
    assert theatre.read("prompt.md") == "https://example.invalid/x"


def test_an_unchanged_literal_is_a_noop(make: Callable[[str], Theatre]) -> None:
    t = make("docs: !literal file:x\n")
    before = t.snapshot()
    assert set_ok(t, "docs", "file:x") == "docs: !literal file:x\n"
    assert t.snapshot() == before
