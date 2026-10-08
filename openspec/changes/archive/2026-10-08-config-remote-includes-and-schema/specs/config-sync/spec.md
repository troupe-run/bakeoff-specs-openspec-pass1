# Spec Delta

## MODIFIED Requirements

### Requirement: Watch command
`troupe config watch [--theatre DIR]` SHALL run in the foreground. It SHALL load the configuration, import it if this
is the theatre's first command, and reconcile. Only after it is able to observe every later change SHALL it print
exactly one line, `watching <dir>`, to stdout and flush it. `<dir>` is the theatre directory as given by `--theatre`
or `TROUPE_THEATRE`, or the absolute path of the current directory when neither is given. After that line appears,
`watch` SHALL reconcile within 2 seconds of any change to the config file, to any local file it currently includes,
or to `.troupe/troupe.schema.json`. A file
counts as changed when its content changes, when it is replaced (for example by an editor's save-by-rename), or when
it is created or deleted. `watch` SHALL NOT poll URLs: remote content is fetched again by each reconcile, so a
change to it is recorded at the next reconcile that a local change (or another command) causes. `watch` SHALL write
nothing else to stdout. On SIGINT or SIGTERM it SHALL finish any
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

#### Scenario: Edit to the schema file
- **WHEN** `watch` is running on `endpoint: file:e.md\n` with `.troupe/e.md` containing `x\n` and no schema, and `troupe.schema.json` is then created marking `endpoint` as `format: uri`
- **THEN** within 2 seconds `set endpoint` (old `"x\n"`, new `"file:e.md"`) is recorded


## ADDED Requirements

### Requirement: Changes to remote content are reconciled
Reconcile SHALL compare the configuration as loaded with remote content fetched afresh. A change to remote content
since the last reconcile SHALL be recorded like a hand edit to a local file (via `file`, actor unknown).

#### Scenario: Remote content changed
- **WHEN** `<base>` is the URL of a directory served over HTTP, the theatre was imported with `coder: <base>/coder.yaml\n` while `<base>/coder.yaml` served `model: m1\n`, the server then serves `model: m2\n`, and `get coder.model` runs
- **THEN** it prints `m2\n` and `history` lists `set coder.model` (old `"m1"`, new `"m2"`) via `file`
