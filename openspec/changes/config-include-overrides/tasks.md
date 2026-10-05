# Tasks

## 1. Loading mapping-form includes

- [x] 1.1 Add `src/troupe/overrides.py` (D1): `REF_KEY`, `ref_string`, `merge` building new nodes with `layers` and the merged key order; add `Include.overrides` and `MappingNode.layers` to `tree.py` (D2); verify `uv run mypy` and `uv run ruff check` are clean
- [x] 1.2 Load mapping-form includes in `loader._Loader.expand` (D3): expand overrides in the including file's context, reuse `include(...)`, set `include.overrides`, merge, and raise `LoadError` naming the `$ref` file and the target for overrides on a text include or on non-mapping content (list, scalar, empty file); verify the existing `uv run pytest tests/test_loading.py tests/test_show.py tests/test_show_sources.py` still pass
- [x] 1.3 Add `tests/test_overrides_loading.py` through the real CLI for every config-loading "Mapping-form includes and overrides" scenario: deep merge with byte-exact `show` output (key order, nested merge, list replaces, extra key), override mapping replaced by a scalar, mapping form without overrides equals scalar form, text include in mapping form, exit 4 with stderr naming both files for text-with-overrides and for list / scalar / empty content, include inside an override resolved against the including file, mapping form inside an included file, `$ref: hello` as an ordinary key, missing target exits 4; verify they pass, and that making `merge` replace instead of recurse fails the deep-merge test
- [x] 1.4 Add the "Sources with overrides" scenario to `tests/test_show_sources.py`; verify it passes, and fails if a merged entry takes the included layer's node

## 2. Writing new keys as overrides

- [x] 2.1 Add `AddOverride` and `plan.new_key_target` (D4), used for every `AddKey` that `plan` and `_diff` emit; verify `uv run mypy` is clean
- [x] 2.2 Add `ops.to_mapping_form` with its four cases (block entry, block list item, document root, flow) (D6), and resolve `AddOverride` in `apply._apply` (walk the physical override mapping, then `add_key`; convert otherwise); assert that `add_key`/`delete`/`replace` targets have no `layers`; verify `uv run mypy` and `uv run ruff check` are clean
- [x] 2.3 Replace `test_new_key_inside_an_included_mapping_goes_into_that_file` in `tests/test_set_targets.py` with the "New key inside an included mapping" override scenario, and add `tests/test_set_overrides.py` with byte-exact checks (every file in the theatre compared) for each scenario of "New keys under includes are written as overrides": contract example with comment, indentation 4, existing mapping form, ancestor deeper in the included file, into an existing override mapping, missing intermediates, file included twice (and `get b.k` exits 5), quoted include string, flow mapping, list item, whole-document include, nested include (nearest including file), key inside a list item of an included file, CRLF; verify they pass, and that each fails if `new_key_target` returns a plain `AddKey`
- [x] 2.4 Add to `tests/test_set_overrides.py` the "Appending to lists" scenarios (append in an included file, append to an overridden flow list) and a test that `set` with a mapping VALUE adding a key under an included mapping (`set coder.limits "{tokens: 100, calls: 9}"`) writes the override; verify they pass

## 3. Existing values, deletes and include equality

- [x] 3.1 Make `_slot` pick the winning layer's entry and `Delete` remove a key from every layer, moving up past emptied override mappings and stopping at `$ref` mappings (D5); verify `uv run mypy` is clean
- [x] 3.2 Make `_diff` and `_matches` treat the bare include string as equal only when the include has no overrides (D5); verify the existing `tests/test_set_targets.py` include tests still pass
- [x] 3.3 Add tests for the modified config-set requirements: overridden value changes the override; non-overridden value changes in the included file; deleting an overridden key (both files byte-exact); replacing an overridden mapping by a scalar; `set coder file:agents/coder.yaml` with overrides exits 3 naming `coder` with no file changed; parent set that keeps the merged value changes only `other`; verify they pass, and that the delete test fails if only the override layer is deleted

## 4. Reconcile, watch and documentation

- [x] 4.1 Add to `tests/test_reconcile.py` the config-sync scenarios "Override added by hand" (event `set coder.temperature` 0.2 → 0.3, via `file`) and "Converting to mapping form records nothing", and to `tests/test_watch.py` "File included through $ref is watched"; add a `history` check that `set coder.temperature 0.3` on a scalar-form include whose file has no `temperature` records one `set` event for `coder.temperature` (old null) via `cli`; verify they pass
- [x] 4.2 Add a smoke test through `uv run troupe config` that sets a new key under a scalar-form include and checks `troupe.yml`, the unchanged included file and `show --sources`; verify it passes
- [ ] 4.3 Update README: an "Includes" section describing mapping form, `$ref`, deep merge, where `set` writes (new keys as overrides, existing values where they live, lists, deletes), the exit 4 cases, the BREAKING note for existing `$ref: file:` data and step-4 rollback; a worked example; `overrides.py` in the code map; design decisions D3–D6 and each D9 choice with its reason appended to the decisions list, with this change's design.md added to the referenced files; verify each new README command runs as written against `/tmp/demo`

## 5. Integration

- [ ] 5.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check` and `uv run ruff format --check`; verify all are clean and show the output
- [ ] 5.2 Run `openspec validate config-include-overrides --strict`; verify it reports the change as valid
- [ ] 5.3 Commit the work on `main` in small steps with messages that say why (no push, no PR); verify `git status` is clean and `git log` shows the commits
