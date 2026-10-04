"""Who, how, when, why and in which change each recorded event happened (the one place these are decided).

Each `for_*` call is one change: a fresh change id and one timestamp, shared by every event saved with it.
"""

import getpass
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from troupe.errors import UsageError

ActorKind = Literal["human", "agent", "unknown"]
Via = Literal["import", "cli", "file"]

ACTOR_VARIABLE = "TROUPE_ACTOR"
_ACTOR_KINDS: tuple[ActorKind, ...] = ("human", "agent")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: str | None


# Imports and hand edits: troupe cannot know who wrote the files.
UNKNOWN = Actor("unknown", None)


@dataclass(frozen=True)
class Lineage:
    actor: Actor
    via: Via
    at: str  # RFC 3339 UTC, TIMESTAMP_FORMAT
    reason: str | None
    change: str


def login_name() -> str | None:
    """The login name of the user running troupe, or None when none can be determined.

    `getpass.getuser()` reads LOGNAME, USER, LNAME and USERNAME, then the password database; it works
    without a terminal, unlike `os.getlogin()`. It raises KeyError (3.12) or OSError (later) when nothing
    is known.
    """
    try:
        return getpass.getuser() or None
    except (KeyError, OSError):
        return None


def actor_from_env(environ: Mapping[str, str]) -> Actor:
    """The CLI command's actor: `human:<id>` or `agent:<id>` from TROUPE_ACTOR, else the human logged in.

    An empty value is not "unset": anything other than the two forms is a usage error.
    """
    value = environ.get(ACTOR_VARIABLE)
    if value is None:
        return Actor("human", login_name())
    kind, sep, actor_id = value.partition(":")
    for known in _ACTOR_KINDS:
        if kind == known and sep and actor_id:
            return Actor(known, actor_id)
    raise UsageError(f"{ACTOR_VARIABLE}: expected human:<id> or agent:<id>, got {value!r}")


def format_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def now() -> str:
    return format_timestamp(datetime.now(UTC))


def new_change_id() -> str:
    return str(uuid.uuid4())


def for_import() -> Lineage:
    return Lineage(UNKNOWN, "import", now(), None, new_change_id())


def for_file() -> Lineage:
    return Lineage(UNKNOWN, "file", now(), None, new_change_id())


def for_cli(actor: Actor, reason: str | None) -> Lineage:
    return Lineage(actor, "cli", now(), reason, new_change_id())
