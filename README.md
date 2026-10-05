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
| `troupe config set PATH VALUE [--reason TEXT]` | Change or create the value at `PATH` and write it back into the file that holds it; `--reason` is recorded in the history |
| `troupe config history [PATH]` | Print the change events with their [lineage](#lineage) as JSON Lines, oldest first, optionally only for `PATH` and below |
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
uv run troupe config set agents.coder.tools '[read, write]' --reason "coder needs files" --theatre /tmp/demo
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

### Lineage

Every history event says who made the change, how, when, why, and what else changed with it:

```sh
TROUPE_ACTOR=agent:planner-7 uv run troupe config set agents.coder.model huge --reason "harder tasks" --theatre /tmp/demo
uv run troupe config history agents.coder.model --theatre /tmp/demo | tail -1
# {"seq": …, "op": "set", "path": "agents.coder.model", "old": "big", "new": "huge",
#  "actor": {"kind": "agent", "id": "planner-7"}, "via": "cli", "at": "2026-10-04T09:15:02.481233Z",
#  "reason": "harder tasks", "change": "3f0c…"}      (one line in the real output)
```

| Field | Meaning |
|---|---|
| `actor` | `{"kind": "human" \| "agent" \| "unknown", "id": …}`: who made the change |
| `via` | `"cli"` (a `set`), `"file"` (a hand edit, picked up by reconciling) or `"import"` (the first command) |
| `at` | when the change was recorded: RFC 3339 UTC, always six fractional digits and a trailing `Z` |
| `reason` | the text given with `set --reason TEXT` (kept exactly, even if empty), else `null` |
| `change` | an id shared by every event of one change and by no other event |

The actor of a `set` comes from `TROUPE_ACTOR`: `human:<id>` or `agent:<id>` (the id is everything after the first
`:`). When the variable is unset, the actor is the human logged in (`{"kind": "human", "id": "<login name>"}`, or
`null` for the id if no login name can be found). Any other value, including an empty one, makes every command exit 2
before it reads or records anything. `TROUPE_ACTOR` records a claim, not a proof: it is not access control.

troupe cannot know who edited a file or who wrote the configuration before the import, so those events always have
actor `{"kind": "unknown", "id": null}`, whatever `TROUPE_ACTOR` says. A `set` that first picks up hand edits
therefore records two changes: the hand edits (`file`, unknown actor, no reason) and its own (`cli`). Each `watch`
reconcile is one change.

Event stores written before lineage (step 3) keep working and are not rewritten. Their events are shown with actor
`unknown`, `at` the time they were stored, reason `null`, via `import` or `file` (step 3 did not record which `set`
events came from the command line), and change `legacy-import` (all old imports) or `legacy-<seq>` (each other old
event). Going back to step-3 code after lineage events exist means deleting `.troupe/events.sqlite`. troupe then
imports the files again, and the earlier history is lost.

### Includes

A string starting with `file:` includes the named file, relative to the file containing it. A `.yml`/`.yaml` target is
embedded as YAML; any other target's exact text becomes a string value. Setting a text include rewrites the target
file (keeping CRLF line endings if it had them). Replacing a whole YAML include is refused (exit 3).

Included files are shared between theatres, so an include can also be written in **mapping form**, with
**overrides** next to it:

```yaml
agents:
  coder:
    $ref: file:agents/coder.yaml   # the shared file
    temperature: 0.3               # an override, for this theatre only
```

The value is the included content deep-merged with the overrides: where both sides hold a mapping, they merge key
by key; anything else in the override (a scalar or a list) replaces the included value. Included keys keep their
order and keys only the overrides have come after them. `get`, `show` and `history` see the merged value, and
`show --sources` names the file each value is actually written in. A `$ref` whose value is not an include string
is an ordinary key. Overrides on a text include, or on an included file that does not hold a mapping (a list, a
scalar or an empty file), fail to load (exit 4).

Where `set` writes:

- **A new key under an included section** is written as an override in the file that holds the include reference,
  and the shared file does not change. A one-line include is converted to mapping form first, keeping its comment:
  `coder: file:agents/coder.yaml  # c` becomes `coder:  # c`, `  $ref: file:agents/coder.yaml`,
  `  temperature: 0.3`. With nested includes, the override goes next to the nearest include reference.
- **An existing value** is changed where it lives: in the override if one sets it, else in the included file.
- **Lists** are not reached by overrides. Appending an item, or adding a key inside an item, writes into the file
  that holds the list.
- **Deleting a key** (by setting its parent to a mapping without it) removes it from the included file and from
  every override that sets it. An override mapping left empty is removed too.

```sh
mkdir -p /tmp/demo/.troupe/agents
printf 'model: big\n' > /tmp/demo/.troupe/agents/coder.yaml
printf 'agents:\n  coder: file:agents/coder.yaml  # shared\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config set agents.coder.temperature 0.3 --theatre /tmp/demo
cat /tmp/demo/.troupe/troupe.yml
# agents:
#   coder:  # shared
#     $ref: file:agents/coder.yaml
#     temperature: 0.3
cat /tmp/demo/.troupe/agents/coder.yaml                  # model: big   (unchanged)
uv run troupe config show agents.coder --sources --theatre /tmp/demo
# model: big # from .troupe/agents/coder.yaml
# temperature: 0.3 # from .troupe/troupe.yml
```

Mapping-form includes need step 5 or later. Older code reads `$ref` as an ordinary key, so going back means
rewriting them as one-line includes (and moving the overrides into the shared file) by hand.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | usage error (bad arguments, path syntax, VALUE or `TROUPE_ACTOR`) |
| 3 | write refused, so no file changed |
| 4 | the configuration cannot be loaded (missing or duplicate config file, invalid YAML, missing include, include cycle, overrides on a text include or on included content that is not a mapping) |
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
`openspec/changes/archive/2026-10-03-config-sync-with-files/design.md`, `openspec/changes/archive/2026-10-03-config-get-and-show/design.md`,
`openspec/changes/archive/2026-10-04-config-lineage/design.md` and `openspec/changes/config-include-overrides/design.md`:

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
19. An invalid `TROUPE_ACTOR` is refused by every command, not only `set`, before anything is stored.
20. An empty `TROUPE_ACTOR` is invalid, not "unset". Kinds are lowercase only. The id is kept exactly and may contain
    `:`.
21. With no login name to be found, the actor is `{"kind": "human", "id": null}`.
22. `at` has microsecond precision, and every event of one change has the same `at`.
23. Change ids are random UUIDs. A `set` that picks up hand edits first records two changes (the hand edits', then
    its own).
24. `--reason` applies only to the `set`'s own events. An empty reason is stored as `""`.
25. Events from before lineage: actor unknown, via `import` or `file`, `at` from when they were stored, change
    `legacy-import` or `legacy-<seq>`.
26. A mapping-form include with overrides whose included content is not a mapping (a list, a scalar or an empty
    file) fails to load (exit 4). Deep-merge is only defined between mappings, and any other reading would show a
    value nobody wrote.
27. A `$ref` whose value is not an include string (e.g. `$ref: hello`) is an ordinary key, so every file that loaded
    before step 5 loads the same.
28. A new key under nested includes goes into the nearest including file: the one holding the reference to the include
    that the key's deepest existing ancestor comes from (the contract's "including file").
29. Deleting a key that both an included file and an override set removes it from both: overrides cannot delete, so
    removing only the override would bring the included value back.
30. An override mapping that a delete leaves empty is removed, since it changes nothing; the `$ref` mapping stays in
    mapping form.
31. A list item that is an include is converted as `- $ref: file:…` with its overrides below, at the include
    string's column: the smallest edit, keeping the item's comment on its line.
32. Setting a mapping-form include with overrides to its bare include string is refused (exit 3), so overrides are never
    dropped silently.
33. A converted one-line include keeps the include string's bytes and quotes as the `$ref` value. New overrides copy
    the quoting of the preceding entry (at first, the `$ref` value's).

## Development

```sh
uv run pytest            # tests, including end-to-end runs of `uv run troupe`
uv run mypy              # strict typing
uv run ruff check && uv run ruff format --check
```

Code map: `src/troupe/loader.py` (files and includes), `overrides.py` (`$ref` and the deep merge), `tree.py` (YAML
nodes with source positions), `schema.py` (core-schema types and printing), `lineage.py` (actors, timestamps and
change ids), `store.py` (event store), `edit/` (byte-surgical write-back: `plan.py` → `ops.py` → `apply.py`, with
`scalars.py`, `blocks.py`, `folded.py` and `text.py` holding the quoting, block-scalar, folding and layout rules),
`sync.py` (reconcile), `commands.py` (subcommands, the theatre lock and the `watch` loop) and `cli.py`.
