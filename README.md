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
| `troupe config set PATH VALUE [--reason TEXT] [--in-include] [--expand-alias] [--include]` | Change or create the value at `PATH` and write it back into the file that holds it; `--reason` is recorded in the history; `--in-include` puts new keys into the included (shared) file instead of an override; `--expand-alias` gives a value reached through an [alias](#anchors-and-aliases) its own copy; `--include` writes a `file:`/`https://`/`http://` string as an include instead of a [literal](#literal-strings) |
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

A string starting with `file:` includes the named file, relative to the file containing it. A string starting with
`https://` or `http://` includes what that URL serves (see [Remote includes](#remote-includes)). A `.yml`/`.yaml`
target is embedded as YAML; any other target's exact text becomes a string value. A string tagged `!literal` is never
an include (see [Literal strings](#literal-strings)). Setting a text include rewrites the target
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

When a new setting really belongs in the shared file, for every theatre that includes it, say so with
`--in-include`. New keys then go into the file that holds their deepest existing section (the included file, or the
innermost one with nested includes) and no override is written. Only new keys are affected: existing values,
appends and deletes go where they would without the flag.

```sh
uv run troupe config set agents.coder.top_p 0.9 --in-include --theatre /tmp/demo
cat /tmp/demo/.troupe/agents/coder.yaml
# model: big
# top_p: 0.9
```

Mapping-form includes need step 5 or later. Older code reads `$ref` as an ordinary key, so going back means
rewriting them as one-line includes (and moving the overrides into the shared file) by hand.

### Remote includes

Shared team configuration can live on a web server. A URL include works like a file include. A URL whose path
(without query string) ends `.yml`/`.yaml` is embedded as YAML, and any other is text. It can be written in mapping
form with overrides:

```yaml
agents:
  coder:
    $ref: https://config.example.com/team/coder.yaml
    temperature: 0.3          # this theatre only
```

URLs are fetched every time the configuration loads: every command, each `watch` reconcile, and once (not again)
during a `set`. A change on the server is recorded at the next reconcile, like a hand edit (`via` `file`, actor
unknown). `watch` does not poll URLs, so it records such a change when a local change, or another command, next
reconciles. A failed fetch fails to load (exit 4), naming the URL. That covers a server that cannot be reached, a
response that is not 2xx, no answer within 30 seconds, a body that is not UTF-8, invalid YAML, and a redirect to
anything but `http`/`https`.

A `file:` include inside remote content is relative to that content's URL, like a link in a web page. Remote content
can never read your local files. `show --sources` names remote values by URL.

troupe cannot write to a URL, so **remote values are read-only**. A `set` that would change or delete a value written
in remote content, add to or remove from a remote list, change a remote text include, or expand an alias in remote
content is refused (exit 3), and nothing changes. The message names the include line in your own file to change
instead:

```
troupe: agents.coder.model: comes from https://config.example.com/team/coder.yaml, which troupe cannot change.
It is included by https://config.example.com/team/coder.yaml in .troupe/troupe.yml line 3: change that include line
instead (new keys are written as local overrides)
```

(one line in the real output). A value that a local override sets is yours, and `set` changes it in the override.
A **new key** under a remote include is written as an override next to the include line in your file, as for any
include. Remote content that includes more remote content gets its override next to the include written in a local
file. `--in-include` would put the key into the remote file, so it is refused.

**Upgrading:** before step 7, a string such as `homepage: https://example.com/docs.yaml` was a plain string. Now it is
fetched. Tag it `!literal`, or mark it in the [schema](#schema) with `"format": "uri"`, to keep it a string.

### Literal strings

A string that only looks like an include is written with the `!literal` tag. It is then an ordinary string, in
any quoting style or as a block scalar, and nothing is read or fetched:

```sh
printf 'docs: !literal file:README.md\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config get docs --theatre /tmp/demo                  # file:README.md
uv run troupe config set docs file:CHANGES.md --theatre /tmp/demo  # docs: !literal file:CHANGES.md
```

`set` keeps the tag when it changes the string, and removes it when the new value is not a string (a number, say),
since it would turn that into a string. `!literal` on a mapping or list fails to load (exit 4).

`set` writes the tag for you. A string in VALUE that would be read as an include is written `!literal`, unless you
pass `--include` or the [schema](#schema) marks the path `format: uri`:

```sh
printf 'a: 1\n' > /tmp/demo/.troupe/troupe.yml && printf 'You write code.\n' > /tmp/demo/.troupe/coder.md
uv run troupe config set docs https://example.com/guide --theatre /tmp/demo   # docs: !literal https://example.com/guide
uv run troupe config set prompt file:coder.md --include --theatre /tmp/demo   # prompt: file:coder.md
uv run troupe config get prompt --theatre /tmp/demo                           # You write code.
```

**Upgrading scripts:** before step 7, `set PATH file:…` created an include. It now writes a literal string. Add
`--include` to keep the old behaviour.

### Schema

A theatre can describe its configuration with a [JSON Schema](https://json-schema.org/) (draft 2020-12) in
`.troupe/troupe.schema.json`. When the file exists, it does two things:

- **It marks URL settings as literals.** A string whose schema has `"format": "uri"` is a plain string, never an
  include, whatever it starts with. troupe finds a value's schema by following `properties` (then
  `additionalProperties`) for each mapping key and `items` for each list index, from the top. It follows nothing
  else, so `$ref`, `allOf` and the like are not used for this. A value reached through an alias is judged where its
  anchor is written.
- **It checks the configuration.** The loaded configuration, with includes resolved, must be valid, or every command
  fails to load (exit 4), naming the schema file and a failing path. A `set` whose result would not be valid is
  refused (exit 3). `format` is not checked, as draft 2020-12 specifies by default.

```sh
cat > /tmp/demo/.troupe/troupe.schema.json <<'JSON'
{"type": "object",
 "properties": {"endpoint": {"type": "string", "format": "uri"},
                "temperature": {"type": "number"}}}
JSON
printf 'endpoint: https://api.example.com/v1.yaml\ntemperature: 0.2\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config get endpoint --theatre /tmp/demo           # https://api.example.com/v1.yaml (not fetched)
uv run troupe config set temperature hot --theatre /tmp/demo    # exit 3: not valid against the schema
```

A schema that is not valid JSON, or not a valid draft 2020-12 schema, fails to load (exit 4). So does one with a
`$ref` to anything outside the file, because troupe never fetches schemas. Its `$schema` keyword is ignored. `watch`
also watches the schema file, since editing it can change what is an include.

### Anchors and aliases

A value can be shared within one file with a YAML anchor (`&name`) and aliases (`*name`) to it. An alias has the value
of the node anchored with that name earlier in the same file. A merge key (`<<`, plain) adds the entries of the
mapping (or list of mappings) it names to the mapping that holds it. That mapping's own keys win, then earlier
mappings in the list. `get`, `show`, `history` and reconciling all see the resolved values, and `show --sources` names
the file the anchor is written in.

```sh
printf 'defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  <<: *d\n  temperature: 0.2\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config get coder.settings.model --theatre /tmp/demo   # opus
uv run troupe config show reviewer --theatre /tmp/demo              # model: opus / temperature: 0.2
```

Anchors do not cross files: an alias cannot refer to an anchor in a file it includes, or one that includes it. An
alias with no anchor before it (or inside the node it refers to), an anchor or alias used as a key, and a merge key
whose value is not a mapping or list of mappings written in that file all fail to load (exit 4).

Setting a value **at the anchor** changes it there, keeping the `&name`, so every alias sees the new value. History
records an event for each path whose value changed. Setting a value **through an alias** would do the same thing
without your saying so, so it is refused (exit 3) and nothing changes:

```sh
printf 'defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config set defaults.model sonnet --theatre /tmp/demo        # coder and reviewer now use sonnet too
uv run troupe config set coder.settings.model haiku --theatre /tmp/demo   # exit 3:
# troupe: coder.settings.model: coder.settings is the alias *d of &d at defaults, so this would change all its
# uses. Set defaults.model to change it everywhere, or use --expand-alias to give coder.settings a copy
```

This covers a mapping or list VALUE that would change anything under an alias, and a new key below one. Removing an
entry whose value is an alias is fine, since it changes nothing else. Deleting an anchor that an alias still uses is
refused (exit 3).

To change it for one user only, ask for that user's own copy with `--expand-alias`. The alias is replaced by a
block-style copy of the anchored node as it is written, marked with a comment, and the value is then set in the
copy. The anchor and every other alias stay as they were:

```sh
printf 'defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config set --expand-alias coder.settings.model sonnet --theatre /tmp/demo
cat /tmp/demo/.troupe/troupe.yml
# defaults: &d
#   model: opus
# coder:
#   settings:  # expanded from *d by troupe
#     model: sonnet
# reviewer:
#   settings: *d
```

The copy keeps each key and scalar as written (quoting, `0x10`, include strings), and aliases inside the anchored
node stay aliases. An alias that the set still reaches through is expanded too, with its own comment. An alias inside
a flow collection (`{…}`, `[…]`) cannot take a block-style copy, so setting through it is refused even with the flag.
With no alias in the way, the flag changes nothing, so running the same command again is safe.

Merge keys are never written. In a mapping with `<<`, its own keys are set where they are written, and a new key goes
after its last entry. But a value that the merge key supplies cannot be set, deleted or given a copy (exit 3, even
with `--expand-alias`), and neither can the `<<` entry or anything that holds it. Change the merged value at its
anchor, or edit the file by hand:

```sh
printf 'base: &b\n  model: opus\ncoder:\n  <<: *b\n  temperature: 0.5\n' > /tmp/demo/.troupe/troupe.yml
uv run troupe config set coder.temperature 0.7 --theatre /tmp/demo   # changes coder's own key
uv run troupe config set coder.model sonnet --theatre /tmp/demo      # exit 3: supplied by the merge key coder.<<
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | usage error (bad arguments, path syntax, VALUE or `TROUPE_ACTOR`) |
| 3 | write refused, so no file changed (for example a value from a remote include, or a result the schema rejects) |
| 4 | the configuration cannot be loaded (missing or duplicate config file, invalid YAML, missing include, a remote include that cannot be fetched, include cycle, overrides on a text include or on included content that is not a mapping, an alias without an anchor before it, a merge key that names no mapping, an unusable schema file, a configuration that is not valid against the schema) |
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
`openspec/changes/archive/2026-10-04-config-lineage/design.md`, `openspec/changes/archive/2026-10-05-config-include-overrides/design.md`
`openspec/changes/archive/2026-10-05-config-set-in-include/design.md`,
`openspec/changes/archive/2026-10-06-config-anchors-and-aliases/design.md` and
`openspec/changes/archive/2026-10-08-config-remote-includes-and-schema/design.md`:

1. Setting a key under a null or scalar value (e.g. `agents:` with nothing after it) exits 5. Set the parent to a
   mapping first: `set agents '{coder: {model: x}}'`.
2. A digit segment that would need a missing parent created exits 5.
3. An empty or comment-only `troupe.yml` is an empty mapping.
4. A string in VALUE starting with `file:`, `https://` or `http://` is written tagged `!literal`, so it stays the
   string you typed, unless the schema marks its path `format: uri` (then it is written untagged, a literal anyway).
   With `--include` it is written as an include, and if the result cannot load the write is refused (exit 3). This
   covers strings inside a mapping or list VALUE too: otherwise `set links "[https://…]"` would silently fetch.
5. Mapping and list VALUEs are applied as a diff: unchanged entries keep their bytes, and keys missing from VALUE are
   deleted. Changing or deleting a YAML include through a parent path is refused (exit 3).
6. Import happens on any command whose configuration loads, before the command runs. So does reconciling (except for
   `history`), and its events are kept even if the command then fails with exit 3 or 5.
7. `history PATH` with no matches prints nothing and exits 0. `.inf`/`.nan` appear in JSON as the strings `".inf"`,
   `"-.inf"` and `".nan"`.
8. Non-core tags fail to load (exit 4), except `!literal` on a scalar: see [Literal strings](#literal-strings).
   Anchors, aliases and merge keys load: see [Anchors and aliases](#anchors-and-aliases).
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
34. `set --in-include` changes only where new keys go. Existing values keep the override rule, so the flag can never
    leave an override hiding the value just written.
35. `--in-include` is accepted where no include is involved and changes nothing there, since the step-1 rule picks
    the same file; scripts need not check for includes first.
36. With `--in-include`, a new key under a section merged from an included file and overrides goes into the included
    file (where the shared content lives); under a section that exists only in an override, into the override's
    file, the only file that holds it.
37. With `--in-include` and nested includes, the key goes into the innermost included file: the file containing its
    deepest existing ancestor.
38. `--in-include` adds no exit codes and does not change the recorded events: history records values, not files.
39. Merge keys (`<<`) are applied when reading, since that is what people who write `<<: *base` mean.
40. A value supplied by a merge key cannot be set, even with `--expand-alias` (exit 3). Writing a local key instead
    would not touch `<<`, but merges are shallow: a local mapping would silently drop the other merged sub-keys.
41. Deleting or replacing anything that holds a `<<` entry is refused (exit 3): "never written" covers removal.
42. `--expand-alias` with no alias in the way changes nothing, so re-running a command after the expansion succeeds.
43. `--expand-alias` expands every alias the set would otherwise be refused for, including nested ones and those a
    mapping or list VALUE reaches into. Expanding only the first would leave the command refused.
44. A comment already on the alias's line is kept, and the `# expanded from *name by troupe` marker follows it.
45. The copy is the anchored node as written, not its resolved value: nested aliases, include strings, quoting and
    number formats stay. Anchors inside it are not copied, as they would re-bind later aliases.
46. A path through an alias in an included file, or in the included part of a mapping-form include, is refused, even
    where an override would be written elsewhere. That refuses more than strictly needed, but never writes through
    an anchor.
47. A new key named `<<` is written quoted (`'<<'`), so it is an ordinary key and never a merge key.
48. A `file:` include inside remote content is resolved against that content's URL: the step-1 rule says "relative
    to the file containing it", and that file is remote. Reading a local file named by shared content would let it
    read your disk.
49. A refused write to remote content names the outermost include written in a local file, with its file and line,
    quoted as written: that is the only line you can change.
50. A new key under nested remote includes becomes an override of the nearest include written in a local file, deep
    enough to reach the key, since the nearer include's reference is itself remote.
51. Deleting a key that remote content sets is refused (exit 3) even when an override also sets it, because removing
    only the override would bring the remote value back (as in decision 29).
52. `show --sources` names a value from remote content by its URL.
53. Fetching: a 30-second timeout, redirects followed only to `http`/`https`, a 2xx status and UTF-8 body required,
    nothing cached between commands, and each URL fetched at most once per command (so a `set` checks its result
    against the same content it started from).
54. `watch` does not poll URLs. Remote changes are recorded at the next reconcile, as hand edits (`via` `file`, actor
    unknown).
55. The schema is always read as draft 2020-12 (its `$schema` is ignored), `format` is not checked, and a `$ref` to
    anything outside the schema file fails to load: the contract names 2020-12, the draft makes `format` an
    annotation by default, and fetching a schema would add a second, unannounced network dependency.
56. A string is judged `format: uri` or not at its position in the loaded configuration, with includes resolved. The
    `$ref` string of a mapping-form include is at `<path>.$ref`, where it is written. A node reached through an alias
    is judged where its anchor is written.
57. `set` checks the schema once, on its final result, so a change made in several steps is not refused for a state
    in between.
58. `--include` on a string at a path the schema marks `format: uri` is refused (exit 3), rather than silently
    writing a literal you did not ask for.
59. Setting an include to its own string without `--include` is refused (exit 3): it asks for a literal string in
    place of the include. With `--include` it changes nothing, as before step 7.
60. A `!literal` tag is kept when its scalar becomes another string (the smallest diff), and removed when the new value
    is not a string, which the tag would otherwise turn into one.
61. `--include` does not affect the text written into a text include's file: that text is never read as an include.

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
