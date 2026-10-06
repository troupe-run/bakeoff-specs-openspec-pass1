"""Merge keys (`<<`) are never written (config-set, "Merge keys are never written")."""

import json
from collections.abc import Callable

import pytest

from conftest import Theatre

MERGED = "base: &b\n  model: opus\n  temperature: 0.2\ncoder:\n  <<: *b\n  temperature: 0.5\n"


@pytest.mark.parametrize(
    ("before", "path", "value", "after"),
    [
        pytest.param(MERGED, "coder.temperature", "0.7", MERGED.replace("0.5", "0.7"), id="own-key"),
        pytest.param(MERGED, "coder.top_p", "0.9", MERGED + "  top_p: 0.9\n", id="new-key"),
        pytest.param(
            "base: &b {m: 1}\ncoder:\n  t: 1\n  <<: *b\nz: 2\n",
            "coder.u",
            "2",
            "base: &b {m: 1}\ncoder:\n  t: 1\n  <<: *b\n  u: 2\nz: 2\n",
            id="new-key-when-the-merge-key-is-last",
        ),
        pytest.param(
            "base: &b {m: 1}\ncoder:\n  <<: *b\nz: 2\n",
            "coder.u",
            "2",
            "base: &b {m: 1}\ncoder:\n  <<: *b\n  u: 2\nz: 2\n",
            id="new-key-when-only-the-merge-key-is-written",
        ),
        pytest.param(
            "base: &b {m: 1}\ncoder:\n  <<: *b\n",
            "after",
            "1",
            "base: &b {m: 1}\ncoder:\n  <<: *b\nafter: 1\n",
            id="new-key-after-a-merging-mapping",
        ),
        pytest.param(
            MERGED,
            "coder",
            "{model: opus, temperature: 0.5, top_p: 1}",
            MERGED + "  top_p: 1\n",
            id="mapping-value-keeping-merged-keys",
        ),
        pytest.param(
            "base: &b {m: 1}\nzz: {}\n",
            "zz.<<",
            "5",
            "base: &b {m: 1}\nzz: {'<<': 5}\n",
            id="new-key-named-<<",
        ),
    ],
)
def test_writes_next_to_a_merge_key(
    set_file: Callable[..., str], before: str, path: str, value: str, after: str
) -> None:
    assert set_file(before, path, value) == after


def test_changing_the_merged_anchor_changes_the_merging_mapping(make: Callable[[str], Theatre]) -> None:
    t = make(MERGED)
    t.run("history")
    assert t.run("set", "base.model", "sonnet").code == 0
    assert t.read("troupe.yml") == MERGED.replace("opus", "sonnet")
    assert t.run("get", "coder.model").out == "sonnet\n"
    events = [json.loads(line) for line in t.run("history").out.splitlines()]
    assert [(e["path"], e["new"]) for e in events if e["via"] == "cli"] == [
        ("base.model", "sonnet"),
        ("coder.model", "sonnet"),
    ]


@pytest.mark.parametrize(
    ("before", "args"),
    [
        pytest.param(MERGED, ("coder.model", "sonnet"), id="merged-value"),
        pytest.param(
            MERGED, ("coder.model", "sonnet", "--expand-alias"), id="merged-value-with-expand-alias"
        ),
        pytest.param(MERGED, ("coder", "{temperature: 0.5}"), id="leaving-out-a-merged-key"),
        pytest.param(MERGED, ("coder", "none"), id="replacing-the-holding-mapping"),
        pytest.param(MERGED, ("coder", "{}"), id="emptying-the-holding-mapping"),
        pytest.param(
            "base: &b {m: 1}\nx:\n  coder:\n    <<: *b\n  k: 1\n",
            ("x", "{k: 1}"),
            id="deleting-an-entry-with-it",
        ),
        pytest.param(
            "base: &b {m: 1}\nl:\n  - k: 1\n  - <<: *b\n", ("l", "[{k: 1}]"), id="deleting-an-item-with-it"
        ),
        pytest.param(
            "base: &b {s: {m: 1}}\ncoder:\n  <<: *b\n", ("coder.s.x", "2"), id="new-key-below-a-merged-value"
        ),
    ],
)
def test_writes_to_merge_keys_are_refused(
    make: Callable[[str], Theatre], before: str, args: tuple[str, ...]
) -> None:
    t = make(before)
    snapshot = t.snapshot()
    r = t.run("set", *args)
    assert (r.code, r.out) == (3, "")
    assert args[0] in r.err and "<<" in r.err
    assert t.snapshot() == snapshot
