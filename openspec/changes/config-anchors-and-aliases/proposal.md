# Proposal

## Why

Bug report troupe-run/bakeoff-specs-openspec-pass1#2: teams share settings between agents with YAML anchors
(`defaults: &d` … `settings: *d`). When `set coder.settings.model sonnet` follows the alias, it edits the anchor,
which silently changes `defaults` and every other agent that uses `*d`. The reporter expects the opposite. Changing
the anchor (`defaults.model`) should change everyone. Changing one user of the alias should be refused, and
`set` should offer an explicit way to give that user its own copy.

On `main` today, anchors and aliases fail to load (exit 4, README decision 8), so these configurations cannot be
used at all. The contract now adds an **Aliases** section (step 6) that defines how they behave. This change adds
anchor and alias support under those rules, so the reported behaviour cannot occur.

## What Changes

- **Loading**: anchors (`&name`), aliases (`*name`) and merge keys (`<<`) load. An alias has the value of its
  anchored node. A merge key adds the entries of the mapping(s) it names, and the mapping's own keys win.
  `get`, `show`, `show --sources`, `history`, import and reconcile all see the resolved values. Undefined aliases,
  anchors or aliases used as mapping keys, and merge keys whose value is not a mapping (or a list of mappings) fail
  to load (exit 4).
- **Setting at an anchor**: setting a path whose value is defined at an anchor changes it there, keeping the
  `&name`, so every alias sees the new value. History records an event for every path whose value changed.
- **Setting through an alias**: setting a path reached through an alias (`*name`) is refused with exit 3, and
  no file changes. stderr names the path and the alias, and mentions `--expand-alias`.
- **`set --expand-alias PATH VALUE`** (new flag): replaces the alias on the path with a block-style copy of the
  anchored node. It adds the end-of-line comment `# expanded from *<name> by troupe` (two spaces before `#`) on
  the key's line, then sets the value in the copy. Nothing else changes, and other aliases still refer to the
  anchor. Without an alias on the way, the flag has no effect.
- **Merge keys are never written**: any `set` that would add, change or delete a `<<` entry, or change or delete
  a value that a merge key supplies, is refused with exit 3. That includes `--expand-alias` and copies that would
  contain a `<<`.
- README: the exit-4 rule for anchors (decision 8) is replaced by the new behaviour and its decisions.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `config-loading`: new requirement "Anchors, aliases and merge keys".
- `config-set`: new requirements "Setting a value defined at an anchor", "Refusing to set through an alias",
  "Expanding an alias on request" and "Merge keys are never written".
- `config-cli`: "Invocation and theatre selection" lists `set PATH VALUE [--reason TEXT] [--in-include]
  [--expand-alias]`.

## Impact

- Code: `tree.py` (build anchors, aliases and merge keys instead of refusing them, and record where each is
  written), `loader.py` (expand includes once per anchored node), `edit/plan.py` (detect paths through aliases and
  merge keys), `edit/apply.py` (the expand-then-retry loop and keeping `&name` on replace), `edit/ops.py` and
  `edit/blocks.py` (writing the copy), `cli.py` and `commands.py` (the flag). The store, history format and
  rendering for `show` do not change.
- Tests: `test_anchors_are_refused_at_load` is replaced. New tests cover loading, setting at an anchor, refusing
  through an alias, expansion, merge keys and the CLI flag.
- Compatibility: configurations that failed to load before now load. Going back to earlier code makes them fail
  to load again (exit 4), and the history recorded meanwhile stays valid.
