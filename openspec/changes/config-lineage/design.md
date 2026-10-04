# Design

## Context

See proposal.md for the motivation and `specs/` for the exact behaviour. What exists today (after step 3):

- `store.py` has one aggregate per theatre, `TheatreConfig`, with events declared by the `@event("…")` decorator:
  `Created`, `Imported(path, new)`, `LeafSet(path, old, new)` and `LeafRemoved(path, old)`. They are stored by
  `eventsourcing` 9.5 in `<theatre>/.troupe/events.sqlite` under topics such as `troupe.store:TheatreConfig.LeafSet`.
  `ConfigStore.import_leaves(leaves)` saves `Created` plus the imports in one save; `record(changes)` saves a batch of
  `set`/`remove` events in one save. `history()` yields `Record(seq, Change)`.
- Events are written in three places, each already its own atomic save:
  1. the import in `commands.theatre_session` (first command only);
  2. `sync.reconcile`, called by `theatre_session` for `get`, `show`, `set` and `watch` (and on each `watch` reconcile);
  3. `commands.set_value`, after the write-back, for the `set`'s own changes.
- `cli.run` parses arguments and dispatches; `UsageError` maps to exit 2 in `errors.py`. Argument and path errors are
  raised before `theatre_session` runs, which is why exit 2 creates no state. `TROUPE_THEATRE` is read in `cli.run`.
- `eventsourcing` supports versioned events: an event class with `class_version = 2` and a static
  `upcast_v1_v2(state)` has older stored state passed through the upcaster when it is read. The stored state includes
  `originator_version` and `timestamp` (an aware UTC datetime set when the event was triggered).

## Goals / Non-Goals

**Goals:**
- Each lineage decision (actor syntax, login fallback, clock and format, change ids, what is "unknown") lives in one
  module, `lineage.py`.
- Each of the three write sites gets its lineage from one call that matches its meaning. A batch of events cannot get
  more than one lineage, so the "one change, one id" rule cannot be broken by accident.
- Old event stores keep working without being rewritten.

**Non-Goals:**
- Filtering or grouping `history` by actor, change or time. History output stays one event per line.
- Authenticating actors. `TROUPE_ACTOR` is trusted as given: it records a claim, not a proof.
- Recording who edited a file by hand (for example from file ownership or git). The contract says it is unknown.

## Decisions

### D1. A `lineage.py` module holds every lineage decision
```python
ActorKind = Literal["human", "agent", "unknown"]
Via = Literal["import", "cli", "file"]

@dataclass(frozen=True)
class Actor: kind: ActorKind; id: str | None
UNKNOWN = Actor("unknown", None)

@dataclass(frozen=True)
class Lineage: actor: Actor; via: Via; at: str; reason: str | None; change: str

def actor_from_env(environ: Mapping[str, str]) -> Actor      # UsageError naming TROUPE_ACTOR on a bad value
def login_name() -> str | None
def now() -> str                                              # "YYYY-MM-DDTHH:MM:SS.ffffffZ"
def new_change_id() -> str
def for_import() -> Lineage                                   # UNKNOWN, "import", now(), None, new id
def for_file() -> Lineage                                     # UNKNOWN, "file",   now(), None, new id
def for_cli(actor: Actor, reason: str | None) -> Lineage      # actor,   "cli",    now(), reason, new id
```
The three constructors are the only way code outside the module makes a `Lineage`. Each call is one change: a fresh id
and one timestamp. The timestamp is taken when the change is built, just before its single save.

### D2. `TROUPE_ACTOR` syntax
`actor_from_env` returns `Actor("human", login_name())` when the variable is absent. Otherwise the value is split at the
first `:`. The kind must be exactly `human` or `agent`, and the rest (the id, kept exactly, colons included) must be
non-empty. Anything else raises `UsageError("TROUPE_ACTOR: expected human:<id> or agent:<id>, got '<value>'")`.
- An empty value is an error, not "unset". The contract says "unset" for the fallback and "anything else" for exit 2.
  This differs from `TROUPE_THEATRE`, where empty means unset, because a mistyped actor in an audit trail is worse than
  a refused command.
- Kinds are case-sensitive. The contract spells them in lowercase and they are echoed into the history as `kind`.
- Whitespace in the id is kept: troupe does not reinterpret what the caller claims.

`cli.run` calls `actor_from_env(os.environ)` right after `parse_args`, for every subcommand. So an invalid value exits 2
before anything is loaded or recorded, like any other usage error. Only `set` uses the result. Checking it for all
commands means a bad value is reported the first time it is used, not later when an agent first tries to `set`.

*Alternative:* check only in `set`. Rejected: read commands import and reconcile, and a misconfigured agent would
not hear about its typo until it wrote.

### D3. Login name
`login_name()` returns `getpass.getuser()`, which reads `LOGNAME`, `USER`, `LNAME`, `USERNAME`, then the password
database. On Python 3.12 it raises `KeyError` (and on later versions `OSError`) when none is available, for example
in a container with an unknown uid. Then `login_name()` returns `None`, and the actor is `{"kind": "human", "id": null}`:
the kind is known from the contract, the id genuinely is not. `os.getlogin()` is not used, because it fails
without a controlling terminal, which is how agents run troupe.

### D4. Timestamps
`now()` is `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")`. It always has six fractional digits, so the format is
fixed-width and tests can match it exactly. It is computed from an aware UTC datetime, so `TZ` cannot affect it. The
string is stored in the event as is. It is not derived from `eventsourcing`'s own event `timestamp`, which is per
event (it differs within one batch) and whose time zone depends on the `TZINFO_TOPIC` environment variable.

### D5. Change ids
`new_change_id()` is `str(uuid.uuid4())`. UUID4 is unique across processes, machines and theatres without coordination
or a counter in the store. That is the conservative reading of "no two commands share one". Ids are opaque, and
history order comes from `seq`.

*Alternative:* a per-theatre counter. Rejected: it would need a store read inside the lock for every change, and ids
would repeat across theatres.

### D6. Storage: lineage on every leaf event, event classes at version 2
Each of `Imported`, `LeafSet` and `LeafRemoved` gains the attributes `actor_kind`, `actor_id`, `via`, `at`, `reason` and
`change`, as plain strings or null. These are types the default transcoder already stores, so no custom transcoding
is needed. The events are declared as explicit nested classes of `TheatreConfig` with the **same names**, so the
stored topics `troupe.store:TheatreConfig.LeafSet` and the others still resolve. Each has `class_version = 2` and a
`upcast_v1_v2` (D7). They are triggered with `self.trigger_event(...)` or via `@event(LeafSet)`, whichever mypy accepts
more cleanly. The projection logic is unchanged. `Created` is left at version 1. It carries no leaf, and the import's
lineage is on its `Imported` events.

`ConfigStore.import_leaves(leaves, lineage)` and `record(changes, lineage)` take one `Lineage` for the batch.
`history()` yields `Record(seq, change, lineage)`. Lineage is a separate field from `Change`, so the `Change` values
that `diff_leaves` and `compute_set` produce stay untouched. Write sites:
- `theatre_session`: `store.import_leaves(..., lineage.for_import())`
- `sync.reconcile(config, store)`: `store.record(changes, lineage.for_file())`, built only when there are changes
- `set_value(theatre, path, value, actor, reason)`: `store.record(result.changes, lineage.for_cli(actor, reason))`

*Alternative:* one separate `ChangeRecorded` event per change holding the lineage, with leaf events referring to it.
It is more normalised, but `history` would have to join the two and the filter would get harder. Rejected: there is
no size pressure, and one self-contained event per line matches the output.

### D7. Events stored before step 4
`upcast_v1_v2(state)` fills in the lineage of a version-1 event in one place, without guessing an actor:
- `actor_kind="unknown"`, `actor_id=None`, `reason=None`;
- `at` = the stored `state["timestamp"]`, converted to UTC and formatted like `now()`. It is when the event was saved, which
  is true for all three kinds;
- `via`: `"import"` for `Imported`. For `LeafSet` and `LeafRemoved`, step-3 stores do not record whether the event came from
  `set` or from a reconcile. The contract's values have no "unknown", and `"cli"` would be inconsistent with an
  unknown actor (CLI events always have a known actor kind). So these are reported as `"file"`, the only value that
  pairs with an unknown actor.
- `change`: `"legacy-import"` for every old `Imported` event (the import is known to be a single change), and
  `"legacy-<originator_version>"` for each old `LeafSet`/`LeafRemoved`. Old batches cannot be reconstructed, so each
  old event is reported as its own change rather than wrongly merged with others. These strings cannot collide
  with UUID4 ids.

Nothing is rewritten on disk. Upcasting happens on every read, so the store stays exactly as step 3 left it, plus
new events. This is flagged for product-owner review below.

### D8. CLI and output
- `set` gets `--reason` (`metavar="TEXT"`, default `None`). argparse accepts it before or after the positionals. A value
  starting with `-` must be written `--reason=-x`, which is standard argparse.
- `history` adds the keys after the existing ones, in the order `actor`, `via`, `at`, `reason`, `change`, with
  `actor` as `{"kind": …, "id": …}`. It still uses `ensure_ascii=False`, so a multi-line reason is escaped and stays on
  one line.

### D9. Testing
- `tests/conftest.py`: an autouse fixture deletes `TROUPE_ACTOR` from the environment (and sets `LOGNAME`/`USER` to a
  known name), so the developer's own environment cannot change test results. The smoke tests' `troupe()` helper
  passes an explicit environment for the same reason.
- `tests/test_lineage.py`, through the real CLI (`main`) on real theatres, covering each config-lineage scenario:
  - actor kinds, an id containing a colon, the login fallback;
  - every invalid value, including the empty string, gives exit 2 with `TROUPE_ACTOR` on stderr and no `events.sqlite`,
    for each subcommand;
  - via for import, reconcile-by-command, reconcile-by-`watch` (in `tests/test_watch.py`, which already runs watch)
    and `set`;
  - `at` format and bounds, with `TZ` set to a non-UTC zone and `time.tzset()`;
  - reason, including empty and multi-line reasons, and that it does not attach to reconciled events;
  - change grouping, including the reconcile-then-set case;
  - persistence across processes.
- Unit tests for `actor_from_env` and `login_name`. For "no login name", the test removes `LOGNAME`/`USER`/`LNAME`/`USERNAME`
  and makes `pwd.getpwuid` raise `KeyError`, the real failure shape on 3.12.
- Pre-step-4 store: a real `events.sqlite` produced by the step-3 code (commit `4ef5d76`, checked out in a temporary
  git worktree and run with `uv run`) is committed as `tests/fixtures/step3-events.sqlite` with its `troupe.yml`. The
  test copies them into a theatre, runs `set` with `TROUPE_ACTOR`, and checks the spec's scenario. A script, or the
  steps in the test module's docstring, records how the fixture was made.
- Existing `tests/test_store.py` calls pass a `Lineage`. One test is added: lineage round-trips through storage with
  types intact (null id, null reason, empty-string reason).
- `tests/test_history.py` gains the "every line carries lineage" check, with and without `PATH`.

## Risks / Trade-offs

- [`via: "file"` on pre-step-4 `set` events may be wrong, since some were CLI sets] → this cannot be known from step-3
  data. The actor is `unknown`, which is honest. It is documented in the README and below for product-owner review.
  It affects only stores written before step 4.
- [`TROUPE_ACTOR` is self-asserted, so anyone can claim any id] → this is the contract. The README says lineage records
  claims and is not access control.
- [An empty `TROUPE_ACTOR` now fails every command (exit 2), where a user might expect it to mean unset] → this is the
  contract's "anything else". The message says what is expected. `unset TROUPE_ACTOR` is the fix.
- [Event classes move from decorator-generated to explicit] → topic names are kept, and the pre-step-4 fixture test
  proves that old stores still load.

## Migration Plan

No user action is needed. Old stores are read through the upcaster (D7), and new events are written at version 2. To roll
back, the step-3 code cannot read version-2 events: its event classes have no `class_version` and would reject the
extra attributes. So rolling back after step-4 events exist means removing `.troupe/events.sqlite`. troupe then
re-imports from the files on the next command, and history before that point is lost. This is noted in the README.

## Decisions on points the contract leaves open (for product-owner review)

1. An invalid `TROUPE_ACTOR` is rejected by every subcommand, not only `set`, before anything is stored (D2).
2. An empty `TROUPE_ACTOR` is invalid (exit 2), not "unset". Kinds are lowercase only. Ids are kept exactly and may
   contain `:` (D2).
3. When no login name can be found, the actor is `{"kind": "human", "id": null}` (D3).
4. `at` has microsecond precision (`2026-10-04T09:15:02.481233Z`). Every event of one change has the same `at` (D4).
5. Change ids are UUID4 strings (D5). A `set` that first reconciles hand edits produces two changes: the reconcile
   (`file`) and its own (`cli`). The contract says a change identifies "the command (or file reconcile, or import)".
6. `--reason` applies only to the `set`'s own events. An empty reason is stored as `""`, not `null`.
7. Pre-step-4 events: actor unknown, `via` `"import"` or `"file"`, `at` from the stored event time, `change`
   `legacy-import` or `legacy-<n>` (D7).
