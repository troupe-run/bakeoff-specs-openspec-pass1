# Design

## Context

See proposal.md for the motivation and `specs/` for the exact behaviour. What exists today (after step 2):

- `cli.py` has a `show PATH` subparser. `commands.show()` opens a `theatre_session(theatre, "show")`, finds the node
  with `commands.find()`, refuses anything that is not a `ScalarNode` or `TextNode` (`PathError`, exit 5), and returns
  `schema.show_text(value)`.
- `RECONCILING_COMMANDS = {"show", "set", "watch"}` in `commands.py` decides which commands reconcile first.
- The loaded tree (`tree.py`) already holds what `--sources` needs. Every node has `file: SourceFile`, the file its text
  is in. A text include is a `TextNode` whose `target: SourceFile` is the included file. An included YAML file's
  root node and everything under it carry that file. An empty included YAML file becomes a `ScalarNode(None)` whose
  `file` is the included file.
- `SourceFile.path` is not resolved. It is `<theatre>/.troupe/<name>` for the config file and `base / target` for
  includes, so it can contain `..` segments.
- `set` already writes new values into block context:
  - `edit/scalars.py`: `render_scalar`/`render_key` (plain if it reads back the same, else single, else double quoted)
    and `can_plain`.
  - `edit/blocks.py`: `literal(value, owner_col, layout)` builds a literal block, choosing chomping and an indentation
    digit, and checks that the block reads back exactly (`block_ok`). It returns `None` when a block cannot hold the
    value.
  - `edit/blocks.py` also renders whole `Data` trees (`mapping_lines`, `item_lines`), but only from plain data, which
    has no file information and no `TextNode`s.

## Goals / Non-Goals

**Goals:**
- One renderer for `show` output. With and without sources it produces the same lines, so the two can never differ
  except for the comments.
- Scalars are written by the same helpers `set` uses, so quoting and literal-block rules are decided in one place.
- Output is checked by reading it back with troupe's own YAML reader, not by eye.

**Non-Goals:**
- Reproducing the user's original formatting, comments or quoting in `show` output. `show` prints the configuration
  as troupe understands it, in one canonical layout. The files themselves are never touched.
- Showing `file:` include strings or marking include boundaries, except through `--sources`.
- Flow style, anchors, or any output format other than block YAML.

## Decisions

### D1. `get` and `show` share lookup; `get` keeps the step-1 code path
`commands.get(theatre, path)` is today's `show()` with a new error message. `commands.show(theatre, path | None,
sources)` uses the same `theatre_session` and `find()`. With no path, the node is `config.root`. Then:
- a scalar or `TextNode` without `--sources` → `show_text(value)`, the `get` form, so the spec's "prints a scalar like
  `get`" is the same function call;
- anything else, or any node with `--sources` → `render.render(node, sources=...)`.

The `get` refusal message lives in one place, `commands.get`: `<path>: is a mapping, not a scalar (use `troupe config
show <path>` to print it)`. It names the path and contains `config show`, as the spec requires. `"get"` is added to
`RECONCILING_COMMANDS`, since a read must see hand edits the same way `show` does.

### D2. A new module `render.py` walks the node tree into lines with sources
`render(node, theatre, *, sources) -> str` walks `Node`s, not `Data`, because only nodes know their file and
whether a string is a text include. It produces a list of `Line(text, source: SourceFile | None)`. `source` is set only
on lines that hold a scalar value. Then it joins them. Each line is `text`, plus ` # from <label>` when `sources` is on
and `source` is set.
- Mapping entry with a non-empty mapping or list value: `key:` (no source), children at indentation +2.
- Mapping entry with a scalar: `key: <scalar>` with the scalar's source.
- Mapping entry with a literal block: `key: |…` with the source, then content lines without a source.
- Sequence item: `- <scalar>`. Non-empty collections use the compact `- key: v` / `- - x` form: the first child line
  is joined to the dash, as `edit/blocks.item_lines` does. The source stays with that first line.
- Empty mapping or list: `{}` / `[]`, no source. An empty root mapping prints `{}`.
- Root scalar (only reached with `--sources`): the scalar alone, or the literal header alone at indentation 0 with
  content at 2.

*Alternative:* extend `edit/blocks.py`'s `Data` renderer to carry sources. Rejected: it would need nodes instead of
data and a `TextNode` case, all for a feature that `set` does not use. That would make `set`'s write path harder
to verify. The structural rules are short. The scalar rules, which are the hard part, are shared (D3).

### D3. Scalars use `set`'s helpers
- Non-strings and single-line strings: `edit.scalars.render_scalar(value, None, flow=False)`. That gives `plain_text`
  for non-strings (`null`, `true`, `31`, `1000.0`, `.inf`), and plain, single or double quotes for strings. Keys use
  `render_key(key, None, flow=False)`.
- A `TextNode`, or any string containing `\n`: `edit.blocks.literal(value, owner_col, Layout(unit=2, seq_offset=2))`.
  `owner_col` is the column of the key or `-` that owns the value, or `-1` at the root. If `literal` returns `None`
  (a carriage return, a control character, or a value such as `"\n"` that its check rejects), fall back to
  `render_scalar`. That is double quotes, because single quotes cannot hold a line break.
So `block_ok`, which reads the candidate block back, is the one definition of what a literal block cannot hold.

### D4. `<file>` is a lexical path relative to the theatre
`source_label(file, theatre) = os.path.relpath(os.path.normpath(os.path.abspath(file.path)),
os.path.abspath(theatre))`, with `/` separators. `.troupe/agents/../b.yaml` becomes `.troupe/b.yaml`. Symlinks are
not resolved. That keeps the label consistent with how the user named the theatre (on macOS, `resolve()` would turn
`/var/…` into `/private/var/…`), and it matches how `cli.py` already treats `watch`'s `<dir>`. An include outside the
theatre gets a `../` label. Includes outside the theatre are not forbidden by the contract, so this is not an error.
The function lives in `render.py`.

### D5. The source of each scalar
`ScalarNode.file` for ordinary scalars, and `TextNode.target` for text includes. The `file:` string's own file is
deliberately not used, as the contract says. Mapping keys get no comment of their own. The line's comment always
describes the value on that line, and in block style a key and its scalar value are always in the same file.

### D6. CLI shape
- `get` subparser: one required `path`.
- `show` subparser: `path` with `nargs="?"`, and `--sources` (`store_true`), accepted before or after the path.
- `run` dispatches to `commands.get` / `commands.show`. Exit-code mapping stays in `main`.

### D7. Testing
- Move today's `tests/test_show.py` scalar and refusal tests to `tests/test_get.py`, running `get`. Add the
  `config show` message check.
- Rewrite `tests/test_show.py` for the spec's exact-output scenarios: whole config, section, list, list of mappings,
  one-line text include, quoting, scalar types, empty collections, empty config. Also check that `show` of a scalar
  equals `get`, and that missing paths exit 5.
- `tests/test_show_sources.py`: the exact `--sources` scenarios, the empty included file, a `..` include, the
  `troupe.yaml` name, a scalar with `--sources`, and a text include's comment naming the included file.
- Round-trip test: for a table of tricky configurations (multi-line strings with and without trailing newlines,
  leading spaces, CRLF text includes, `.nan`/`-.inf`, strings like `true`/`0.2`/`- x`/`#x`/`a: b`, nested lists, lists
  of mappings, unicode, empty strings), read `show` and `show --sources` output back with `tree.build_tree` +
  `to_data`, and compare with the loaded configuration using `schema.same`, so types count.
- Update callers that relied on the old refusal. `tests/test_smoke.py` expects `show agents` → 5, which becomes
  `get agents` → 5, plus a smoke test for `uv run troupe config show --sources`. Other `show` calls on scalars keep
  working unchanged. That is itself a check that the `get` form is preserved.
- Reconcile: add `get` cases to `tests/test_reconcile.py` (hand edit then `get` records the reconcile event, and
  `get nope` exit 5 still keeps it).

## Risks / Trade-offs

- [Scripts that relied on `show` exiting 5 on collections now get YAML and exit 0] → this is the step-3 contract
  (**BREAKING** in the proposal). The migration is to call `get`. The README says so.
- [Canonical output differs from the user's file layout (quoting, `0x1F` shown as `31`, flow lists shown as block)]
  → this is intended: `show` shows values, not text. The files are never touched.
- [A string starting with `file:` (only possible through a tag such as `!!str file:x`) prints plain, and troupe's
  loader would read that back as an include] → the output is still correct YAML 1.2 for the data. Reading `show`
  output back into troupe is not in the contract.
- [The literal-block check parses each candidate block] → a few small parses per multi-line value. No performance
  targets apply.

## Migration Plan

No data migration: events, state and write-back do not change. To roll back, use the step-2 code. `get` disappears
and `show` refuses collections again.

## Decisions on points the contract leaves open (for product-owner review)

1. `show PATH --sources` on a scalar prints a one-scalar YAML document with the comment (`x # from .troupe/troupe.yml`)
   instead of the bare `get` form. `--sources` asks for source information, and a bare value cannot carry it.
2. The comment is written as one space, `#`, one space, then the file. It goes on the `|` header line for literal
   blocks, because content lines cannot hold comments. Lines with `{}`/`[]` get no comment: they hold no scalar.
3. `<file>` is normalised lexically (`..` removed) and symlinks are not resolved (D4). Includes outside the theatre
   get `../` labels.
4. Strings are quoted by the same rule `set` uses for new values: plain if it reads back the same, else single
   quotes, else double quotes. Every string containing a line break, not only text includes, is a literal block when
   one can hold it exactly.
5. Lists under a mapping key are indented two spaces, and items that are collections use the compact `- key: v` form.
6. `get` reconciles first, like `show`. A read sees hand edits the same way regardless of which command reads.
