"""The theatre's JSON Schema, `.troupe/troupe.schema.json` (config-schema): reading it, literal URIs, and
validating the configuration on load and on `set`. Real schema files on disk, run through the real CLI."""

import json
from collections.abc import Callable

import pytest

from conftest import HttpServer, Result, Theatre

ENDPOINT_URI = {"type": "object", "properties": {"endpoint": {"type": "string", "format": "uri"}}}
NUMBER = {"properties": {"temperature": {"type": "number"}}}


def with_schema(t: Theatre, schema: object, config: str) -> Theatre:
    t.write("troupe.schema.json", json.dumps(schema) if not isinstance(schema, str) else schema)
    t.write("troupe.yml", config)
    return t


def assert_unloadable(t: Theatre, *names: str) -> None:
    for args in (("get", "a"), ("show",), ("set", "x", "1"), ("history",)):
        r = t.run(*args)
        assert (r.code, r.out) == (4, ""), (args, r.err)
        for name in names:
            assert name in r.err, (args, r.err)


def cli_events(t: Theatre) -> list[dict[str, object]]:
    return [e for e in map(json.loads, t.run("history").out.splitlines()) if e["via"] == "cli"]


# --- the schema file ---------------------------------------------------------------------------------------


def test_without_a_schema_nothing_is_validated(make: Callable[[str], Theatre]) -> None:
    assert make("a: 1\n").run("get", "a").out == "1\n"


@pytest.mark.parametrize(
    "data", [b'{"type": "object",', b'{"type": 5}', b"\xff"], ids=["not JSON", "not a schema", "not UTF-8"]
)
def test_an_unusable_schema_fails_to_load(theatre: Theatre, data: bytes) -> None:
    theatre.write("troupe.yml", "a: 1\n")
    (theatre.dir / "troupe.schema.json").write_bytes(data)
    assert_unloadable(theatre, "troupe.schema.json")


def test_a_reference_outside_the_schema_fails_to_load_and_is_not_fetched(
    theatre: Theatre, http_server: HttpServer
) -> None:
    url = http_server.serve("/other.json", "{}")
    with_schema(theatre, {"properties": {"a": {"$ref": url}}}, "a: 1\n")
    assert_unloadable(theatre, "troupe.schema.json")
    assert http_server.requests["/other.json"] == 0


def test_a_property_named_ref_is_not_a_reference(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), {"properties": {"$ref": {"type": "string"}}}, "a: 1\n")
    assert t.run("get", "a").out == "1\n"


# --- strings the schema marks as URIs ----------------------------------------------------------------------


def test_a_uri_setting_is_a_literal_and_not_fetched(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/v1.yaml", "a: 1\n")
    with_schema(theatre, ENDPOINT_URI, f"endpoint: {url}\n")
    assert theatre.run("get", "endpoint").out == f"{url}\n"
    assert http_server.requests["/v1.yaml"] == 0


def test_the_same_string_elsewhere_is_an_include(theatre: Theatre, http_server: HttpServer) -> None:
    url = http_server.serve("/x.yaml", "a: 1\n")
    with_schema(theatre, ENDPOINT_URI, f"endpoint: {url}\nshared: {url}\n")
    assert theatre.run("get", "endpoint").out == f"{url}\n"
    assert theatre.run("get", "shared.a").out == "1\n"


def test_found_through_additional_properties_and_items(make: Callable[[str], Theatre]) -> None:
    schema = {
        "properties": {
            "agents": {"additionalProperties": {"properties": {"docs": {"items": {"format": "uri"}}}}}
        }
    }
    t = with_schema(
        make(""), schema, "agents:\n  coder:\n    docs: [https://example.invalid/a.md, file:b.md]\n"
    )
    r = t.run("show", "agents.coder.docs")
    assert (r.code, r.out) == (0, "- https://example.invalid/a.md\n- file:b.md\n"), r.err


def test_properties_win_over_additional_properties(make: Callable[[str], Theatre]) -> None:
    schema = {"properties": {"a": {"type": "string"}}, "additionalProperties": {"format": "uri"}}
    t = with_schema(make(""), schema, "a: file:nope.md\nb: file:nope.md\n")
    assert_unloadable(t, "nope.md")  # `a` is not marked, so it is an include of a missing file


def test_inside_included_content(make: Callable[[str], Theatre]) -> None:
    schema = {
        "properties": {"agents": {"properties": {"coder": {"properties": {"homepage": {"format": "uri"}}}}}}
    }
    t = with_schema(make(""), schema, "agents:\n  coder: file:agents/coder.yaml\n")
    t.write("agents/coder.yaml", "homepage: https://example.invalid/coder\n")
    assert t.run("get", "agents.coder.homepage").out == "https://example.invalid/coder\n"


def test_only_properties_items_and_additional_properties_are_followed(make: Callable[[str], Theatre]) -> None:
    schema = {"properties": {"endpoint": {"$ref": "#/$defs/url"}}, "$defs": {"url": {"format": "uri"}}}
    t = with_schema(make(""), schema, "endpoint: file:nope.md\n")
    assert_unloadable(t, "nope.md")


def test_a_ref_string_is_judged_at_its_own_position(make: Callable[[str], Theatre]) -> None:
    schema = {"properties": {"a": {"properties": {"$ref": {"format": "uri"}}}}}
    t = with_schema(make(""), schema, "a:\n  $ref: file:nope.yaml\n  b: 1\n")
    assert t.run("show", "a").out == "$ref: file:nope.yaml\nb: 1\n"


def test_an_aliased_string_is_judged_where_its_anchor_is(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), ENDPOINT_URI, "endpoint: &e file:nope.md\nother: *e\n")
    assert t.run("get", "other").out == "file:nope.md\n"


# --- validation ----------------------------------------------------------------------------------------------


def test_an_invalid_configuration_fails_to_load(make: Callable[[str], Theatre]) -> None:
    assert_unloadable(
        with_schema(make(""), NUMBER, "temperature: hot\n"), "troupe.schema.json", "temperature"
    )


def test_included_content_is_validated(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), {"properties": {"coder": {"required": ["model"]}}}, "coder: file:coder.yaml\n")
    t.write("coder.yaml", "temperature: 0.2\n")
    assert_unloadable(t, "troupe.schema.json", "coder")


def test_format_is_not_checked(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), ENDPOINT_URI, "endpoint: not a url\n")
    assert t.run("get", "endpoint").out == "not a url\n"


def test_a_hand_edit_that_breaks_validity_records_nothing(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), NUMBER, "temperature: 0.2\n")
    before = t.run("history").out
    t.write("troupe.yml", "temperature: hot\n")
    r = t.run("show")
    assert (r.code, r.out) == (4, "")
    t.write("troupe.yml", "temperature: 0.2\n")
    assert t.run("history").out == before


def test_an_invalid_set_is_refused(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), NUMBER, "temperature: 0.2\n")
    before = t.snapshot()
    r: Result = t.run("set", "temperature", "hot")
    assert (r.code, r.out) == (3, "")
    assert "temperature" in r.err and "troupe.schema.json" in r.err
    assert t.snapshot() == before
    assert cli_events(t) == []


def test_a_valid_set_is_accepted(make: Callable[[str], Theatre]) -> None:
    t = with_schema(make(""), NUMBER, "temperature: 0.2\n")
    assert t.run("set", "temperature", "0.5").code == 0
    assert t.read("troupe.yml") == "temperature: 0.5\n"


def test_only_the_result_of_a_set_is_validated(make: Callable[[str], Theatre]) -> None:
    # Valid only with both keys or neither; the set adds them in two steps.
    schema = {"properties": {"m": {"dependentRequired": {"a": ["b"], "b": ["a"]}}}}
    t = with_schema(make(""), schema, "m:\n  c: 1\n")
    r = t.run("set", "m", "{c: 1, a: 1, b: 2}")
    assert r.code == 0, r.err
    assert t.read("troupe.yml") == "m:\n  c: 1\n  a: 1\n  b: 2\n"
