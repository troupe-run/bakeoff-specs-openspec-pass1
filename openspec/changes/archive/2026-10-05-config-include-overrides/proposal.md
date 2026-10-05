# Proposal

## Why

Included files are shared between projects (theatres). Today `set` writes a new key under an included section into
the included file itself, so adding `agents.coder.temperature` in one theatre silently changes every other theatre that
includes `agents/coder.yaml`. Step 5 (change request CR-A) keeps shared includes shared: new settings under an include
are written as **overrides** in the including file. Existing settings still change where they live.

## What Changes

- **Mapping-form includes.** An include may be written as a mapping with a `$ref` key whose value is the include
  string (`coder: {$ref: file:agents/coder.yaml, temperature: 0.3}`, usually in block style). Its other keys are
  overrides: the value is the included content deep-merged with them (mappings merge recursively; a scalar or list in
  the override replaces). `get`, `show`, `show --sources`, `history`, reconcile and `watch` all see the merged value,
  and `--sources` names the file each scalar is actually written in.
- A mapping-form include of a non-YAML file with sibling keys fails to load (exit 4). So does one with overrides
  whose included content is not a mapping (design D3).
- **BREAKING (write-back target):** a new key whose deepest existing ancestor comes from an included file is now
  written as an override in the file that contains the include reference, not in the included file. A scalar-form
  include is first converted to mapping form, keeping any end-of-line comment on the key's line:
  `coder: file:agents/coder.yaml  # c` → `coder:  # c` / `  $ref: file:agents/coder.yaml` / `  temperature: 0.3`.
- Appending a list item, and adding a key inside a list item, still write into the file that holds the list
  (overrides cannot address list items).
- Setting an existing value that is overridden changes the override. A value that is not overridden is still changed
  in the file it comes from (unchanged behaviour).
- Replacing a whole include is still refused (exit 3). A mapping-form include with overrides is "the same value"
  only if the merged data is equal, not when VALUE is the bare include string (design D7).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `config-loading`: new requirement "Mapping-form includes and overrides": `$ref` syntax, deep-merge rules, key
  order, and the load failures (non-YAML with overrides, overrides on non-mapping content).
- `config-set`: "Creating new keys" no longer writes into included files; new requirement "New keys under includes
  are written as overrides" (target file, scalar-to-mapping conversion, list rule); "Target file for an existing
  value" covers overridden values; "Refusing to replace an include" covers mapping-form includes; "Setting a
  collection value" says how deleting a key that has an override works.
- `config-show`: "Show sources" names the overriding file for overridden scalars (new scenario).

## Impact

- Code:
  - `loader.py`: recognise mapping-form includes and merge overrides; `tree.py`: an included node records its
    override mapping, and a merged mapping records the physical mappings (layers) it was built from.
  - `edit/plan.py`, `edit/apply.py`: one function decides where a new key is written; deletes and replacements of
    overridden values go to the override layer.
  - `edit/ops.py`: a new primitive converts a scalar-form include to mapping form.
- Tests: the existing test "new key inside an included mapping goes into that file" is replaced by its opposite. New
  tests cover loading, merging, show/sources, write-back targets, conversion (block, flow, list item, CRLF, comments),
  exit 4 cases, reconcile and `watch` of files reached through `$ref`.
- README: includes section, decisions list.
- No new dependencies. The event store and history format are unchanged (history records merged leaf values).
