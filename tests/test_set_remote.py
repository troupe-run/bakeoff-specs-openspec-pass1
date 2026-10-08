"""Values from remote includes are read-only (config-set, "Values from remote includes are read-only").

Every test serves the remote files from a real local HTTP server, and checks every local file byte for byte.
"""

import json

import pytest

from conftest import HttpServer, Result, Theatre


def refused(t: Theatre, *args: str) -> Result:
    """Run `set`; assert exit 3, empty stdout, no local file changed and no `cli` event recorded."""
    assert t.run("show").code == 0  # import (and reconcile) first, so only the set's own events could follow
    before = t.snapshot()
    r = t.run("set", *args)
    assert (r.code, r.out) == (3, ""), r.err
    assert t.snapshot() == before
    events = [json.loads(line) for line in t.run("history").out.splitlines()]
    assert [e for e in events if e["via"] == "cli"] == []
    return r


def test_changing_a_remote_value_names_the_local_include_line(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/team/coder.yaml", "model: m1\n")
    theatre.write("troupe.yml", f"name: x\nagents:\n  coder: {url}  # shared\n")
    r = refused(theatre, "agents.coder.model", "m2")
    assert "agents.coder.model" in r.err
    assert url in r.err
    assert ".troupe/troupe.yml line 3" in r.err


def test_the_include_string_is_quoted_as_written(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "model: m1\n")
    theatre.write("troupe.yml", f'coder: "{url}"\n')
    r = refused(theatre, "coder.model", "m2")
    assert f'"{url}"' in r.err


def test_a_new_key_under_a_remote_include_becomes_a_local_override(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/coder.yaml", "model: m1\n")
    theatre.write("troupe.yml", f"coder: {url}  # shared\n")
    r = theatre.run("set", "coder.temperature", "0.3")
    assert r.code == 0, r.err
    assert theatre.read("troupe.yml") == f"coder:  # shared\n  $ref: {url}\n  temperature: 0.3\n"
    assert theatre.run("show", "coder").out == "model: m1\ntemperature: 0.3\n"


def test_a_value_an_override_sets_is_local(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "temperature: 0.2\n")
    theatre.write("troupe.yml", f"coder:\n  $ref: {url}\n  temperature: 0.3\n")
    assert theatre.run("set", "coder.temperature", "0.5").code == 0
    assert theatre.read("troupe.yml") == f"coder:\n  $ref: {url}\n  temperature: 0.5\n"


def test_deleting_a_remote_key_is_refused(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "model: m1\ntemperature: 0.2\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert url in refused(theatre, "coder", "{model: m1}").err


def test_deleting_a_key_both_remote_and_overridden_is_refused(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/coder.yaml", "model: m1\ntemperature: 0.2\n")
    theatre.write("troupe.yml", f"coder:\n  $ref: {url}\n  temperature: 0.3\nother: 1\n")
    assert url in refused(theatre, "coder", "{model: m1}").err


def test_appending_to_a_remote_list_is_refused(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "tools: [read]\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert url in refused(theatre, "coder.tools.1", "write").err


def test_a_remote_text_include_is_refused(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/prompt.md", "Hi\n")
    theatre.write("troupe.yml", f"prompt: {url}\n")
    assert url in refused(theatre, "prompt", '"Bye\\n"').err


def test_in_include_under_a_remote_include_is_refused(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "model: m1\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert url in refused(theatre, "coder.temperature", "0.3", "--in-include").err


def test_nested_remote_includes_name_the_local_include_line(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/team/coder.yaml", "limits: file:limits.yaml\n")
    http_server.serve("/team/limits.yaml", "calls: 5\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    r = refused(theatre, "coder.limits.calls", "9")
    assert url in r.err and ".troupe/troupe.yml line 1" in r.err


def test_a_new_key_under_nested_remote_includes_overrides_the_local_include(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/team/coder.yaml", "limits: file:limits.yaml\n")
    http_server.serve("/team/limits.yaml", "calls: 5\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    r = theatre.run("set", "coder.limits.burst", "2")
    assert r.code == 0, r.err
    assert theatre.read("troupe.yml") == f"coder:\n  $ref: {url}\n  limits:\n    burst: 2\n"
    assert theatre.run("get", "coder.limits.calls").out == "5\n"
    assert theatre.run("set", "coder.limits.cap", "3").code == 0
    assert theatre.read("troupe.yml") == f"coder:\n  $ref: {url}\n  limits:\n    burst: 2\n    cap: 3\n"


def test_a_remote_include_in_a_local_included_file(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/limits.yaml", "calls: 5\n")
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", f"x: 1\nlimits: {url}\n")
    r = refused(theatre, "coder.limits.calls", "9")
    assert url in r.err and ".troupe/agents/coder.yaml line 2" in r.err


@pytest.mark.parametrize("flag", [(), ("--expand-alias",)])
def test_expanding_an_alias_in_remote_content_is_refused(
    theatre: Theatre, http_server: HttpServer, flag: tuple[str, ...]
) -> None:
    url = http_server.serve("/team.yaml", "base: &b {model: m}\ncoder: *b\n")
    theatre.write("troupe.yml", f"team: {url}\n")
    refused(theatre, *flag, "team.coder.model", "x")
