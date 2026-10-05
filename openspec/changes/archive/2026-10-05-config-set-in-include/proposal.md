# Proposal

## Why

After `config-include-overrides` (CR-A), a new key under an included section is always written as an override in the
including file. Sometimes the setting really belongs in the shared file, for every theatre that includes it. Change
request CR-B gives `set` an explicit way to say so, without editing the shared file by hand.

This change builds on `config-include-overrides`, which must be implemented first.

## What Changes

- `troupe config set PATH VALUE --in-include` (the flag may appear anywhere after `set`, like `--reason`) writes each
  new key into the file that holds its deepest existing ancestor mapping, with missing intermediate mappings created
  there. This is the step-1 rule, so a new key under an include goes into the included file and no override is
  written.
- The flag changes only where *new keys* go. Existing values (overridden or not), list appends, deletions and the
  "refusing to replace an include" rule behave exactly as without it.
- Without the flag, behaviour is unchanged from `config-include-overrides`.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `config-cli`: "Invocation and theatre selection" lists `set PATH VALUE [--reason TEXT] [--in-include]`.
- `config-set`: new requirement "Writing new keys into the included file on request".

## Impact

- Code: `cli.py` (flag), `commands.set_value` and `edit/apply.compute_set` (pass the choice through), and
  `edit/plan.py`, where `new_key_target` takes the choice. No loader, store or history changes.
- Tests: CLI parsing of the flag, and write-back targets with the flag (included file, nested includes, merged
  ancestors, no include at all, mapping VALUEs, existing values unaffected).
- README: commands table, includes section, decisions list.
