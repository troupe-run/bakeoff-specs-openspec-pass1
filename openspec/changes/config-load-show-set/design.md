# Design

## Context

The repository is greenfield; it holds only OpenSpec scaffolding. See proposal.md for the motivation and the specs
for the behaviour. Fixed constraints: Python 3.12 or later, uv, the `eventsourcing` library, `mypy --strict`, a clean
ruff run, macOS and Linux, and small files (no performance targets).

A read-only spike (ruamel.yaml 0.19.1, eventsourcing 9.5.5, both ship `py.typed`) established:
- `YAML(typ='safe', pure=True).compose()` gives every node `start_mark`/`end_mark`, with `.index` counted in code
  points of the text as given. `\r\n` counts as two characters, so marks index straight into a string read with
  `newline=''`. Scalar nodes carry `style` (`None`, `'`, `"`, `|`, `>`) and collections carry `flow_style`.
- ruamel's 1.2 resolver is **not** the strict core schema: it tags `2001-01-01` as a timestamp and `1_000` as an int.
  Its tags for plain scalars must not be trusted.

## Goals / Non-Goals

**Goals:**
- Edits change only the bytes the spec requires, and are checked before any byte reaches the disk.
- Each policy (quoting fallback, indentation, chomping, comment alignment, entry placement, exit codes) lives in one
  named function or module, so a later step can change it in one place.
- Later steps (remove, anchors at step 6, include changes at step 5) can extend the edit model without a rewrite.

**Non-Goals:**
- Reconciling hand edits into the event log.
- Anchors and aliases, multi-document files, a TAB before an end-of-line comment, and concurrent writers. Whatever
  these do is acceptable.
- A general-purpose YAML emitter; we emit only what `set` needs.

## Decisions

### D1. Package layout (`src/troupe/`)
| Module | Responsibility |
|---|---|
| `cli.py` | argparse, subcommand dispatch, mapping `TroupeError` → exit code + stderr; the `troupe` entry point |
| `errors.py` | `TroupeError` hierarchy, each class owning its exit code (`UsageError`=2, `WriteRefused`=3, `LoadError`=4, `PathError`=5) |
| `paths.py` | parse and format dotted paths |
| `schema.py` | YAML 1.2 core-schema resolution of plain scalars, plus `format_scalar` for printing (the one place for type rules) |
| `values.py` | parse a command-line `VALUE` as a single flow node |
| `source.py` | `SourceFile` (path, text, newline style, line index ↔ offset helpers) |
| `tree.py` | the loaded tree: `MapNode`/`SeqNode`/`ScalarNode`/`TextInclude`, each carrying its `SourceFile`, span, style, flow/block context, key node, and the include it came through |
| `loader.py` | find the config file, compose with ruamel, convert to `tree`, resolve includes (cycle stack of resolved paths) |
| `leaves.py` | flatten a tree or plain value to an ordered `{path: value}` dict |
| `edit/` | write-back: `plan.py` (diff semantics → edits), `scalars.py` (quoting and escaping), `blocks.py` (literal blocks, block collections), `folded.py` (folded paragraph alignment and re-wrap), `layout.py` (indentation detection, entry placement, comment alignment), `apply.py` (splicing text edits and verification) |
| `store.py` | eventsourcing application, aggregate and events |
| `commands.py` | the `show`, `set` and `history` flows |

### D2. Parse with ruamel.yaml's composer and do our own scalar resolution and editing
We use ruamel only for `compose()`, which gives nodes and marks. We resolve plain scalars with our own core-schema
regexes (`schema.py`), and quoted and block scalars are always strings. Explicit core tags (`!!str`, `!!int`, …) are
honoured. Other tags, anchors and aliases fail with exit 4 (out of contract, conservative).
*Alternatives:* ruamel round-trip mode reformats on dump and cannot guarantee byte preservation. PyYAML is YAML 1.1.
A hand-written parser would be a large risk for no gain.

### D3. Edits are text splices on the original string, then verified
The planner produces a list of `Edit(file, start, end, replacement)` against each file's original text, applied right
to left. Comments are not in ruamel's node graph, so `layout.py` scans raw lines. An end-of-line comment is the first
`#` after the node's end on its last line that is preceded by whitespace, where the bytes between the node end and the
`#` are only whitespace (or flow punctuation, for collections). **Verification** (`apply.py`): re-load the whole
configuration from the edited in-memory texts, as if they were on disk, and require that the result's leaves equal the
intended leaves and its include structure is unchanged. Any mismatch → `WriteRefused` (exit 3) before any write. This
safety net is what lets us use "emit, then re-read" to test whether a style can represent a value.

### D4. Writing files
A file is written only if its text changed, in place (`open(..., 'w', encoding='utf-8', newline='')`), with no temp
files outside `.troupe/` and nothing else created. Normally one file changes per `set`. When several do, all texts are
computed and verified first, so the only failure left is an OS error during the write itself.

### D5. `set` uses diff semantics
`plan.py` compares the existing node with `VALUE`. Two mappings → per key: recurse on keys in both, add new keys,
delete keys VALUE lacks. Two lists → per index: recurse, append extras, delete surplus trailing items. Equal scalars →
no edit. Anything else → replace the node. A YAML include root is never recursed into from the target path or above:
if its value would change or be deleted, the result is `WriteRefused`. This follows contract rule 4 and is
conservative. *Alternative:* replacing the whole collection text would discard comments and formatting inside it,
which goes against the product principle "never rewrite what the user did not ask to change".

### D6. Quoting policy (`edit/scalars.py`)
`choose_style(value, preferred, context)` tries the preferred style, then plain → single → double, and returns the
first style that can represent the value. Plain is valid if no indicator rule is broken (leading indicator, `: `,
` #`, leading or trailing whitespace, empty, flow characters in flow context, newline) **and** `schema.resolve(text)`
gives back the same typed value. Single-quoted is valid if there are no newlines and only printable characters.
Double-quoted always works. Multi-line strings go through `blocks.py` instead (literal block in block context,
double-quoted in flow context). Non-strings are always plain, using a canonical form: `true`/`false`, `null`, a decimal
int, `repr(float)` with `.inf`/`-.inf`/`.nan` for non-finite floats.

### D7. Layout policies (`edit/layout.py`)
- **Indent unit:** the column difference between the first block mapping nested in a block mapping and its parent
  key; default 2. **Sequence offset:** the offset of the first block sequence under a mapping key (0 = indentless);
  default = the indent unit.
- **Insertion point** for a new block entry: the end of the last entry's value, then extended past following lines
  that are blank or are comments indented at least as far as the entries. Stop at any other line. Then back up to the
  end of the last comment line, so trailing blank lines stay below the new entry.
- **Comment alignment:** `realign(line_before, line_after)` keeps the comment column if possible, else leaves one
  space. It is applied to the (first and last) lines an edit touches that carry a comment.
- **Newline:** the file's first line break decides the style of inserted lines; an LF-only or empty file uses LF.

### D8. Block scalars (`edit/blocks.py`, `edit/folded.py`)
We parse the header (`|`/`>`, chomping, indentation indicator) from the source at the node's start mark. Content
indentation is kept from the old node. For new blocks it is the owning line's indentation plus the indent unit.
Chomping is chosen by `required_chomping(value)`: no trailing newline → strip, exactly one → clip, more → keep. The old
chomping is kept when it can represent the value (keep represents one or more). For folded scalars, the old and new
values are split into paragraphs on `\n`, aligned with `difflib.SequenceMatcher`, and the paragraphs of a `replace`
opcode are paired by position. Unpaired new paragraphs use the global width. We re-emit the separator blank lines that
folding requires between non-empty paragraphs and for empty paragraphs. Any new paragraph starting with a space or TAB
is refused (exit 3).

### D9. Event store (`store.py`)
- An `eventsourcing.application.Application` subclass configured through its constructor `env`:
  `PERSISTENCE_MODULE=eventsourcing.sqlite` and `SQLITE_DBNAME=<theatre>/.troupe/events.sqlite`. This keeps the
  environment of the process untouched.
- One aggregate, `TheatreConfig`, whose id is a fixed `uuid5` (so it can be found without an index). Its events are
  `Imported(path, new)`, `LeafSet(path, old, new)` and `LeafRemoved(path, old)`, and its state is the leaf projection
  `{path: value}`. The aggregate's `Created` event marks "imported". It is not shown in history, so `seq` = aggregate
  version − 1.
- All events of one command are saved in one `save()` call (atomic in SQLite).
- The store is opened only after the configuration has loaded and the arguments are valid, so a failing load creates
  no state.
- Values are JSON-compatible Python values. Text-include leaves store the text.
*Alternative:* a hand-rolled JSONL log is simpler, but the constraint requires `eventsourcing`.

### D10. Source of truth for reads
`show` and the `old` values of `set` come from the files as loaded now, not from the projection. Hand edits are
honoured, and the projection is not reconciled (contract: "importing is not reconciling"). Because the files are what
people edit and review, this is the choice that cannot misreport the files' contents.

### D11. Command flow
`cli` parses argv (exit 2) and parses `VALUE` (exit 2). Then `loader` loads (exit 4), the `store` imports if needed,
and the command runs. For `set`: resolve the path → plan → apply in memory → verify → write files → save events. Events
are saved after the files are written. If saving fails, the files were still changed, and the error is reported. The
reverse order could record a change that never reached the disk.

### D12. Testing approach
pytest with real files under `tmp_path`. Most tests call `troupe.cli.main(argv)` in-process and check exit code,
stdout, stderr and **exact file bytes**. A smoke suite runs `uv run troupe config …` as a subprocess to prove the
entry point. Every spec scenario maps to at least one named test. Byte-exact tests assert the whole expected file
content, not substrings.

## Risks / Trade-offs

- [ruamel.yaml mark semantics differ from assumptions in edge cases (BOM, plain multi-line scalars, flow end marks)]
  → mark helpers in `source.py` are covered by focused tests, and verification (D3) refuses rather than corrupts.
- [Representability checks miss an edge case] → verification re-reads the result. The worst case is exit 3 rather
  than a wrong file.
- [Diff semantics surprise someone who expected wholesale replacement] → the result is the same value either way;
  only the byte layout differs, and it is the minimal one. Recorded here and in the spec.
- [Events saved after files written; a crash in between loses an event] → acceptable for step 1 (no concurrency and
  no reconciliation); documented.
- [SQLite creates transient `-journal` files] → they live under `.troupe/`, which the contract allows.

## Migration Plan

None, since there is no existing state.

## Decisions on points the contract leaves open (for product-owner review)

1. A null or scalar intermediate (`agents:` with no value) is not a mapping → `set agents.coder x` exits 5.
2. A digit segment that needs a missing intermediate created exits 5 (digit-only keys are out of contract).
3. An empty or comment-only config file is an empty mapping.
4. A string VALUE starting with `file:` becomes an include. If the configuration then fails to load, the write is
   refused with exit 3.
5. Mapping/list VALUEs are applied as a diff (D5). Changing or deleting an include root through an ancestor exits 3.
6. Import happens on any command whose configuration loads, before the command runs, and persists even if the
   command then exits 3 or 5.
7. `history PATH` with no matches prints nothing and exits 0. Non-finite floats are shown in JSON as YAML-style
   strings.
8. Explicit tags other than core ones, and anchors and aliases, fail to load with exit 4 for now.
9. *(Added during implementation.)* New keys use the same plain-safety rule as string values. A key that would read
   back as a non-string (such as `true` or `1.0`) is quoted, so the YAML key stays a string for every reader.
10. *(Added during implementation.)* Deleting the first entry of a compact `- key: v` item (one that shares the
    dash's line) pulls the next entry up into its place at the same column. It is not refused. An empty value
    (`key:` with nothing after it) is filled right after the `:`.
