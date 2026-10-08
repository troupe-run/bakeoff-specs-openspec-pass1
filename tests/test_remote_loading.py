"""Remote includes when loading (config-loading, "Remote includes"), served by a real local HTTP server."""

import pytest

from conftest import HttpServer, Theatre, closed_port_url

COMMANDS = (("get", "coder"), ("show",), ("set", "x", "1"), ("history",))


def assert_unloadable(t: Theatre, *names: str) -> None:
    before = t.snapshot()
    for args in COMMANDS:
        r = t.run(*args)
        assert (r.code, r.out) == (4, ""), (args, r.err)
        for name in names:
            assert name in r.err, (args, r.err)
    assert t.snapshot() == before


def test_remote_yaml_include(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/team/coder.yaml", "model: m1\n")
    theatre.write("troupe.yml", f"agents:\n  coder: {url}\n")
    r = theatre.run("get", "agents.coder.model")
    assert (r.code, r.out) == (0, "m1\n"), r.err


def test_remote_text_include_keeps_its_exact_text(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/team/prompt.md", b"Hello\r\nWorld\n")
    theatre.write("troupe.yml", f"prompt: {url}\n")
    assert theatre.run("get", "prompt").out == "Hello\r\nWorld\n"


def test_https_and_http_strings_in_any_quoting_are_includes(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/a.yaml", "x: 1\n")
    theatre.write("troupe.yml", f"a: '{url}'\nb: \"{url}\"\n")
    assert theatre.run("show").out == "a:\n  x: 1\nb:\n  x: 1\n"


def test_the_url_path_decides_yaml_or_text(theatre: Theatre, http_server: HttpServer) -> None:
    a = http_server.serve("/a.yaml?v=2", "x: 1\n")
    b = http_server.serve("/b.txt", "x: 1\n")
    theatre.write("troupe.yml", f"a: {a}\nb: {b}\n")
    assert theatre.run("get", "a.x").out == "1\n"
    assert theatre.run("get", "b").out == "x: 1\n"


def test_remote_include_in_mapping_form_with_overrides(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "model: m1\ntemperature: 0.2\n")
    theatre.write("troupe.yml", f"coder:\n  $ref: {url}\n  temperature: 0.3\n")
    assert theatre.run("show", "coder").out == "model: m1\ntemperature: 0.3\n"


def test_file_include_inside_remote_content_resolves_against_its_url(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/agents/coder.yaml", "prompt: file:coder.md\n")
    http_server.serve("/agents/coder.md", "Hi\n")
    theatre.write("agents/coder.md", "local, never read\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert theatre.run("get", "coder.prompt").out == "Hi\n"


def test_remote_include_from_an_included_local_file(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/limits.yaml", "calls: 5\n")
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", f"limits: {url}\n")
    assert theatre.run("get", "coder.limits.calls").out == "5\n"


def test_not_found_fails_to_load_naming_the_url(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.url("/missing.yaml")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert_unloadable(theatre, url)


def test_unreachable_server_fails_to_load_naming_the_url(theatre: Theatre) -> None:
    url = closed_port_url("/coder.yaml")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert_unloadable(theatre, url)


def test_invalid_remote_yaml_fails_to_load_naming_the_url(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/coder.yaml", "a: [1\n")
    theatre.write("troupe.yml", f"coder: {url}\n")
    assert_unloadable(theatre, url)


def test_remote_content_that_is_not_utf8_fails_to_load(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/p.md", b"\xff\xfe")
    theatre.write("troupe.yml", f"p: {url}\n")
    assert_unloadable(theatre, url)


def test_each_url_is_fetched_once_per_command(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/c.yaml", "a: 1\n")
    theatre.write("troupe.yml", f"a: {url}\nb: {url}\n")
    assert theatre.run("show").code == 0
    http_server.requests.clear()
    r = theatre.run("set", "x", "{y: 1, z: 2}")  # several operations, each followed by a reload
    assert r.code == 0, r.err
    assert http_server.requests["/c.yaml"] == 1


def test_each_command_fetches_afresh(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/c.yaml", "a: 1\n")
    theatre.write("troupe.yml", f"c: {url}\n")
    assert theatre.run("get", "c.a").out == "1\n"
    http_server.serve("/c.yaml", "a: 2\n")
    assert theatre.run("get", "c.a").out == "2\n"


def test_remote_cycle_fails_to_load(theatre: Theatre, http_server: HttpServer) -> None:
    a = http_server.url("/a.yaml")
    http_server.serve("/a.yaml", "b: file:b.yaml\n")
    http_server.serve("/b.yaml", f"a: {a}\n")
    theatre.write("troupe.yml", f"x: {a}\n")
    assert_unloadable(theatre, a, "cycle")


def test_redirects_are_followed(theatre: Theatre, http_server: HttpServer) -> None:
    http_server.serve("/new.yaml", "a: 1\n")
    url = http_server.redirect("/old.yaml", http_server.url("/new.yaml"))
    theatre.write("troupe.yml", f"c: {url}\n")
    assert theatre.run("get", "c.a").out == "1\n"


@pytest.mark.parametrize("location", ["file:///etc/hostname", "ftp://127.0.0.1/x.yaml"])
def test_redirects_to_other_schemes_are_refused(
    theatre: Theatre, http_server: HttpServer, location: str
) -> None:
    url = http_server.redirect("/old.yaml", location)
    theatre.write("troupe.yml", f"c: {url}\n")
    assert_unloadable(theatre, url, location)
