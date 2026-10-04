import calendar
import pwd
import re
import time

import pytest

from troupe.errors import UsageError
from troupe.lineage import Actor, actor_from_env, for_cli, for_file, for_import, login_name, now

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


@pytest.mark.parametrize(
    ("value", "actor"),
    [
        ("human:alice", Actor("human", "alice")),
        ("agent:planner-7", Actor("agent", "planner-7")),
        ("agent:claude:session-1", Actor("agent", "claude:session-1")),
        ("human: spaced id ", Actor("human", " spaced id ")),
    ],
)
def test_actor_from_env_reads_kind_and_exact_id(value: str, actor: Actor) -> None:
    assert actor_from_env({"TROUPE_ACTOR": value}) == actor


def test_unset_actor_is_the_human_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOGNAME", "bob")
    assert actor_from_env({}) == Actor("human", "bob")


@pytest.mark.parametrize("value", ["robot:x", "alice", "human:", "Human:alice", "AGENT:x", "", ":x"])
def test_invalid_actor_is_a_usage_error_naming_the_variable(value: str) -> None:
    with pytest.raises(UsageError, match="TROUPE_ACTOR"):
        actor_from_env({"TROUPE_ACTOR": value})


def test_login_name_is_none_when_nothing_names_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
        monkeypatch.delenv(name, raising=False)

    def no_entry(uid: int) -> pwd.struct_passwd:
        raise KeyError(f"getpwuid(): uid not found: {uid}")

    monkeypatch.setattr(pwd, "getpwuid", no_entry)
    assert login_name() is None
    assert actor_from_env({}) == Actor("human", None)


def test_now_is_fixed_width_utc_whatever_the_local_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Asia/Tokyo")  # UTC+9, no DST
    time.tzset()
    try:
        before = time.time()
        stamp = now()
        after = time.time()
    finally:
        monkeypatch.undo()
        time.tzset()
    assert TIMESTAMP.match(stamp), stamp
    # Read back as UTC: a local-time stamp would be 9 hours off.
    parsed = calendar.timegm(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")) + float("0" + stamp[19:-1])
    assert before - 0.001 <= parsed <= after + 0.001


def test_each_lineage_is_a_new_change() -> None:
    lineages = [for_import(), for_file(), for_file(), for_cli(Actor("agent", "a"), None)]
    assert len({lineage.change for lineage in lineages}) == len(lineages)


def test_lineage_constructors_set_actor_via_and_reason() -> None:
    actor = Actor("agent", "a")
    assert [(x.actor, x.via, x.reason) for x in (for_import(), for_file(), for_cli(actor, "why"))] == [
        (Actor("unknown", None), "import", None),
        (Actor("unknown", None), "file", None),
        (actor, "cli", "why"),
    ]
