"""`set --in-include`: new keys go into the included file itself, not into overrides (config-set, step 5 CR-B).

Each test compares every file in the theatre byte for byte, so a stray override or edit fails it.
"""

import json

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
            ("coder.temperature", "0.3", "--in-include"),
            {"agents/coder.yaml": "model: m\ntemperature: 0.3\n"},
            id="into-the-included-file",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n",
                "agents/coder.yaml": "model: m\n",
            },
            ("--in-include", "coder.top_p", "0.9"),
            {"agents/coder.yaml": "model: m\ntop_p: 0.9\n"},
            id="mapping-form-with-overrides",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n",
                "agents/coder.yaml": "limits:\n  tokens: 100\n",
            },
            ("coder.limits.burst", "2", "--in-include"),
            {"agents/coder.yaml": "limits:\n  tokens: 100\n  burst: 2\n"},
            id="merged-ancestor",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  extra:\n    a: 1\n",
                "agents/coder.yaml": "model: m\n",
            },
            ("coder.extra.b", "2", "--in-include"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  extra:\n    a: 1\n    b: 2\n"},
            id="override-only-ancestor",
        ),
        pytest.param(
            {"troupe.yml": "coder: file:agents/coder.yaml\n", "agents/coder.yaml": "model: m\n"},
            ("coder.a.b", "x", "--in-include"),
            {"agents/coder.yaml": "model: m\na:\n  b: x\n"},
            id="missing-intermediates",
        ),
        pytest.param(
            {
                "troupe.yml": "coder: file:agents/coder.yaml\n",
                "agents/coder.yaml": "limits: file:limits.yaml\n",
                "agents/limits.yaml": "calls: 5\n",
            },
            ("coder.limits.burst", "2", "--in-include"),
            {"agents/limits.yaml": "calls: 5\nburst: 2\n"},
            id="nested-includes-innermost-file",
        ),
        pytest.param(
            {
                "troupe.yml": "coder: file:agents/coder.yaml\n",
                "agents/coder.yaml": "limits:\n  $ref: file:limits.yaml\n  calls: 9\n",
                "agents/limits.yaml": "calls: 5\n",
            },
            ("coder.limits.burst", "2", "--in-include"),
            {"agents/limits.yaml": "calls: 5\nburst: 2\n"},
            id="nested-merged-innermost-file",
        ),
        pytest.param(
            {
                "troupe.yml": "coder: file:agents/coder.yaml\n",
                "agents/coder.yaml": "limits:\n  tokens: 100\n",
            },
            ("coder.limits", "{tokens: 100, calls: 9}", "--in-include"),
            {"agents/coder.yaml": "limits:\n  tokens: 100\n  calls: 9\n"},
            id="mapping-value",
        ),
        pytest.param(
            {
                "troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n",
                "agents/coder.yaml": "temperature: 0.2\n",
            },
            ("coder.temperature", "0.5", "--in-include"),
            {"troupe.yml": "coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.5\n"},
            id="existing-overridden-value-changes-the-override",
        ),
    ],
)
def test_in_include_writes_new_keys_into_the_included_file(
    theatre: Theatre, files: dict[str, str], args: tuple[str, ...], after: dict[str, str]
) -> None:
    assert set_and_read(theatre, files, *args) == {**files, **after}


def test_in_include_without_an_include_gives_the_same_bytes_as_without_it(theatre: Theatre) -> None:
    with_flag = set_and_read(theatre, {"troupe.yml": "a:\n  b: 1\n"}, "a.c", "2", "--in-include")
    without = set_and_read(theatre, {"troupe.yml": "a:\n  b: 1\n"}, "a.c", "2")
    assert with_flag == without == {"troupe.yml": "a:\n  b: 1\n  c: 2\n"}


def test_in_include_into_an_empty_included_file_exits_5_and_changes_nothing(theatre: Theatre) -> None:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "")
    before = theatre.snapshot()
    for extra in (("--in-include",), ()):
        r = theatre.run("set", "coder.x", "1", *extra)
        assert (r.code, r.out) == (5, "")
        assert theatre.snapshot() == before


def _own_events(theatre: Theatre, *flag: str) -> list[dict[str, object]]:
    theatre.write("troupe.yml", "coder: file:agents/coder.yaml\n")
    theatre.write("agents/coder.yaml", "model: m\n")
    (theatre.dir / "events.sqlite").unlink(missing_ok=True)
    assert theatre.run("set", "coder.temperature", "0.3", *flag).code == 0
    lines = [json.loads(line) for line in theatre.run("history").out.splitlines()]
    return [
        {k: e[k] for k in ("seq", "op", "path", "old", "new", "actor", "via", "reason")}
        for e in lines
        if e["op"] != "import"
    ]


def test_in_include_records_the_same_event_as_without_it(theatre: Theatre) -> None:
    with_flag = _own_events(theatre, "--in-include")
    assert theatre.read("agents/coder.yaml") == "model: m\ntemperature: 0.3\n"
    without = _own_events(theatre)
    assert theatre.read("agents/coder.yaml") == "model: m\n"
    assert with_flag == without
    assert [(e["op"], e["path"], e["old"], e["new"], e["via"]) for e in with_flag] == [
        ("set", "coder.temperature", None, 0.3, "cli")
    ]
