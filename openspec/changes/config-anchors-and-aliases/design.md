# Design

## Context

See proposal.md for the motivation and `specs/` for the behaviour. Today:

- `tree._Builder.node` raises `LoadError` on any `AliasEvent` or anchored event (README decision 8;
  `tests/test_loading.py::test_anchors_are_refused_at_load`).
- ruamel's event for an anchored node starts **at the `&`**. For `a: &x  "q"` the `ScalarEvent` spans `&x  "q"`,
  and for a block mapping `d: &d\n  model: …` the `MappingStartEvent` starts at `&d`. Every edit primitive takes
  `node.start` as the start of the value's own text, so spans that include `&name` would make a replace remove the
  anchor.
- `loader._Loader.expand` replaces `entry.value` / `item.value` in place with included content. `overrides.merge`
  builds merged mappings out of new `Entry` objects plus `layers` (the mappings as written).
- `edit/apply.compute_set` plans once, then applies the operations one at a time, reloading from the edited texts
  after each, and finally checks that the result reads back as intended (`_matches`). Anything that does not reload,
  or does not match, becomes `WriteRefused` (exit 3) with no file written.

## Goals / Non-Goals

**Goals:**
- Aliased values are the anchored node itself, so `to_data`, `leaves`, `render`, `show --sources`, import, reconcile
  and history need no change.
- One place decides "this write goes through an alias" and one place decides "this write touches a merge key", both
  in the planner. Expansion reuses the existing apply → reload loop.
- The read-back check stays the last line of defence: any case this design misses becomes exit 3, never a wrong
  file.

**Non-Goals:**
- Writing anchors or aliases in new values (VALUE is a flow node and cannot contain them).
- Collapsing equal values back into an alias, or turning a copy back into an alias.
- Anchors across files, YAML 1.1 merge semantics beyond `<<`, and anchors or aliases as mapping keys.

## Decisions

### D1. An alias is the anchored node object; the alias is recorded on the entry or item
`Node` gets `anchor: Anchor | None` (`name`, and the `start`/`end` of the `&name` text). The builder moves
`node.start` past the node's properties (the anchor and any whitespace, line breaks or comments after it, and a
tag if present), so a node's span is its value text only, as before. `Entry` and `Item` get
`alias: Alias | None` (`name`, the `start`/`end` of `*name`, and `target`), and their `value` **is** the anchored
`Node` object. The builder keeps `anchors: dict[str, Node]`, filled when an anchored node is complete. A later
anchor of the same name replaces the earlier one. An alias to a name that is missing, or still being built (an
alias inside its own anchor), raises `LoadError`. An `AliasEvent` or anchored event in key position keeps failing
as today ("only scalar mapping keys", plus anchored keys).

*Alternative*: an `AliasNode` type pointing at its target. Rejected: every consumer (`to_data`, render, leaves,
sources, plan, apply, `_matches`) would need a new case. With the shared object, they read the right value
unchanged, and the anchored node's `file`, `owner_col` and `in_flow` describe where an edit would actually go.

### D2. The loader expands each node once
`_Loader.expand` keeps a memo keyed by `id(node)`. A node reached a second time through an alias returns the same
expanded node. So an anchored include string is read once, and all its aliases share one included tree. Without the
memo, the second visit would see an already-replaced `entry.value` and include the file again as a separate tree.
`overrides.merge` copies `alias` onto the `Entry` objects it creates for deep-merged keys (from the base entry,
else the override), so the alias marker survives mapping-form includes.

### D3. Merge keys are resolved by the builder; the mapping as written is kept
At the end of a block or flow mapping, an entry whose key is plain and untagged `<<` is a merge key. Its value must
be a mapping, or a sequence of mappings, as built in this file (directly or through aliases). An include string is
not a mapping yet at build time, so it fails to load (exit 4). The builder then makes the resolved `MappingNode`:
- local entries keep their positions;
- the merged-in entries that no local key (and no earlier merge source) has take the `<<` entry's position;
- `written` holds the mapping as written, with the `<<` entry and only local entries.

Merged-in entries are the source mapping's `Entry` objects, so they are already marked if they came through an
alias. A key is **supplied by a merge** exactly when `node.written is not None and node.written.get(key) is None`,
with no extra bookkeeping. Every edit primitive gets the mapping as written: `apply.physical_mapping` (and the
places that pick a layer for `delete` or `add_key`) follow `written` after `layers`. The physical indexes, last
entries and `owned_end` that `ops.py` computes therefore only ever see real text.

*Alternative*: treat `<<` as an ordinary key (YAML 1.2 core has no merge keys). Rejected: people who write `<<: *base`
mean a merge, and `get coder.model` should answer accordingly. See D8.

### D4. The planner raises typed refusals; expansion is a retry loop in `compute_set`
`errors.py` gains two `WriteRefused` subclasses:
- `ThroughAlias(path, alias_path, alias, anchor_path, in_flow)`. Its message names `PATH`, `*name` and
  `alias_path`, says where the anchor is (`anchor_path`, the first non-alias path to the anchored node), and
  mentions `--expand-alias`.
- `MergeKeyWrite(path, holder_path)`. Its message names `PATH` and the `<<` at `holder_path`, and says merge keys
  are not written, so `--expand-alias` cannot help.

In `plan.plan` and `plan._diff`:
- Walking `PATH`, an entry or item with `alias` raises `ThroughAlias` (this covers the alias itself, values below it
  and new keys below it). A key supplied by a merge raises `MergeKeyWrite`.
- `_diff` first returns early when `same(to_data(node), value)`, so an unchanged alias or merged value is a no-op.
  Otherwise it raises the same two errors on reaching an aliased or merge-supplied child. Deleting a merged key
  raises `MergeKeyWrite`. Deleting an alias entry is a plain `Delete`.
- `Replace` and `Delete` of a subtree that holds a `<<` entry raise `MergeKeyWrite`. This is a walker next to
  `_check_no_includes`, which does not descend through aliases, since nothing below an alias is rewritten.
- `new_key_target` is unchanged. Its path was already walked by the checks above.

`compute_set(..., expand_alias=False)` plans in a loop. On `ThroughAlias`, if the flag is set and the alias is not
`in_flow`, it applies an `ExpandAlias(alias_path)` operation, reloads and plans again on the new tree. Otherwise it
re-raises. Each round removes one alias from the text, so the loop ends. Nested aliases on the way are expanded one
round at a time, each with its own comment. A no-op `VALUE` plans to `[]` before any refusal, so nothing is
expanded. Expansion does not change `to_data`, so the expected value, the read-back check and the recorded events
work as before, and only real value changes become events.

*Alternative*: a separate expansion pass that pre-computes every alias on `PATH` and in `VALUE`'s diff. Rejected:
it would duplicate the planner's walk. The retry reuses the one place that knows when a write crosses an alias.

### D5. The copy is the anchored node as written, rendered in block style
`ExpandAlias` is applied by `ops.expand_alias(slot, alias, copy)`. The copy comes from the anchored node **as
written**: the builder's tree for the anchor's file, before include expansion. It is found by `anchor.start`.
`blocks.copy_lines(node, col, layout)` renders it:
- a mapping gives its written entries in order, keys as written;
- a sequence gives `-` items at the list offset from "New collection values";
- a single-line scalar gives its source text (so `'opus'` and `0x10` stay as written, and include strings stay
  includes);
- a multi-line scalar is rendered by `render_value`, the rule for new multi-line values;
- an aliased entry or item gives `*name`;
- an empty collection gives `{}` / `[]`.

Anchors and comments inside the copy are not copied, because node spans exclude anchors (D1). An anchor in the
copy would also re-bind later aliases. A `<<` entry in the node raises `MergeKeyWrite` (merge keys are never
written).

The edits, all in the alias's file:
- remove the whitespace before `*name` and the `*name` itself;
- put a scalar copy at that position;
- add `  # expanded from *name by troupe` at the end of the key's line (the dash's line for an item). When that line
  already ends with a comment, the marker goes after it with two spaces;
- insert a collection copy as lines after that line, at the key's (or dash's) column plus one indentation unit.

Expanding then re-plans (D4), so `VALUE` is written into the copy by the existing primitives, which keep the marker
as an end-of-line comment.

*Alternative*: render the copy from the resolved data with `render_value`. Rejected: nested aliases would silently
become independent copies, include strings would be replaced by included content, and the user's quoting and number
formats would change.

### D6. Replacing an anchored node keeps `&name`
Since spans exclude the anchor (D1), scalar and flow replacements leave `&name` in place without any change. The
block-collection and empty-value replacements insert inline text right after the indicator. `Slot.indicator_end`
becomes "after the indicator, or after the anchor when the node has one on that line", the single place that
decides it. So `a: &x 1` → `a: &x 2`, and `a: &x 1` set to a list gives `a: &x` followed by the list lines.
Deleting an anchored node that an alias still uses is not special-cased. The reload fails ("undefined alias"), and
`_reload` already turns that into exit 3 naming `PATH`.

### D7. CLI
`cli.py` adds `--expand-alias` (`store_true`) to `set`. `commands.set_value(..., expand_alias=False)` passes it to
`compute_set`. `plan` does not take it, because the decision lives in the D4 loop.

### D8. Points the contract leaves open, and what we chose
The contract gives four rules (anchor writes, alias refusal, `--expand-alias`, merge keys never written). Where it
is silent, we took the choice that cannot change a value the user did not name:
- **Merge keys are honoured when reading.** The contract names them, and users write `<<: *base` to get a merge.
  Reading `<<` as a plain key would give answers nobody expects.
- **A merge-supplied value cannot be set, even with `--expand-alias`.** Writing a local key would avoid touching
  `<<`, but merges are shallow. A local mapping would silently replace every merged sub-key, and a local scalar
  would silently start shadowing the anchor. Refusing loses nothing (exit 3, the message says to edit by hand). This
  can be relaxed later without changing other behaviour.
- **Deleting or replacing anything that holds a `<<` is refused.** "Never written" covers removal, and the user can
  still do it by hand.
- **The flag without an alias on the way has no effect.** So re-running a command after the expansion has happened
  succeeds instead of failing, the same reasoning as `--in-include`.
- **The flag also expands aliases reached by a mapping or list `VALUE`'s differences, and nested aliases on the
  way.** "That alias" is any alias the set would otherwise be refused for. Expanding only the first would leave the
  command refused with the flag that asks for expansion.
- **An existing end-of-line comment is kept, and the marker follows it.** Losing a user's comment is not allowed,
  and the marker still ends the key's line.
- **Aliases in flow collections are not expanded** (exit 3). A block-style copy cannot go inside `{…}` / `[…]`.
- **The copy is the node as written** (D5), with nested aliases kept. "Other aliases still refer to the anchor"
  includes those inside the anchored node.
- **Paths through an alias inside an included file, or in the included layer of a mapping-form include, are
  refused**, even when an override would be written elsewhere. This refuses more than strictly needed, and it
  cannot write through an anchor.

## Risks / Trade-offs

- [Shared node objects are mutated by the loader or merge] → D2's memo. `merge` already builds new nodes rather
  than mutating, and a test loads a file with an anchored include used twice and checks both paths.
- [Spans excluding properties break a primitive that looked back from `node.start`] → the full existing suite runs
  unchanged against unanchored files (their spans do not move). New tests cover replace, delete and add next to
  anchored scalars and block and flow collections. The read-back check turns any miss into exit 3.
- [Alias marker lost in merged layers, letting a write go through an anchor] → D2 copies `alias` in `merge`, and a
  test covers a mapping-form include whose included file has an alias. `_matches` would not catch a write through
  the anchor, because the aliases change consistently, so this one needs its test.
- [Copy rendering differs from what the parser reads back] → the read-back check after the final set compares
  values. A copy that reads back differently is exit 3.
- [Merge key resolution order differs from other tools] → we follow the YAML merge-key spec: local keys win, then
  earlier sources. Tests pin it.

## Migration Plan

No data migration. The event store is untouched and new events are ordinary `set`/`remove` events. Rolling back to
earlier code makes configurations with anchors fail to load (exit 4) again, and history recorded meanwhile stays
readable. README decision 8 is replaced by the new rules and the D8 choices.
