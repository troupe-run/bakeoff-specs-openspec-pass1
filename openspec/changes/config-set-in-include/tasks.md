# Tasks

## 1. Prerequisite

- [x] 1.1 Confirm `config-include-overrides` is implemented and committed on `main` (all its tasks checked, `uv run pytest` passing); verify by running `openspec status --change config-include-overrides` and `uv run pytest`

## 2. The flag and the target rule

- [x] 2.1 Add `--in-include` (`store_true`) to `set` in `cli.py` and thread `in_include` through `commands.set_value`, `compute_set`, `plan` and `_diff` to `new_key_target`, which returns a plain `AddKey` when it is set (D1); verify `uv run mypy` and `uv run ruff check` are clean
- [x] 2.2 Add `physical_mapping` in `edit/apply.py` and use it to resolve `AddKey` parents, with the "no `layers`" assertion on its result (D2), and make sure `merge` flattens layers so `layers[0]` is the innermost included mapping; verify the existing `uv run pytest` suite (including the override tests) still passes
- [x] 2.3 Add `tests/test_set_in_include.py` through the real CLI with byte-exact checks on every file in the theatre for each "Writing new keys into the included file on request" scenario: into the included file (comment line kept), mapping form with overrides, merged ancestor, override-only ancestor, missing intermediates, nested includes (innermost file), mapping VALUE, existing overridden value still changes the override, no include involved (same bytes as without the flag), empty included file exits 5 with no change, one `cli` event identical in content to the flag-less run; verify they pass, and that the merged and nested-merged tests fail if `physical_mapping` returns `layers[-1]` (the plain nested case has no merged layers, so a nested case with a `$ref` mapping in the middle file was added)
- [x] 2.4 Extend `tests/test_cli.py` with "set takes an optional --in-include" (both positions, with `--reason`) and `set model b --in-include x` exiting 2 with empty stdout; verify they pass
- [x] 2.5 Add a smoke test through `uv run troupe config set … --in-include` that checks the included file gained the key and `troupe.yml` is unchanged; verify it passes
- [ ] 2.6 Update README: `set PATH VALUE [--reason TEXT] [--in-include]` in the commands table, a paragraph in the includes section on writing into the shared file on purpose (with an example), and the D3 choices with their reasons appended to the decisions list, with this change's design.md added to the referenced files; verify each new README command runs as written against `/tmp/demo`

## 3. Integration

- [ ] 3.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check` and `uv run ruff format --check`; verify all are clean and show the output
- [ ] 3.2 Run `openspec validate config-set-in-include --strict`; verify it reports the change as valid
- [ ] 3.3 Commit the work on `main` in small steps with messages that say why (no push, no PR), archiving `config-include-overrides` before this change; verify `git status` is clean and `git log` shows the commits
