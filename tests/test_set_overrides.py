"""New keys under includes are written as overrides in the including file (config-set, step 5 CR-A).

Each test writes a theatre, runs one `set` and compares every file in it byte for byte, so a stray edit to the
shared, included file fails the test.
"""

import pytest

from conftest import Theatre


def set_and_read(theatre: Theatre, files: dict[str, str], *args: str) -> dict[str, str]:
    for name, text in files.items():
        theatre.write(name, text)
    r = theatre.run("set", *args)
    assert (r.code, r.out, r.err) == (0, "", ""), r.err
    return {name: theatre.read(name) for name in files}


@pytest.mark.parametrize(
    ("files", "args", "after"),
    [
        pytest.param(
            {"troupe.yml": "coder: file:agents/coder.yaml  # c\n", "agents/coder.yaml": "model: m\n"},
            ("coder.temperature", "0.3"),
            {"troupe.yml": "coder:  # c\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n"},
            id="contract-example-keeps-comment",
        ),
        pytest.param(
            {"troupe.yml": "agents:\n    coder: file:agents/coder.yaml\n", "agents/coder.yaml": "model: m\n"},
            ("agents.coder.temperature", "0.3"),
            {
                "troupe.yml": "agents:\n    coder:\n        $ref: file:agents/coder.yaml\n        temperature: 0.3\n"
            },
            id="indentation-of-the-including-file",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n",
                "agents/coder.yaml": "model: m\n",
            },
            ("coder.top_p", "0.9"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n  top_p: 0.9\n"},
            id="existing-mapping-form",
        ),
        pytest.param(
            {
                "troupe.yml": "coder: file:agents/coder.yaml\n",
                "agents/coder.yaml": "limits:\n  tokens: 100\n",
            },
            ("coder.limits.calls", "9"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n"},
            id="ancestor-deeper-in-the-included-file",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n",
                "agents/coder.yaml": "limits:\n  tokens: 100\n",
            },
            ("coder.limits.burst", "2"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n    burst: 2\n"},
            id="into-an-existing-override-mapping",
        ),
        pytest.param(
            {"troupe.yml": "coder: file:agents/coder.yaml\n", "agents/coder.yaml": "model: m\n"},
            ("coder.a.b", "x"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  a:\n    b: x\n"},
            id="missing-intermediates",
        ),
        pytest.param(
            {"troupe.yml": "coder: 'file:agents/coder.yaml'\n", "agents/coder.yaml": "model: m\n"},
            ("coder.t", "1"),
            {"troupe.yml": "coder:\n  $ref: 'file:agents/coder.yaml'\n  t: 1\n"},
            id="quoted-include-string",
        ),
        pytest.param(
            {"troupe.yml": "agents: {coder: file:agents/coder.yaml}\n", "agents/coder.yaml": "model: m\n"},
            ("agents.coder.t", "1"),
            {"troupe.yml": "agents: {coder: {$ref: file:agents/coder.yaml, t: 1}}\n"},
            id="flow-mapping",
        ),
        pytest.param(
            {"troupe.yml": "steps:\n  - file:step.yaml\n", "step.yaml": "name: a\n"},
            ("steps.0.k", "v"),
            {"troupe.yml": "steps:\n  - $ref: file:step.yaml\n    k: v\n"},
            id="list-item",
        ),
        pytest.param(
            {"troupe.yml": "file:base.yaml\n", "base.yaml": "a: 1\n"},
            ("k", "v"),
            {"troupe.yml": "$ref: file:base.yaml\nk: v\n"},
            id="whole-document",
        ),
        pytest.param(
            {
                "troupe.yml": "coder: file:agents/coder.yaml\n",
                "agents/coder.yaml": "limits: file:limits.yaml\n",
                "agents/limits.yaml": "calls: 5\n",
            },
            ("coder.limits.burst", "2"),
            {"agents/coder.yaml": "limits:\n  $ref: file:limits.yaml\n  burst: 2\n"},
            id="nested-include-nearest-including-file",
        ),
        pytest.param(
            {"troupe.yml": "coder: file:agents/coder.yaml\n", "agents/coder.yaml": "steps:\n  - name: a\n"},
            ("coder.steps.0.n", "1"),
            {"agents/coder.yaml": "steps:\n  - name: a\n    n: 1\n"},
            id="key-inside-a-list-item-of-an-included-file",
        ),
        pytest.param(
            {"troupe.yml": "coder: file:agents/coder.yaml\r\n", "agents/coder.yaml": "model: m\n"},
            ("coder.t", "1"),
            {"troupe.yml": "coder:\r\n  $ref: file:agents/coder.yaml\r\n  t: 1\r\n"},
            id="crlf-including-file",
        ),
    ],
)
def test_new_key_under_an_include_is_written_as_an_override(
    theatre: Theatre, files: dict[str, str], args: tuple[str, str], after: dict[str, str]
) -> None:
    assert set_and_read(theatre, files, *args) == {**files, **after}


def test_new_override_reads_back_as_the_new_value(theatre: Theatre) -> None:
    files = {"troupe.yml": "coder: file:agents/coder.yaml  # c\n", "agents/coder.yaml": "model: m\n"}
    set_and_read(theatre, files, "coder.temperature", "0.3")
    assert theatre.run("get", "coder.temperature").out == "0.3\n"
    assert theatre.run("show", "coder").out == "model: m\ntemperature: 0.3\n"


def test_overrides_merge_with_the_ancestor_in_the_included_file(theatre: Theatre) -> None:
    files = {"troupe.yml": "coder: file:agents/coder.yaml\n", "agents/coder.yaml": "limits:\n  tokens: 100\n"}
    set_and_read(theatre, files, "coder.limits.calls", "9")
    assert theatre.run("show", "coder.limits").out == "tokens: 100\ncalls: 9\n"


def test_a_file_included_twice_stays_shared(theatre: Theatre) -> None:
    files = {"troupe.yml": "a: file:common.yaml\nb: file:common.yaml\n", "common.yaml": "x: 1\n"}
    after = set_and_read(theatre, files, "a.k", "1")
    assert after == {**files, "troupe.yml": "a:\n  $ref: file:common.yaml\n  k: 1\nb: file:common.yaml\n"}
    assert theatre.run("get", "b.k").code == 5


@pytest.mark.parametrize(
    ("files", "args", "after"),
    [
        pytest.param(
            {"troupe.yml": "coder: file:agents/coder.yaml\n", "agents/coder.yaml": "tools:\n  - read\n"},
            ("coder.tools.1", "write"),
            {"agents/coder.yaml": "tools:\n  - read\n  - write\n"},
            id="list-in-an-included-file",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  tools: [read]\n",
                "agents/coder.yaml": "tools: [read, write]\n",
            },
            ("coder.tools.1", "exec"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  tools: [read, exec]\n"},
            id="overridden-list",
        ),
    ],
)
def test_append_goes_into_the_file_that_holds_the_list(
    theatre: Theatre, files: dict[str, str], args: tuple[str, str], after: dict[str, str]
) -> None:
    assert set_and_read(theatre, files, *args) == {**files, **after}


def test_mapping_value_adding_a_key_under_an_include_writes_an_override(theatre: Theatre) -> None:
    files = {"troupe.yml": "coder: file:agents/coder.yaml\n", "agents/coder.yaml": "limits:\n  tokens: 100\n"}
    after = set_and_read(theatre, files, "coder.limits", "{tokens: 100, calls: 9}")
    assert after == {
        **files,
        "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n",
    }


def test_new_key_after_an_include_entry_goes_below_its_reference(theatre: Theatre) -> None:
    # The end of an entry whose value is an include is the end of its reference, not of the included file.
    files = {"troupe.yml": "agents:\n  coder: file:c.yaml\nz: 1\n", "c.yaml": "model: " + "m" * 80 + "\n"}
    after = set_and_read(theatre, files, "agents.x", "1")
    assert after == {**files, "troupe.yml": "agents:\n  coder: file:c.yaml\n  x: 1\nz: 1\n"}


def test_second_override_after_a_mapping_form_entry_goes_below_its_overrides(theatre: Theatre) -> None:
    files = {
        "troupe.yml": "agents:\n  coder:\n    $ref: file:c.yaml\n    t: 1\nz: 1\n",
        "c.yaml": "model: " + "m" * 80 + "\n",
    }
    after = set_and_read(theatre, files, "agents.x", "1")
    assert after == {
        **files,
        "troupe.yml": "agents:\n  coder:\n    $ref: file:c.yaml\n    t: 1\n  x: 1\nz: 1\n",
    }


# --- existing values, deletes and include equality -------------------------------------------------------

OVERRIDDEN = {
    "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n",
    "agents/coder.yaml": "model: m\ntemperature: 0.2\n",
}
LIMITS = {
    "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n",
    "agents/coder.yaml": "limits:\n  tokens: 100\n  calls: 5\n",
}


def test_overridden_value_changes_the_override(theatre: Theatre) -> None:
    after = set_and_read(theatre, OVERRIDDEN, "coder.temperature", "0.5")
    assert after == {
        **OVERRIDDEN,
        "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.5\n",
    }


def test_value_that_is_not_overridden_changes_in_the_included_file(theatre: Theatre) -> None:
    after = set_and_read(theatre, OVERRIDDEN, "coder.model", "m2")
    assert after == {**OVERRIDDEN, "agents/coder.yaml": "model: m2\ntemperature: 0.2\n"}


def test_deleting_an_overridden_key_removes_it_from_both_files(theatre: Theatre) -> None:
    after = set_and_read(theatre, LIMITS, "coder.limits", "{tokens: 100}")
    assert after == {
        "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n",
        "agents/coder.yaml": "limits:\n  tokens: 100\n",
    }
    assert theatre.run("show", "coder.limits").out == "tokens: 100\n"


def test_deleting_one_of_several_override_keys_keeps_the_override_mapping(theatre: Theatre) -> None:
    files = {
        "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n    burst: 2\n",
        "agents/coder.yaml": "limits:\n  tokens: 100\n",
    }
    after = set_and_read(theatre, files, "coder.limits", "{tokens: 100, burst: 2}")
    assert after == {
        **files,
        "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    burst: 2\n",
    }


def test_replacing_an_overridden_mapping_writes_the_override(theatre: Theatre) -> None:
    after = set_and_read(theatre, LIMITS, "coder.limits", "5")
    assert after == {**LIMITS, "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits: 5\n"}


def test_setting_the_bare_include_string_with_overrides_is_refused(theatre: Theatre) -> None:
    for name, text in OVERRIDDEN.items():
        theatre.write(name, text)
    before = theatre.snapshot()
    r = theatre.run("set", "coder", "file:agents/coder.yaml")
    assert (r.code, r.out) == (3, "")
    assert "coder" in r.err
    assert theatre.snapshot() == before


def test_parent_set_that_keeps_the_merged_value_changes_only_the_rest(theatre: Theatre) -> None:
    files = {
        "troupe.yml": "agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    temperature: 0.3\n  other: 1\n",
        "agents/coder.yaml": "model: m\n",
    }
    after = set_and_read(theatre, files, "agents", "{coder: {model: m, temperature: 0.3}, other: 2}")
    assert after == {
        **files,
        "troupe.yml": "agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    temperature: 0.3\n  other: 2\n",
    }
