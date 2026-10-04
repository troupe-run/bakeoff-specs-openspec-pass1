"""A store written by step 3, before lineage, keeps working (config-lineage: Events recorded before lineage existed).

The fixture is a real `events.sqlite` made by the step-3 code; see `fixtures/step3/README.md`.
"""

import re
import shutil
from pathlib import Path

import pytest
from test_history import events

from conftest import Theatre

FIXTURE = Path(__file__).parent / "fixtures" / "step3"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
UNKNOWN = {"kind": "unknown", "id": None}


@pytest.fixture
def step3(theatre: Theatre) -> Theatre:
    """The step-3 theatre: imported with `a: 1`, then `set a 2`; its files now say `a: 2`."""
    theatre.dir.mkdir(parents=True)
    for name in ("troupe.yml", "events.sqlite"):
        shutil.copyfile(FIXTURE / name, theatre.dir / name)
    return theatre


def test_old_events_are_read_with_unknown_actor_and_their_stored_time(step3: Theatre) -> None:
    old = events(step3.run("history"))
    assert [(e["seq"], e["op"], e["path"], e["old"], e["new"]) for e in old] == [
        (1, "import", "a", None, 1),
        (2, "set", "a", 1, 2),
    ]
    assert [(e["actor"], e["via"], e["reason"], e["change"]) for e in old] == [
        (UNKNOWN, "import", None, "legacy-import"),
        (UNKNOWN, "file", None, "legacy-2"),
    ]
    # The times the step-3 code stored (see the fixture README), in UTC.
    assert [e["at"] for e in old] == ["2026-10-04T13:57:08.396654Z", "2026-10-04T13:57:08.756867Z"]
    assert all(TIMESTAMP.match(e["at"]) for e in old)


def test_new_events_follow_old_ones_with_their_own_lineage(
    step3: Theatre, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TROUPE_ACTOR", "human:alice")
    assert step3.run("set", "a", "9").code == 0
    lines = events(step3.run("history"))
    assert [(e["seq"], e["op"], e["old"], e["new"]) for e in lines] == [
        (1, "import", None, 1),
        (2, "set", 1, 2),
        (3, "set", 2, 9),  # the old projection (a = 2) still matches the files: nothing reconciled
    ]
    assert [(e["actor"], e["via"]) for e in lines] == [
        (UNKNOWN, "import"),
        (UNKNOWN, "file"),
        ({"kind": "human", "id": "alice"}, "cli"),
    ]
    assert len({e["change"] for e in lines}) == 3


def test_old_events_are_not_rewritten(step3: Theatre) -> None:
    before = (step3.dir / "events.sqlite").read_bytes()
    assert step3.run("history").code == 0
    assert (step3.dir / "events.sqlite").read_bytes() == before
