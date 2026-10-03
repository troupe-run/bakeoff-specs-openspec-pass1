# Tasks

## 1. The get command

- [ ] 1.1 Add the `get PATH` subparser in `cli.py` and `commands.get()` (D1, D6): today's scalar lookup, with the collection refusal message naming the path and `config show`; add `"get"` to `RECONCILING_COMMANDS`; verify `uv run troupe config get` with no PATH exits 2 with a usage message
- [ ] 1.2 Move the scalar, include, list-index, hand-edit and refusal tests from `tests/test_show.py` to `tests/test_get.py` running `get`, and add tests that `get` on a mapping and on a list exits 5 with empty stdout and stderr containing the path and `config show` (config-get spec); verify they pass
- [ ] 1.3 Add `get` cases to `tests/test_reconcile.py` (hand edit then `get a` records `set a` once; `get nope` exit 5 keeps the reconcile event) per the config-sync delta; verify they pass

## 2. Rendering YAML

- [ ] 2.1 Add `src/troupe/render.py` (D2–D5): walk nodes into `Line(text, source)` lines, use `edit.scalars.render_scalar`/`render_key` and `edit.blocks.literal` for scalars (text includes always tried as literal blocks, fallback to `render_scalar`), and add `source_label()` for lexical theatre-relative paths; verify `uv run mypy` and `uv run ruff check` are clean
- [ ] 2.2 Add `tests/test_render.py` round-trip tests: for a table of tricky configurations (multi-line strings with 0/1/2 trailing newlines, leading-space first lines, CRLF text includes, empty text include, `.nan`/`-.inf`, strings `true`/`0.2`/`- x`/`#x`/`a: b`/empty, nested lists, lists of mappings, unicode, empty mapping/list), read the output of the renderer with and without sources back with `tree.build_tree` + `to_data` and compare with `schema.same` against the loaded data; verify they pass and that breaking quoting (e.g. forcing plain) makes them fail
- [ ] 2.3 Add unit tests for `source_label`: config file, nested include, `..` include normalised, include outside the theatre gives `../`, relative `--theatre`; verify they pass

## 3. The new show command

- [ ] 3.1 Change the `show` subparser to an optional `path` plus `--sources`, and `commands.show(theatre, path | None, sources)` (D1, D6): scalar without `--sources` prints `show_text`, otherwise `render.render`; no path means the whole configuration; missing paths still exit 5; verify `show` and `show --sources` on a loading theatre exit 0
- [ ] 3.2 Rewrite `tests/test_show.py` with the config-show scenarios checked byte for byte: whole configuration with includes, a section, a list, list of mappings, one-line text include (`|-`), strings that need quoting, scalar types kept, empty collections and empty config (`{}\n`), `show` of a scalar equals `get` (including a text include), missing key and descending into a scalar exit 5 naming the path, nothing on stderr; verify they pass
- [ ] 3.3 Add `tests/test_show_sources.py` with the "Show sources" scenarios checked byte for byte: sources across includes, a section, a scalar and a text include with `--sources`, empty included YAML file, `..` include labelled `.troupe/b.yaml`, `troupe.yaml` name, `--sources` before or after PATH; verify they pass
- [ ] 3.4 Update callers of the old refusal: in `tests/test_smoke.py` change `show agents` → 5 to `get agents` → 5, and add a `uv run troupe config show --sources` smoke test with an include; make the "user files untouched" test in `tests/test_cli.py` also run `get`, `show` and `show --sources` (config-cli delta); verify `uv run pytest` passes in full
- [ ] 3.5 Update README: commands table (`get PATH`, `show [PATH] [--sources]`), an example of `show --sources` output, the breaking change and how to migrate (`get`), `get` in the reconcile paragraph, and the design.md decisions in the decisions list; verify each README command runs as written against `/tmp/demo`

## 4. Integration

- [ ] 4.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check` and `uv run ruff format --check`; verify all are clean and show the output
- [ ] 4.2 Run `openspec validate config-get-and-show --strict`; verify it reports the change as valid
- [ ] 4.3 Commit the work on `main` in small steps with messages that say why (no push, no PR); verify `git status` is clean and `git log` shows the commits
