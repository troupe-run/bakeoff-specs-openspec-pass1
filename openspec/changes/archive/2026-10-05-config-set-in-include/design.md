# Design

## Context

See proposal.md for the motivation and `specs/` for the behaviour. This change is built on `config-include-overrides`
(its design.md is referred to as "A-D<n>" below), which must be implemented first:

- `plan.new_key_target` (A-D4) is the one place that decides where a new key goes. It returns a plain
  `AddKey(path, value)` when no include anchors the deepest existing ancestor A, and otherwise
  `AddOverride(include_path, rel, value)`.
- Merged mappings carry `layers`: the physical mappings they were built from, the included one first (A-D2).
  `_apply` asserts that `add_key` targets a mapping without `layers`.
- `cli.py` parses `set PATH VALUE [--reason TEXT]`, and `commands.set_value` calls `compute_set`, which calls `plan`.

## Goals / Non-Goals

**Goals:**
- The flag changes one decision, in the one place that makes it (`new_key_target`), and nothing else.

**Non-Goals:**
- Making the flag the default, or a per-theatre setting.
- Recording the flag in history. The events say what changed, and the files show where.
- Moving an existing override into the included file, or the other way round.

## Decisions

### D1. The choice is a keyword argument passed down to `new_key_target`
`cli.py` adds `--in-include` (`store_true`) to `set`. `commands.set_value(..., in_include: bool = False)` passes it to
`compute_set`, then `plan`, then `_diff`, then `new_key_target(root, path, in_include=...)`. With `in_include=True`,
`new_key_target` always returns `AddKey(path, value)`, so the anchor walk is skipped. Alternative: a separate planner
mode or a post-pass that rewrites `AddOverride` into `AddKey`. Rejected: two places would know the rule.

### D2. `AddKey` writes into the innermost physical layer
`_apply` resolves an `AddKey` parent through `physical_mapping(node)`: `node.layers[0]` when the node is merged,
otherwise `node`. This helper lives next to `_slot` in `apply.py`. `merge` flattens layers (a merged base contributes
its own layers first), so `layers[0]` is always the innermost included file's mapping. That gives the spec's cases:
- an included mapping with no overrides is physical already, so the key goes into the included file;
- a mapping merged from included content and overrides goes into the included content's file;
- a mapping that exists only in an override is physical in the overriding file, so the key goes there;
- nested includes go to the innermost included file (`agents/limits.yaml`), which is the step-1 rule's "file
  containing the deepest existing ancestor".
Without the flag, `AddKey` only ever reaches physical mappings (A-D4), so the helper changes nothing there. The
existing "no `layers`" assertion moves to the `physical_mapping` result.

### D3. Points the contract leaves open, and what we chose
The contract says only that `set --in-include PATH VALUE` "writes a new key into the included file instead (the step
1 rule)". Each choice below follows the reading that changes least:
- **Only new keys are affected.** The contract talks about new keys. Existing values keep CR-A's rule (an overridden
  value changes the override), so the flag can never silently leave an override shadowing the value just written.
- **Where no include is involved, the flag is accepted and changes nothing.** The step-1 rule is defined for every
  path and gives the same file there. Refusing would make scripts check for includes before passing the flag.
- **A merged ancestor goes into its included content's file, and an override-only ancestor into its override's
  file.** "The included file" is where the ancestor's shared content lives. An ancestor that exists only in an
  override has no included file, and the step-1 rule ("the file containing the deepest existing ancestor") names the
  override's file.
- **Nested includes go to the innermost included file.** That is the file containing the deepest existing ancestor.
- **No new exit codes, and events are unchanged.** `--in-include` changes placement, not meaning, and history
  records values, not files.

## Risks / Trade-offs

- [A key written into the shared file changes every theatre that includes it] → This is the purpose of the flag.
  It is opt-in, and the default (CR-A) keeps shared files untouched.
- [This change depends on unimplemented work in `config-include-overrides`] → tasks.md starts by checking that
  change is implemented. The archive order is `config-include-overrides` first, then this change.

## Archive decision

The change was archived with its delta specs **synced** into `openspec/specs/`, for the same reason as
`config-include-overrides`. Archiving without syncing would leave the main specs without `--in-include` while the
code, tests and README have it, contradicting the rule that spec, code and tests agree. Syncing changes only spec
files and keeps every existing scenario.
