# Spec Delta

## Purpose

Keeps a theatre's recorded configuration in step with its hand-edited files. Edits are picked up as they happen
while `troupe config watch` runs, and edits made while nothing was running are picked up by the next command.
troupe's own write-backs are never picked up as new changes.

## ADDED Requirements

### Requirement: Reconcile
To reconcile, troupe SHALL load the configuration files as they are now and compare their leaves (as defined in
config-history) with the recorded configuration, which is the leaves as left by every recorded event. It SHALL record,
atomically, one `remove` event (`old` the recorded value, `new` null) for each recorded leaf whose path is no longer
in the files, in recorded order, followed by one `set` event for each leaf in the files whose path is not recorded
(`old` null) or whose value differs from the recorded value, in document order. Values SHALL be compared strictly: a
difference of type (such as `1`, `1.0`, `true` and `"1"`) is a difference, and NaN equals NaN. An edit that changes
no leaf, such as reformatting, requoting with the same value, reordering mapping keys, or changing comments, SHALL record
nothing. A reconcile that finds no difference SHALL record nothing.

#### Scenario: Hand edit becomes a set event
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `show a` runs
- **THEN** one event is added: op `set`, path `a`, old `1`, new `2`

#### Scenario: Removed and added leaves
- **WHEN** the theatre was imported with `a: 1\nb: 2\n` and the file is edited by hand to `b: 2\nc: [x]\n`
- **THEN** the next reconcile adds `remove a` (old 1, new null) and then `set c.0` (old null, new `"x"`)

#### Scenario: Scalar replaced by a mapping by hand
- **WHEN** the theatre was imported with `a: 1\n` and the file is edited by hand to `a:\n  b: 2\n`
- **THEN** the next reconcile adds `remove a` and then `set a.b` (old null, new 2)

#### Scenario: Type change is a change
- **WHEN** the theatre was imported with `a: 1\n` and the file is edited by hand to `a: '1'\n`
- **THEN** the next reconcile adds `set a` with old `1` and new `"1"`

#### Scenario: Formatting-only and comment-only edits
- **WHEN** the theatre was imported with `a: 1\nb: x\n` and the file is edited by hand to `# note\nb:   "x"   # c\na: 1\n`
- **THEN** the next reconcile adds no event

#### Scenario: Edit inside an included file
- **WHEN** `prompt` is `file:prompt.md`, the theatre was imported, and `prompt.md` is edited by hand from `Hi\n` to `Bye\n`
- **THEN** the next reconcile adds `set prompt` with old `"Hi\n"` and new `"Bye\n"`

### Requirement: Commands reconcile first
`show`, `set` and `watch` SHALL reconcile after the configuration loads (and, on a theatre's first command, after the
import) and before doing their own work, so they pick up edits made while nothing was running. The reconcile's events
SHALL persist even if the command then exits 3 or 5. `history` SHALL never reconcile: it reports only what has been
recorded. Nothing SHALL be reconciled when the command line is invalid (exit 2) or the configuration cannot be loaded
(exit 4).

#### Scenario: set after a hand edit
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `set a 3` runs
- **THEN** two events are added, in this order: `set a` (old 1, new 2), then `set a` (old 2, new 3)

#### Scenario: Reconcile persists when the command fails
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `show nope` runs and exits 5
- **THEN** a later `history` includes `set a` (old 1, new 2)

#### Scenario: history does not reconcile
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `history` runs
- **THEN** no event mentions the value 2. After `show a` runs, `history` lists `set a` (old 1, new 2)

#### Scenario: Invalid command line or unloadable configuration records nothing
- **WHEN** the file was edited by hand after import, and then `set a "[x"` (exit 2) runs, or the file is made invalid YAML and `show a` (exit 4) runs
- **THEN** no event is added

### Requirement: Watch command
`troupe config watch [--theatre DIR]` SHALL run in the foreground. It SHALL load the configuration, import it if this
is the theatre's first command, and reconcile. Only after it is able to observe every later change SHALL it print
exactly one line, `watching <dir>`, to stdout and flush it. `<dir>` is the theatre directory as given by `--theatre`
or `TROUPE_THEATRE`, or the absolute path of the current directory when neither is given. After that line appears,
`watch` SHALL reconcile within 2 seconds of any change to the config file or to any file it currently includes. A file
counts as changed when its content changes, when it is replaced (for example by an editor's save-by-rename), or when
it is created or deleted. `watch` SHALL write nothing else to stdout. On SIGINT or SIGTERM it SHALL finish any
reconcile in progress, then exit 0 with nothing written to stderr. If the configuration cannot be loaded when `watch`
starts, it SHALL exit 4 like any other command, without printing the line.

#### Scenario: Ready line
- **WHEN** `watch --theatre /tmp/t` is started on a loadable theatre
- **THEN** its stdout is the line `watching /tmp/t\n`, flushed while the process keeps running

#### Scenario: Live edit is reconciled within 2 seconds
- **WHEN** `watch` has printed its line and `troupe.yml` is then edited by hand from `a: 1\n` to `a: 2\n`
- **THEN** within 2 seconds `history` lists `set a` (old 1, new 2), and running `history` does not cause it

#### Scenario: Edit to an included file
- **WHEN** `watch` is running and an included file is edited by hand so that a leaf changes
- **THEN** within 2 seconds the leaf's `set` event is recorded

#### Scenario: Save by rename
- **WHEN** `watch` is running and an editor saves `troupe.yml` by writing a new file and renaming it over the old one
- **THEN** the change is reconciled within 2 seconds

#### Scenario: Comment-only live edit
- **WHEN** `watch` is running and only a comment in `troupe.yml` is changed
- **THEN** no event is recorded

#### Scenario: Stopping
- **WHEN** `watch` is running and receives SIGINT, or separately SIGTERM
- **THEN** it exits 0, its stdout is exactly `watching <dir>\n`, and its stderr is empty

#### Scenario: Unloadable at start
- **WHEN** `watch` starts on a directory with no `.troupe/troupe.yml` or `.yaml`
- **THEN** it exits 4, stdout is empty, stderr names `troupe.yml`, and no file or directory is created

### Requirement: Unloadable configuration while watching
When a change makes the configuration impossible to load (for example invalid YAML half-way through an edit, or a
missing include target), `watch` SHALL record nothing, write one message naming the file involved to stderr, and keep
running. It SHALL NOT repeat the message until the error changes. When a later change makes the configuration
loadable again, `watch` SHALL reconcile within 2 seconds of that change.

#### Scenario: Broken then fixed
- **WHEN** `watch` is running on `a: 1\n`, the file becomes `a: [1\n`, and then becomes `a: 2\n`
- **THEN** stderr gains a message naming `troupe.yml`, `watch` is still running, and within 2 seconds of the fix `set a` (old 1, new 2) is recorded with no event in between

### Requirement: troupe's own write-backs are not reconciled again
Commands against the same theatre SHALL NOT interleave their reads of the files, their writes to the files and their
recording of events. A `set` that runs while `watch` runs SHALL add exactly the events it would add if `watch` were not
running, and its write-back SHALL cause no further events, however soon `watch` notices the written files.

#### Scenario: set while watch runs
- **WHEN** `watch` is running on `model: a\n` and `set model b` runs
- **THEN** after more than 2 seconds the only event added since `watch` printed its line is `set model` (old `"a"`, new `"b"`)

#### Scenario: set into an included file while watch runs
- **WHEN** `watch` is running and `set agents.coder.model m2` writes into the included `agents/coder.yaml`
- **THEN** after more than 2 seconds exactly one event has been added, the `set`'s own

### Requirement: Includes added by hand are followed
When a hand edit adds an include, reconcile SHALL follow it like any other include: each leaf of the included content
SHALL be recorded as a `set` event (and a leaf it replaces as a `remove` event). From then on `watch` SHALL also watch
the newly included file. When an include is removed by hand, its leaves SHALL be recorded as `remove` events and
`watch` SHALL stop treating the file as part of the configuration.

#### Scenario: New YAML include
- **WHEN** `watch` is running on `agents: {}\n`, `agents/tester.yaml` containing `model: t1\n` exists, and `troupe.yml` is edited to `agents:\n  tester: file:agents/tester.yaml\n`
- **THEN** within 2 seconds `set agents.tester.model` (old null, new `"t1"`) is recorded

#### Scenario: Newly included file is watched
- **WHEN** after that, `agents/tester.yaml` is edited by hand to `model: t2\n`
- **THEN** within 2 seconds `set agents.tester.model` (old `"t1"`, new `"t2"`) is recorded

#### Scenario: New include added while nothing runs
- **WHEN** no command is running, a hand edit adds `prompt: file:prompt.md`, and `show prompt` runs
- **THEN** `history` lists `set prompt` whose new value is the text of `prompt.md`
