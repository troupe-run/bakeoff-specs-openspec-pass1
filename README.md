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
| `troupe config get PATH` | Print the scalar at `PATH` (a mapping or list exits 5: use `show`) |
| `troupe config show [PATH] [--sources]` | Print the value at `PATH`, or the whole configuration, as YAML with includes resolved; `--sources` says which file each value comes from |
| `troupe config set PATH VALUE` | Change or create the value at `PATH` and write it back into the file that holds it |
| `troupe config history [PATH]` | Print the change events as JSON Lines, oldest first, optionally only for `PATH` and below |
| `troupe config watch` | Record hand edits to the files as they happen, until Ctrl-C (SIGINT) or SIGTERM |

`PATH` is dotted (`agents.coder.model`); a numeric segment indexes a list (`tools.0`). `VALUE` is one YAML 1.2 flow
node: `0.2` is a float, `true` a boolean, `abc` and `"0.2"` strings, `{a: 1}` a mapping, `[a, b]` a list, and
`"line one\nline two\n"` a multi-line string.

Example, from the repository root:

```sh
mkdir -p /tmp/demo/.troupe
printf 'agents:\n  coder:\n    model: big   # strongest\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config get agents.coder.model --theatre /tmp/demo         # big
uv run troupe config set agents.coder.model small --theatre /tmp/demo   # model: small # strongest
uv run troupe config set agents.coder.tools '[read, write]' --theatre /tmp/demo
uv run troupe config history agents.coder --theatre /tmp/demo
```

### Watching for hand edits

`troupe config watch` runs in the foreground. Once it is watching, it prints one line, `watching <dir>`. From then
on, within 2 seconds of any change to `troupe.yml` or a file it includes (including files included by a later edit),
it reconciles (see [State](#state)). It prints nothing else to stdout. If an edit leaves the configuration unloadable
(say, half-typed YAML), it reports this once on stderr and carries on, then picks up the change once the files load
again. SIGINT or SIGTERM stop it with exit code 0.

```sh
uv run troupe config watch --theatre /tmp/demo &        # watching /tmp/demo
sed -i.bak 's/small/tiny/' /tmp/demo/.troupe/troupe.yml && rm /tmp/demo/.troupe/troupe.yml.bak
sleep 2; uv run troupe config history agents.coder.model --theatre /tmp/demo   # ... "old": "small", "new": "tiny"
kill %1
```

A `set` made while `watch` runs records exactly its own events. Its write-back is not picked up again.

### Showing sections and where values come from

`get` prints one value. `show` prints a value the same way. A mapping or list, or with `PATH` omitted the whole
configuration, is printed as block YAML. Includes are resolved: an included YAML file appears in place of its
`file:` string, and a text include's content is a literal block (`|`). The output is a canonical layout of the
values, not a copy of your files: comments are dropped, `0x1F` shows as `31`, and quoting follows the same rule `set`
uses for new values. With `--sources`, every line that holds a scalar ends with `# from <file>`, relative to the
theatre:

```sh
mkdir -p /tmp/demo/.troupe/agents
printf 'model: big\nprompt: file:coder.md\n' > /tmp/demo/.troupe/agents/coder.yaml
printf 'You write code.\n' > /tmp/demo/.troupe/agents/coder.md
printf 'name: demo\nagents:\n  coder: file:agents/coder.yaml\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config show --sources --theatre /tmp/demo
# name: demo # from .troupe/troupe.yml
# agents:
#   coder:
#     model: big # from .troupe/agents/coder.yaml
#     prompt: | # from .troupe/agents/coder.md
#       You write code.
```

Until step 3, `show PATH` refused mappings and lists with exit 5. Scripts that relied on that should call `get`, whose
output and exit codes are the same as the old `show PATH`.

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
`get`, `show` and `set` reconcile before doing anything else, so edits made while nothing was running are picked up.
`history` never reconciles: it reports only what has been recorded. Commands against one theatre take turns (a lock
on the `.troupe/` directory), so troupe never records its own write-back a second time.

## Decisions on points the contract leaves open

These are recorded with their reasons in `openspec/changes/archive/2026-10-02-config-load-show-set/design.md`,
`openspec/changes/archive/2026-10-03-config-sync-with-files/design.md` and the `config-get-and-show` design.md:

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
11. `watch` on a theatre that cannot be loaded exits 4 without printing its line. Once it is running, a load failure
    does not stop it: it reports the error once on stderr and resumes when the files load again.
12. `watch` prints only its `watching <dir>` line to stdout. `<dir>` is the theatre as given (`--theatre` or
    `TROUPE_THEATRE`), not resolved, or the absolute current directory when neither is given.
13. Reconcile records removes in the order they were recorded, then sets in the files' document order.
14. `watch` reads the watched files every 0.2 s and reconciles once a change has read the same twice in a row. That
    way it does not record a file that an editor has emptied halfway through a save.
15. `show PATH --sources` on a scalar prints it as YAML with the comment (`big # from …`), not in the
    `get` form, so the source can be shown.
16. The source comment is ` # from <file>`, on the `|` line for literal blocks. Lines holding `{}` or `[]` get none.
    `<file>` has `..` folded away and symlinks are not resolved; a file outside the theatre gets a `../` path.
17. `show` writes every multi-line string as a literal block when one can hold it exactly, otherwise double-quoted.
    Lists under a key are indented two spaces, and list items that are collections use the compact `- key: v` form.
18. `get` reconciles before reading, like `show`.

## Development

```sh
uv run pytest            # tests, including end-to-end runs of `uv run troupe`
uv run mypy              # strict typing
uv run ruff check && uv run ruff format --check
```

Code map: `src/troupe/loader.py` (files and includes), `tree.py` (YAML nodes with source positions), `schema.py`
(core-schema types and printing), `store.py` (event store), `edit/` (byte-surgical write-back:
`plan.py` → `ops.py` → `apply.py`, with `scalars.py`, `blocks.py`, `folded.py` and `text.py` holding the quoting,
block-scalar, folding and layout rules), `sync.py` (reconcile), `commands.py` (subcommands, the theatre lock
and the `watch` loop) and `cli.py`.
