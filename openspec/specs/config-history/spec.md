# config-history Specification

## Purpose

Keeps a durable, per-leaf record of how a theatre's configuration has changed (its initial import and every `set`)
and lets users list that record, optionally filtered to a path.

## Requirements

### Requirement: Durable event record under `.troupe/`
The configuration's events SHALL be stored under `<theatre>/.troupe/` and SHALL persist between commands. Each
event SHALL concern one leaf. A leaf is a scalar (including null and a text-include string, whose value is the
target's text) at a dotted path, and list items are addressed as `list.0`, `list.1`, …. Empty mappings and lists have
no leaves.

#### Scenario: Events survive between commands
- **WHEN** `set model b` runs and then a separate `history` process runs
- **THEN** the second process prints the `set` event

### Requirement: Import on first command
The first command run against a theatre whose configuration loads SHALL import it before doing its own work,
recording one `import` event per leaf in document order with `old` null. Every subcommand imports, including
`history`, and the import persists even if the command then exits 3 or 5. A theatre is imported at most once. Later
hand edits to the files SHALL NOT generate events (importing is not reconciling). Nothing SHALL be imported or stored
when the configuration cannot be loaded or the command line is invalid.

#### Scenario: First history imports
- **WHEN** the config is `a: 1\nb: [x, y]\n` and `history` is the first command run
- **THEN** stdout is three JSON lines with seq 1, 2, 3, op `import`, paths `a`, `b.0`, `b.1`, old null, and new `1`, `"x"`, `"y"`

#### Scenario: Import happens once
- **WHEN** `history` runs twice
- **THEN** both runs print the same import events and no new events are added

#### Scenario: Hand edits are not reconciled
- **WHEN** the theatre was imported with `a: 1`, the user then edits it to `a: 2` by hand, and `history` runs
- **THEN** no event mentions the value 2

#### Scenario: Empty configuration
- **WHEN** the config file is empty and `history` runs
- **THEN** stdout is empty, the exit code is 0, and the theatre counts as imported

### Requirement: Events recorded by set
A `set` SHALL record, atomically and only after the files are written, one `remove` event (`new` null) for each leaf
that no longer exists, in old document order, followed by one `set` event for each leaf whose value it changes or
creates, in new document order. `old` SHALL be the leaf's value as loaded from the files just before the `set` (null
for a created leaf). A `set` that changes nothing, or that fails, SHALL record nothing.

#### Scenario: Changing a scalar
- **WHEN** `model` is `a` and `set model b` runs
- **THEN** one event is added: op `set`, path `model`, old `"a"`, new `"b"`

#### Scenario: Old value comes from the files
- **WHEN** the theatre was imported with `a: 1`, the user edits it by hand to `a: 2`, and `set a 3` runs
- **THEN** the added event has old `2` and new `3`

#### Scenario: Scalar replaced by a mapping
- **WHEN** `a` is `1` and `set a "{b: 2, c: 3}"` runs
- **THEN** the added events are `remove a` (old 1, new null), then `set a.b` (old null, new 2), then `set a.c` (old null, new 3)

#### Scenario: Unchanged leaves are not recorded
- **WHEN** `a` is `{b: 1, c: 2}` and `set a "{b: 1, c: 5}"` runs
- **THEN** exactly one event is added, for `a.c`

#### Scenario: Refused set records nothing
- **WHEN** a `set` exits 3
- **THEN** no `set` or `remove` event is added

### Requirement: Listing history
`troupe config history [PATH]` SHALL print events as JSON Lines, oldest first, one compact JSON object per line. Each
object SHALL have at least `seq` (an integer from 1, increasing by 1), `op` (`import`, `set` or `remove`), `path`
(dotted), `old` and `new` (JSON values: strings, numbers, booleans, null). Non-finite floats SHALL be written as the
strings `".inf"`, `"-.inf"` and `".nan"`. With `PATH`, only events whose path equals `PATH` or starts with `PATH.` SHALL
be printed, keeping their original `seq`. A `PATH` that matches nothing SHALL print nothing and exit 0.

#### Scenario: Filter by prefix
- **WHEN** the events have paths `agents.coder.model`, `agents.coderx`, and `model`, and `history agents.coder` runs
- **THEN** only the `agents.coder.model` event is printed

#### Scenario: Unicode and multi-line values
- **WHEN** a leaf's value is `é⏎`
- **THEN** its event line is valid JSON whose `new` decodes to `é⏎`, and the line contains no raw newline
