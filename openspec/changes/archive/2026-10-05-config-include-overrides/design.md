# Design

## Context

See proposal.md for the motivation and `specs/` for the exact behaviour. What exists today (after step 4):

- `loader._Loader.expand` walks the tree built from each file and replaces every include string with the included
  root, in place. The included root gets `node.include = Include(string, target)`. A text include becomes a
  `TextNode` that keeps the string's span. Every node keeps its own `SourceFile` and offsets, which is what makes
  `show --sources` and byte-surgical write-back work across files.
- `set` (`edit/apply.compute_set`) plans path-based operations (`edit/plan.py`: `Replace`, `AddKey`, `Append`,
  `Delete`, `WriteText`). It applies them one at a time, reloading from the edited texts before each one, so every
  operation finds its node by path in a fresh tree (`_node_at`, `_slot`). It then verifies that the result reads back
  as the intended data (`_matches`). Primitives in `edit/ops.py` produce `Edit`s for one file. `apply_edits` accepts
  several non-overlapping edits to one text.
- `plan` sends `AddKey` to the deepest existing ancestor mapping, which today may sit in an included file. The plan
  refuses to replace or delete an include root unless the data stays equal (`_diff`, `_check_no_includes`).
- History, reconcile and `watch` work on data (`to_data`, `leaves`) and on `config.files` (every file the loader
  read). `render` prints from nodes and takes each scalar's source from `node.file`.

## Goals / Non-Goals

**Goals:**
- The merge rule, the `$ref` syntax and the "where does a new key go" rule each live in one named place.
- The merged tree is still a tree of physical nodes wherever a value is physically written, so `--sources`, scalar
  replacement, appends and the verifier keep working without special cases.
- No change to the event store, history format or lineage.

**Non-Goals:**
- Deleting a key by override (a "tombstone"). Overrides can only add or replace. A deleted key is removed from every
  file that sets it (spec "Setting a collection value").
- Addressing list items through overrides, or merging lists.
- Converting a mapping-form include back to scalar form when its last override is removed.
- Replacing a whole include through `set` (still exit 3).

## Decisions

### D1. A new module `overrides.py` holds the override rules
```python
REF_KEY = "$ref"
def ref_string(mapping: MappingNode) -> ScalarNode | None   # the $ref value if it is an include string
def merge(base: MappingNode, override: MappingNode) -> MappingNode   # deep merge, new nodes, inputs untouched
```
`loader.py` calls them, and `edit/plan.py` and `edit/apply.py` use `REF_KEY`. The rules (what counts as mapping
form, mapping-vs-mapping recursion, replacement otherwise, key order) live only here. Alternative: put them in
`loader.py`. Rejected because the write side needs the same rules, and `loader.py` is about files and includes.

### D2. Merged mappings remember their layers; included roots remember their overrides
- `Include` gains `overrides: MappingNode | None`: the physical `$ref` mapping in the including file, as loaded
  (its values expanded, never merged into). `include.string` is the `$ref` value for mapping form.
- `MappingNode` gains `layers: list[MappingNode]`: for a node built by `merge`, the physical mappings it was built
  from, the included one first and overrides after it in the order they apply. It is empty for a physical mapping.
- A merged mapping's `entries` are the winning `Entry` objects of their layers (physical key and value nodes), except
  that a key both layers hold as mappings gets a newly merged node. Its `file`/`start`/`end`/`owner_col` are those of
  the included layer. They are never used for edits (D5).
- A merged node's `include` is that of the include whose root it is. When an override value is itself an include
  root that merges with base content, the merged node takes the override's include, since that is the nearest one.

So every scalar, list and unmerged mapping in the tree is the physical node that the value is written in, and
`render`, `Replace` on scalars, `Append` and `WriteText` stay unchanged. Alternative: keep the physical tree and
compute merged data separately. Rejected: `get`/`show`/`--sources`/reconcile/verify would all need a second path.

### D3. Loading a mapping-form include
In `_Loader.expand`, a `MappingNode` whose `ref_string` is not `None` is an include. Its non-`$ref` entries are
expanded first, in the including file's directory and with the including file's stack. Then the target is loaded by
the existing `include(...)` path (cycle and missing-target checks unchanged). If there are no other entries, the
result is exactly the scalar-form result (text includes included), with `include.overrides` set. Otherwise a
`TextNode` result, or an included root that is not a `MappingNode` (a list, a scalar, or the null of an empty file),
raises `LoadError` naming the `$ref` mapping's file and the target (exit 4). The spec leaves merging a mapping into a
non-mapping undefined, so we refuse rather than guess. A `$ref` whose value is not an include string leaves the
mapping ordinary. That is the literal reading of the contract and keeps existing files loading as before.

### D4. One function decides where a new key goes: `plan.new_key_target`
`plan` calls it wherever it would emit `AddKey`, including for new keys found by the mapping diff. Given the merged
root and the path of the deepest existing ancestor mapping A, it walks down from the root and tracks an *anchor*:
entering a node with `include` sets the anchor to (that include's path, relative path `()`), descending through a
mapping key extends the relative path, and descending into a list item clears the anchor. Result:
- no anchor at A → `AddKey(path, value)` as today; A is physical there (merged nodes only exist under includes);
- anchor (Q, R) → `AddOverride(include_path=Q, rel=R + rest, value)`, a new `Op`.

`_apply` resolves `AddOverride` on the fresh tree. If the include at Q has `overrides`, it walks `rel` through the
physical override mapping as far as keys exist, then calls `prim.add_key` on that mapping with the remaining keys
nested (`_nest`), so the placement, quoting and indentation rules are the existing ones. If not, it calls
`prim.to_mapping_form(include.string, slot, entries)` (D6). The included file never receives an `AddOverride` edit.

**Nested includes (confirmed by the product owner):** the anchor is the *nearest* include, so a key under
`coder.limits`, where `agents/coder.yaml` includes `limits.yaml`, is written in `agents/coder.yaml`. The contract
defines the including file as "the file that contains the include reference". With nested includes, that is the file
holding the reference to the include that the key's deepest existing ancestor comes from. Always writing into the
root config file was considered and rejected: it is not the contract's definition.

### D5. Existing values and deletions go to physical layers
- `_slot(parent, key)` takes the key's entry from the last layer of `parent.layers` that has it (or from `parent`
  itself when it has no layers). `Replace` therefore edits the override that sets a value, and the included file when
  none does. A merged mapping replaced by a non-mapping is replaced in its outermost override layer, because its
  winning entry is the override's.
- `Delete(path)` on a merged parent deletes the key from every layer that has it, applying the edits per file. If
  that would leave an override sub-mapping empty, the delete moves up and deletes that mapping's entry from its
  parent override instead, repeating while the parent would become empty. It stops at a mapping that holds `$ref`.
- `_diff` treats a VALUE equal to the include string as "unchanged" only when `include.overrides` has no entries
  besides `$ref`. With overrides, the existing rule "whole include differs → exit 3" applies. `_matches` uses the same
  condition.

### D6. Converting to mapping form: `ops.to_mapping_form`
One primitive with four cases, by where the include string sits:
- block mapping value: delete from the whitespace before the string through its end. The rest of the line is kept
  (`coder:  # c`, as in the contract's example, not the column-keeping rule of "Scalar replaced by a block
  collection"). Then insert `$ref: <string as written>` and the override entry lines at key column + `layout.unit`
  of the including file;
- block list item: insert `$ref: ` before the string and the entry lines at the string's column (compact
  `- $ref: …` form). This is the smallest edit, and it keeps a comment on the item's line;
- document root: insert `$ref: ` before the string, entries at column 0;
- flow: replace the string with `{$ref: <string>, k: v}` via `flow_text`, with end-of-line comment alignment from
  `inline_edit`.
The include string's own bytes (and quotes) are copied, never re-rendered. Entry lines come from `entry_lines`, so
nested intermediates, multi-line strings and collections follow the existing new-value rules.

### D7. Verification stays the safety net
The verifier (`_matches` against `_with_value`) already compares the reloaded merged tree with the intended data.
Any case D4–D6 gets wrong (for example an override that would not merge as expected) is refused with exit 3 and
nothing written, rather than written wrongly. Setting a key named `$ref` falls here as well: if its value is an
include string, the mapping becomes an include and the data no longer matches.

### D8. Reconcile, history and `watch` need no code change
They see merged data and `config.files`, which includes every file reached through `$ref`. Tests prove it (spec
config-sync scenarios) instead of new code.

### D9. Points the contract leaves open, and what we chose
The product owner confirmed which of these are out of contract. Each choice and its reason:
- **Overrides on non-mapping YAML content (list, scalar, empty file) → exit 4.** "Deep-merge" is only defined
  between mappings. Any other reading means guessing: drop the included content, ignore the overrides, or treat null
  as `{}`. Each guess can show a value the user did not write. Refusing to load names both files, loses nothing and
  can be relaxed later without breaking anyone. An empty file is treated the same, because it loads as null (spec
  config-show "Empty included YAML file"), not as a mapping.
- **`$ref` whose value is not an include string → ordinary key.** The contract defines mapping form only for "a
  `$ref` key whose value is the include string". Treating other values as ordinary keys keeps every existing file
  loading exactly as before, and `show` makes such a key visible. The alternative, exit 4, would turn a file that
  loads today into one that fails, for a case the contract does not mention.
- **Deleting a key that both the included file and an override set → removed from both.** The contract covers
  changing a value, not deleting one that two files set. Overrides cannot delete (there is no tombstone syntax). So
  removing only the override would let the included value reappear, and `set` would not do what was asked (the
  verifier would refuse it with exit 3). Removing it everywhere does what the user asked. The included file still
  changes only for a deletion of a key it holds, as it does today for keys that are not overridden.
- **An override mapping left empty by a delete is removed; a `$ref` mapping is kept.** An empty override such as
  `limits: {}` changes nothing in the merged value, so it would only be clutter the user did not write. The `$ref`
  mapping is kept in mapping form, with no conversion back to scalar form, so that the delete changes only the lines
  it must.
- **A list item that is an include converts to `- $ref: STRING` with the overrides below, at the string's column.**
  The contract fixes the layout only for a mapping entry. The compact form is the smallest edit: it inserts `$ref: `
  and new lines, and leaves the item's line, including an end-of-line comment, otherwise intact. It is also the form
  `show` uses for list items that are mappings. The alternative, a bare `-` followed by an indented mapping, rewrites
  more of the line and leaves an unusual dangling dash.
- **`set PATH STRING` on a mapping-form include that has overrides → exit 3** (covered by the contract: it replaces a
  value whose whole value comes from an include).

## Risks / Trade-offs

- [Merged nodes carry the included layer's offsets; an edit computed from them would land in the wrong file] → D5
  routes every edit through physical layers, `_apply` asserts that the target of `add_key`/`delete`/`replace` has
  no `layers`, and D7 refuses anything that slips through.
- [**BREAKING**: a theatre whose files contained a mapping with a `$ref: file:…` key as plain data now loads it as
  an include] → This is unlikely in troupe configurations. It is noted in the README decisions. The data stays in
  the files, unchanged.
- [Deleting an overridden key also edits the shared file] → This is the only way to make the key absent, since
  overrides cannot delete (Non-Goals). The spec states it, and it applies only to deletions the user asked for.
- [Rolling back to step-4 code after overrides are written] → Step 4 reads a `$ref` mapping as an ordinary mapping,
  so values differ and a reconcile would record that. The README notes that mapping-form includes need step 5.

## Migration Plan

Nothing to migrate: scalar-form includes load as before. Only new writes produce mapping form. Rolling back means
removing `$ref` mappings by hand (see Risks).

## Archive decision

The change was archived with its delta specs **synced** into `openspec/specs/`. The brief did not say whether to
sync. Archiving without syncing would leave the main specs describing step-4 behaviour (new keys written into the
shared file) while the code and tests do the opposite. That contradicts the contract and the rule that spec, code
and tests agree. Syncing changes only spec files, keeps every existing scenario, and matches how every earlier change
was archived.
