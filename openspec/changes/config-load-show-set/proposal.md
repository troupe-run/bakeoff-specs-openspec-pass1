# Proposal

## Why

troupe projects ("theatres") keep their configuration in hand-edited YAML under `.troupe/`, split across files
with includes. There is no tool yet to read a setting, change one, or see what changed. People review these files
as diffs, so changing a setting must not touch any byte the change does not require. This is step 1 of the
configuration subsystem: the repository is empty, and everything later builds on it.

## What Changes

- New Python 3.12+ project managed with uv, exposing a `troupe` console script (`uv run troupe config …`).
- Configuration loading: find `<theatre>/.troupe/troupe.yml` or `.yaml`, parse YAML 1.2 (core schema), and resolve
  `file:` includes recursively (YAML includes are embedded, other files become text), detecting missing targets and
  cycles.
- An event-sourced record of the configuration built with the `eventsourcing` library, persisted under
  `<theatre>/.troupe/`. Each change is stored as one event per leaf: `import`, `set` and `remove`.
- `troupe config show PATH`: print a scalar's value.
- `troupe config set PATH VALUE`: change, create or append a value and write it back **byte-surgically** into
  whichever file holds it. Quoting style, block scalars (literal and folded, including re-wrapping), flow
  collections, the placement of new entries relative to trailing comments, and end-of-line comment columns all
  follow the contract.
- `troupe config history [PATH]`: print events as JSON Lines.
- Fixed exit codes (0/2/3/4/5), with an empty stdout and a stderr message naming the path or file on every failure.

## Capabilities

### New Capabilities
- `config-cli`: invocation, `--theatre`, path syntax, parsing `VALUE` on the command line, printing scalars, exit codes
  and error reporting, and the rule that state is kept only under `.troupe/`.
- `config-loading`: locating the config file, YAML 1.2 core-schema loading, and `file:` includes (YAML and text,
  recursive, missing target and cycle detection).
- `config-show`: `troupe config show PATH`.
- `config-set`: `troupe config set PATH VALUE`: which file a change goes to, how it is written byte-surgically, and
  when a write is refused.
- `config-history`: the event-sourced change record (import, set and remove events per leaf) and
  `troupe config history [PATH]`.

### Modified Capabilities
- None (greenfield).

## Impact

- New code: `pyproject.toml`, `uv.lock`, `src/troupe/…` and `tests/…`.
- New runtime dependencies: `eventsourcing` (event store and projection, using its SQLite persistence) and
  `ruamel.yaml` (a YAML parser that reports source positions). Dev dependencies: `pytest`, `mypy`, `ruff`.
- On-disk state: an SQLite event database inside `<theatre>/.troupe/`. User files change only when a `set`
  requires it.
