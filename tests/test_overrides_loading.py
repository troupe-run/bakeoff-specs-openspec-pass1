"""Mapping-form includes: `$ref` plus overrides, deep-merged with the included content (config-loading)."""

import pytest

from conftest import Theatre

CODER = "model: m1\ntemperature: 0.2\nlimits:\n  tokens: 100\n  calls: 5\ntools: [read, write]\n"


def test_overrides_deep_merge_with_the_included_content(theatre: Theatre) -> None:
    theatre.write("agents/coder.yaml", CODER)
    theatre.write(
        "troupe.yml",
        "agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    temperature: 0.3\n"
        "    limits:\n      calls: 9\n    tools: [read]\n    extra: x\n",
    )
    r = theatre.run("show", "agents.coder")
    assert (r.code, r.err) == (0, "")
    assert (
        r.out
        == "model: m1\ntemperature: 0.3\nlimits:\n  tokens: 100\n  calls: 9\ntools:\n  - read\nextra: x\n"
    )


def test_override_scalar_replaces_an_included_mapping(theatre: Theatre) -> None:
    theatre.write("agents/coder.yaml", "limits: {tokens: 100}\n")
    theatre.write("troupe.yml", "agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    limits: none\n")
    assert theatre.run("get", "agents.coder.limits").out == "none\n"


def test_override_mapping_replaces_an_included_scalar(theatre: Theatre) -> None:
    theatre.write("agents/coder.yaml", "limits: none\n")
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n")
    assert theatre.run("show", "coder").out == "limits:\n  calls: 9\n"


def test_mapping_form_without_overrides_is_the_scalar_form(theatre: Theatre) -> None:
    theatre.write("agents/coder.yaml", "model: m1\n")
    theatre.write("troupe.yml", "agents:\n  coder:\n    $ref: file:agents/coder.yaml\n")
    mapping_form = theatre.run("show", "--sources").out
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    assert theatre.run("show", "--sources").out == mapping_form
    assert mapping_form == "agents:\n  coder:\n    model: m1 # from .troupe/agents/coder.yaml\n"


def test_text_include_in_mapping_form(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "prompt:\n  $ref: file:prompt.md\n")
    theatre.write("prompt.md", "Hello\n")
    assert theatre.run("get", "prompt").out == "Hello\n"
    assert theatre.run("show", "--sources").out == "prompt: | # from .troupe/prompt.md\n  Hello\n"


def test_text_include_with_overrides_exits_4_naming_both_files(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "prompt:\n  $ref: file:prompt.md\n  extra: 1\n")
    theatre.write("prompt.md", "Hello\n")
    for args in (("get", "prompt"), ("show",), ("set", "a", "1"), ("history",)):
        r = theatre.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "troupe.yml" in r.err and "prompt.md" in r.err


@pytest.mark.parametrize("content", ["[a, b]\n", "5\n", ""], ids=["list", "scalar", "empty"])
def test_overrides_on_content_that_is_not_a_mapping_exit_4(theatre: Theatre, content: str) -> None:
    theatre.write("tools.yaml", content)
    theatre.write("troupe.yml", "tools:\n  $ref: file:tools.yaml\n  extra: 1\n")
    for args in (("show",), ("set", "a", "1"), ("history",)):
        r = theatre.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "troupe.yml" in r.err and "tools.yaml" in r.err


def test_include_inside_an_override_resolves_against_the_including_file(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder:\n  $ref: file:agents/coder.yaml\n  prompt: file:prompt.md\n")
    theatre.write("agents/coder.yaml", "model: m\n")
    theatre.write("prompt.md", "outer")
    theatre.write("agents/prompt.md", "inner")
    assert theatre.run("get", "coder.prompt").out == "outer\n"


def test_mapping_form_inside_an_included_file(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "agents:\n  coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "limits:\n  $ref: file:limits.yaml\n  calls: 9\n")
    theatre.write("agents/limits.yaml", "calls: 5\ntokens: 1\n")
    assert theatre.run("show", "agents.coder.limits").out == "calls: 9\ntokens: 1\n"


def test_ref_that_is_not_an_include_string_is_an_ordinary_key(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a:\n  $ref: hello\n  b: 1\n")
    assert theatre.run("show", "a").out == "$ref: hello\nb: 1\n"


def test_missing_target_in_mapping_form_exits_4_naming_it(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "a:\n  $ref: file:nope.yaml\n  b: 1\n")
    for args in (("show",), ("history",)):
        r = theatre.run(*args)
        assert (r.code, r.out) == (4, "")
        assert "nope.yaml" in r.err


def test_ref_value_is_not_itself_expanded_as_an_include(theatre: Theatre) -> None:
    # `$ref` names the include; it must not also become a key whose value is the included content.
    theatre.write("troupe.yml", "a:\n  $ref: file:a.yaml\n")
    theatre.write("a.yaml", "x: 1\n")
    assert theatre.run("show").out == "a:\n  x: 1\n"
