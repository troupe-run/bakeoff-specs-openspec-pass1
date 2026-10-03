# troupe — configuration subsystem

troupe runs teams of AI agents. Each project (a *theatre*) keeps its configuration in `.troupe/troupe.yml`
(or `.troupe/troupe.yaml`), which can be split across files with `file:` includes. This repository is the
`troupe config` command line for reading and changing that configuration **without disturbing anything you did
not ask to change**: comments, quoting, indentation and layout stay byte-for-byte as you wrote them.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run troupe config --help
```

## Commands

Every command takes `--theatre DIR` (default: the current directory).

| Command | What it does |
|---|---|
| `troupe config show PATH` | Print the scalar at `PATH` |
| `troupe config set PATH VALUE` | Change or create the value at `PATH` and write it back into the file that holds it |
| `troupe config history [PATH]` | Print the change events as JSON Lines, oldest first, optionally only for `PATH` and below |

`PATH` is dotted (`agents.coder.model`); a numeric segment indexes a list (`tools.0`). `VALUE` is one YAML 1.2 flow
node: `0.2` is a float, `true` a boolean, `abc` and `"0.2"` strings, `{a: 1}` a mapping, `[a, b]` a list, and
`"line one\nline two\n"` a multi-line string.

Example, from the repository root:

```sh
mkdir -p /tmp/demo/.troupe
printf 'agents:\n  coder:\n    model: big   # strongest\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config show agents.coder.model --theatre /tmp/demo        # big
uv run troupe config set agents.coder.model small --theatre /tmp/demo   # model: small # strongest
uv run troupe config set agents.coder.tools '[read, write]' --theatre /tmp/demo
uv run troupe config history agents.coder --theatre /tmp/demo
```

### Includes

A string starting with `file:` includes the named file, relative to the file containing it. A `.yml`/`.yaml` target is
embedded as YAML; any other target's exact text becomes a string value. `set` writes into the file that holds the
value. Setting a text include rewrites the target file (keeping CRLF line endings if it had them). Replacing a
whole YAML include is refused.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | usage error (bad arguments, path syntax or VALUE) |
| 3 | write refused, so no file changed |
| 4 | the configuration cannot be loaded (missing or duplicate config file, invalid YAML, missing include, include cycle) |
| 5 | path not found, or the wrong kind of node for the command |

On failure stdout is empty and stderr names the path or file involved.

### State

Change events are stored with the [`eventsourcing`](https://eventsourcing.readthedocs.io/) library in
`<theatre>/.troupe/events.sqlite`. The first command run against a theatre imports its current values.

Edits made by hand are recorded by *reconciling*: troupe compares the files with the recorded configuration and
records a `set` or `remove` event for each leaf that differs. A formatting-only or comment-only edit records nothing.
`show` and `set` reconcile before doing anything else, so edits made while nothing was running are picked up.
`history` never reconciles: it reports only what has been recorded. Commands against one theatre take turns (a lock
on the `.troupe/` directory), so troupe never records its own write-back a second time.

## Decisions on points the contract leaves open

These are recorded with their reasons in `openspec/changes/archive/2026-10-02-config-load-show-set/design.md`
and `openspec/changes/config-sync-with-files/design.md`:

1. Setting a key under a null or scalar value (e.g. `agents:` with nothing after it) exits 5. Set the parent to a
   mapping first: `set agents '{coder: {model: x}}'`.
2. A digit segment that would need a missing parent created exits 5.
3. An empty or comment-only `troupe.yml` is an empty mapping.
4. A string VALUE starting with `file:` becomes an include. If the result cannot load, the write is refused (exit 3).
5. Mapping and list VALUEs are applied as a diff: unchanged entries keep their bytes, and keys missing from VALUE are
   deleted. Changing or deleting a YAML include through a parent path is refused (exit 3).
6. Import happens on any command whose configuration loads, before the command runs. So does reconciling (except for
   `history`), and its events are kept even if the command then fails with exit 3 or 5.
7. `history PATH` with no matches prints nothing and exits 0. `.inf`/`.nan` appear in JSON as the strings `".inf"`,
   `"-.inf"` and `".nan"`.
8. Anchors, aliases and non-core tags fail to load (exit 4) for now.
9. A new key that would read back as a non-string when written plain (e.g. `true`) is quoted.
10. Every `set` is verified before writing: the edited text is re-read and must give exactly the intended
    configuration, otherwise nothing is written (exit 3).

## Development

```sh
uv run pytest            # tests, including end-to-end runs of `uv run troupe`
uv run mypy              # strict typing
uv run ruff check && uv run ruff format --check
```

Code map: `src/troupe/loader.py` (files and includes), `tree.py` (YAML nodes with source positions), `schema.py`
(core-schema types and printing), `store.py` (event store), `edit/` (byte-surgical write-back:
`plan.py` → `ops.py` → `apply.py`, with `scalars.py`, `blocks.py`, `folded.py` and `text.py` holding the quoting,
block-scalar, folding and layout rules), `commands.py` and `cli.py`.
