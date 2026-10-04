# config-lineage Specification

## Purpose

Makes a theatre's configuration history auditable: every recorded event says who made the change, through what
means, when, why, and which other events belong to the same change, and says so explicitly when the answer is
unknown.

## Requirements

### Requirement: Lineage fields on every event
Every event that `history` prints SHALL have, in addition to the fields in config-history:
- `actor`: an object `{"kind": K, "id": I}` where `K` is `"human"`, `"agent"` or `"unknown"`, and `I` is a string or
  `null`. An `unknown` actor SHALL always have `id` `null`.
- `via`: `"import"` for events recorded by importing a theatre, `"file"` for events recorded by reconciling the files
  with the record (hand edits), and `"cli"` for the events a `set` command records for its own change.
- `at`: the UTC time the change was recorded, as an RFC 3339 timestamp of the form `YYYY-MM-DDTHH:MM:SS.ffffffZ` (six
  fractional digits, ending in `Z`).
- `reason`: a string or `null`, as defined in "Reason".
- `change`: a non-empty string that identifies the change the event belongs to, as defined in "Change grouping".

#### Scenario: Fields of an imported event
- **WHEN** the config is `a: 1\n` and `history` is the first command run
- **THEN** its one event has actor `{"kind": "unknown", "id": null}`, via `"import"`, reason `null`, a `change` string, and an `at` matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$`

#### Scenario: Timestamp is UTC and current
- **WHEN** `set a 2` runs between two readings of the UTC clock, and `history` then runs
- **THEN** the `at` of the `set a` event, read as UTC, is no earlier than the first reading and no later than the second, whatever the process's local time zone (`TZ`) is

### Requirement: Actor of a CLI command
The actor of a CLI command SHALL come from the `TROUPE_ACTOR` environment variable. A value `human:<id>` SHALL give
`{"kind": "human", "id": "<id>"}` and `agent:<id>` SHALL give `{"kind": "agent", "id": "<id>"}`, where `<id>` is
everything after the first `:`, kept exactly (it may itself contain `:`) and must not be empty. When `TROUPE_ACTOR` is
not set, the actor SHALL be `{"kind": "human", "id": <login name>}`, the login name of the user running the command,
or `null` when no login name can be determined. Any other value, including the empty string, a kind other than the
lowercase `human` or `agent`, or an empty `<id>`, SHALL be a usage error: exit 2, stdout empty, stderr naming
`TROUPE_ACTOR`. This check SHALL apply to every subcommand and SHALL happen before the configuration is loaded, so an
invalid value imports, reconciles and records nothing. Only a command's own events (a `set`'s `via: "cli"` events)
carry the command's actor.

#### Scenario: Agent actor
- **WHEN** `TROUPE_ACTOR=agent:planner-7` and `set model b` changes `model`
- **THEN** the `set model` event has actor `{"kind": "agent", "id": "planner-7"}` and via `"cli"`

#### Scenario: Human actor
- **WHEN** `TROUPE_ACTOR=human:alice` and `set model b` changes `model`
- **THEN** the `set model` event has actor `{"kind": "human", "id": "alice"}`

#### Scenario: Id containing a colon
- **WHEN** `TROUPE_ACTOR=agent:claude:session-1` and `set model b` changes `model`
- **THEN** the event's actor is `{"kind": "agent", "id": "claude:session-1"}`

#### Scenario: Unset falls back to the login name
- **WHEN** `TROUPE_ACTOR` is not set, the login name of the user running troupe is `bob`, and `set model b` changes `model`
- **THEN** the `set model` event has actor `{"kind": "human", "id": "bob"}`

#### Scenario: Invalid values are usage errors
- **WHEN** `TROUPE_ACTOR` is `robot:x`, `alice`, `human:`, `Human:alice` or the empty string, and `set model b` runs
- **THEN** each run exits 2, stdout is empty, stderr contains `TROUPE_ACTOR`, no file changes, and no event is added

#### Scenario: Invalid value is checked by every subcommand before anything is stored
- **WHEN** `TROUPE_ACTOR=robot:x` and `get`, `show`, `history` or `watch` is the first command run against a theatre
- **THEN** the exit code is 2 and no `.troupe/events.sqlite` is created

### Requirement: Actor and via of imports and hand edits
Events recorded by importing a theatre SHALL have actor `{"kind": "unknown", "id": null}` and via `"import"`.
Events recorded by reconciling SHALL have actor `{"kind": "unknown", "id": null}` and via `"file"`, whichever command
reconciled (`get`, `show`, `set` or `watch`) and whatever `TROUPE_ACTOR` is, because troupe cannot know who edited a
file.

#### Scenario: Import ignores TROUPE_ACTOR
- **WHEN** `TROUPE_ACTOR=agent:a1` and `set model b` is the first command run against a theatre with `model: a\n`
- **THEN** the `import model` event has actor `{"kind": "unknown", "id": null}` and via `"import"`, and the `set model` event has actor `{"kind": "agent", "id": "a1"}` and via `"cli"`

#### Scenario: Hand edit picked up by a command
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `TROUPE_ACTOR=human:alice` runs `set a 3`
- **THEN** the `set a` event with old 1 and new 2 has actor `{"kind": "unknown", "id": null}` and via `"file"`, and the `set a` event with old 2 and new 3 has actor `{"kind": "human", "id": "alice"}` and via `"cli"`

#### Scenario: Hand edit picked up by watch
- **WHEN** `watch` is running and `troupe.yml` is edited by hand from `a: 1\n` to `a: 2\n`
- **THEN** the recorded `set a` event has actor `{"kind": "unknown", "id": null}` and via `"file"`

### Requirement: Reason
`troupe config set PATH VALUE --reason TEXT` SHALL record `TEXT` exactly (including an empty string) as the `reason`
of every event that `set` records for its own change. Every other event SHALL have reason `null`: the events of a
`set` without `--reason`, imports, and reconciled hand edits, including those reconciled by a `set` that was given
`--reason`. `--reason` SHALL be accepted before or after `PATH VALUE`. A `set` that changes nothing SHALL record no
event, with or without `--reason`.

#### Scenario: Reason on every event of the set
- **WHEN** `a` is `1` and `set a "{b: 2, c: 3}" --reason "split a"` runs
- **THEN** the `remove a`, `set a.b` and `set a.c` events each have reason `"split a"`

#### Scenario: No reason
- **WHEN** `set model b` runs without `--reason`
- **THEN** its event has reason `null`

#### Scenario: Reason does not attach to reconciled edits
- **WHEN** the theatre was imported with `a: 1\nb: 1\n`, the file is edited by hand to `a: 2\nb: 1\n`, and `set b 5 --reason "tune"` runs
- **THEN** the `set a` event (old 1, new 2) has reason `null` and the `set b` event (old 1, new 5) has reason `"tune"`

#### Scenario: Unicode and multi-line reason
- **WHEN** `set model b --reason "é⏎second line"` runs
- **THEN** the event's `reason` decodes to `é⏎second line` and its history line contains no raw newline

### Requirement: Change grouping
Each of the following SHALL be one change, with one `change` string shared by all of its events and by no event of
any other change: the import of a theatre; each reconcile that records at least one event (one per command that
reconciles, and one per reconcile that `watch` performs); and the events that one `set` records for its own change.
A `set` that reconciles hand edits first therefore produces two changes: the reconcile's (via `"file"`) and its own
(via `"cli"`). All events of one change SHALL have the same `actor`, `via`, `at` and `reason`. `change` strings SHALL
be unique across theatres and across time, not only within one theatre.

#### Scenario: One set, one change
- **WHEN** `a` is `1` and `set a "{b: 2, c: 3}"` runs
- **THEN** the `remove a`, `set a.b` and `set a.c` events have the same `change`, and it differs from the import's `change`

#### Scenario: Two commands, two changes
- **WHEN** `set a 2` runs and then `set a 3` runs
- **THEN** the two `set a` events have different `change` strings

#### Scenario: Import is one change
- **WHEN** the config is `a: 1\nb: [x, y]\n` and `history` is the first command run
- **THEN** the three `import` events share one `change` and one `at`

#### Scenario: Reconcile is its own change
- **WHEN** the theatre was imported with `a: 1\nb: 1\n`, the file is edited by hand to `a: 2\nb: 2\n`, and `set c 3` runs
- **THEN** the `set a` and `set b` events share one `change`, and the `set c` event has a different `change`

### Requirement: Lineage persists
Lineage SHALL be stored with each event under `<theatre>/.troupe/` and SHALL read back unchanged in every later
process. Listing history SHALL never change any event's lineage.

#### Scenario: Lineage survives restarts
- **WHEN** `TROUPE_ACTOR=agent:a1` runs `set model b --reason r`, and then two separate `history` processes run, the second with `TROUPE_ACTOR=human:other`
- **THEN** both print identical lines, and the `set model` event has actor `{"kind": "agent", "id": "a1"}`, via `"cli"` and reason `"r"`

### Requirement: Events recorded before lineage existed
A theatre whose events were recorded by a version of troupe without lineage SHALL keep loading, and new events SHALL
be added after its old ones. Its old events SHALL NOT be rewritten. `history` SHALL print them with the lineage below, which
marks who made them as unknown: actor `{"kind": "unknown", "id": null}`; via `"import"` for `import` events
and `"file"` for `set` and `remove` events; `at` the time the event was stored; reason `null`; one `change` shared by
all old `import` events, and a `change` of its own for each old `set` or `remove` event.

#### Scenario: A pre-lineage store
- **WHEN** a theatre's `.troupe/events.sqlite` was written by the step-3 version with one import of `a` and one `set a`, and `TROUPE_ACTOR=human:alice` then runs `set a 9`
- **THEN** `history` prints three events; the first two have actor `{"kind": "unknown", "id": null}`, reason `null`, via `"import"` and `"file"` respectively, distinct `change` strings, and a valid `at`; the third has actor `{"kind": "human", "id": "alice"}` and via `"cli"`
