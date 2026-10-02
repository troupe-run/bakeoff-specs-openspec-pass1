# Tasks

## 1. Project scaffolding

- [x] 1.1 Create `pyproject.toml` (Python >=3.12, `src/troupe` layout, `troupe = "troupe.cli:main"` script; deps `eventsourcing`, `ruamel.yaml`; dev deps `pytest`, `mypy`, `ruff`; mypy `strict = true`; ruff config). Run `uv sync` and verify `uv run troupe --help` exits 0
- [x] 1.2 Add `src/troupe/errors.py` with the `TroupeError` hierarchy and exit codes (D1), plus a `cli.py` skeleton with `show`/`set`/`history` subcommands and `--theatre`. Verify `uv run troupe config bogus` exits 2 with empty stdout, and `uv run mypy src tests` and `uv run ruff check` are clean
- [x] 1.3 Add `.gitignore` (`.venv`, caches), commit `uv.lock`, and verify `git status` shows no stray files

## 2. Core schema, paths and values

- [x] 2.1 Implement `schema.py` (core-schema resolution of plain scalars and `format_scalar`). Verify with tests covering every spelling in the config-cli "Command-line VALUE parsing" and "Printing scalars" requirements, including `2001-01-01`, `1_000`, `yes` → strings and `.inf` → `inf`
- [x] 2.2 Implement `paths.py` (parse, format, empty-segment error). Verify with tests for `tools.1`, `a..b` → UsageError, and `a.` → UsageError
- [x] 2.3 Implement `values.py` (one flow node: scalars, quoted escapes, `{}`/`[]`, multi-line strings; malformed or multi-node → UsageError). Verify with tests for every config-cli VALUE scenario

## 3. Loading and includes

- [x] 3.1 Implement `source.py` (read with `newline=''`, newline-style detection, offset ↔ line/column helpers). Verify with tests on LF, CRLF and non-ASCII text that ruamel marks index the right characters
- [x] 3.2 Implement `tree.py` and `loader.py`: config-file discovery (neither or both → exit 4), compose → tree with spans, styles, flow context and owning file; resolution via `schema.py`; an empty file → empty mapping; anchors and unknown tags → exit 4. Verify with tests for each config-loading scenario on locating and parsing
- [x] 3.3 Add include resolution (YAML embedding, text includes with exact bytes, relative paths, recursion, missing target and cycle → exit 4, the same file twice allowed). Verify with tests for every config-loading "Includes" scenario using real nested directories
- [x] 3.4 Implement `leaves.py` (ordered leaf flattening of trees and plain values). Verify with tests for nested lists, text includes and empty collections (no leaves)

## 4. Event store and history

- [x] 4.1 Implement `store.py` (Application with SQLite at `.troupe/events.sqlite` through the constructor `env`, a `TheatreConfig` aggregate with a fixed id, `Imported`/`LeafSet`/`LeafRemoved` events, atomic save, a list of events with seq). Verify with tests that events persist across separate Application instances, and that the process `os.environ` is unchanged
- [x] 4.2 Wire the command flow (D11): parse → load → import-once → command, with no state created on exit 2 or 4. Implement `history [PATH]` (JSON Lines, prefix filter, non-finite floats as strings). Verify with tests for every config-history "Import on first command" and "Listing history" scenario and the config-cli "State confined" scenarios (snapshot the directory tree before and after)

## 5. show

- [x] 5.1 Implement `show PATH` (scalar printing, text include as string, exit 5 for mappings, lists, missing keys, out-of-range indexes and descent into a scalar, each with the path in stderr). Verify with tests for every config-show scenario, including a hand edit after import

## 6. set: planning and simple scalars

- [x] 6.1 Implement path resolution for `set` in `edit/plan.py`: existing node, new key (deepest existing ancestor mapping, intermediates), append (index == len) and the exit-5 cases (scalar or null parent, digit intermediate, index > len, text-include parent). Verify with tests for those config-set scenarios that assert exit codes and that the files are unchanged
- [x] 6.2 Implement `edit/scalars.py` (style choice and fallback, plain representability via `schema.py`, single and double quoting, minimal double-quote escaping). Verify with unit tests per style and a byte-exact test for each config-set "Scalar quoting" and "Double-quoted escaping" scenario
- [x] 6.3 Implement `edit/apply.py` (splice edits, verify by re-loading the edited texts, write only changed files) and `edit/layout.py` comment realignment. Wire `set` for an existing scalar, the no-op case, and set events with old values from the files. Verify with byte-exact tests for "Byte-surgical write-back", "End-of-line comment alignment" and the "Events recorded by set" scenarios, including a no-op set (unchanged mtime, no events)
- [x] 6.4 Implement text-include writes (exact VALUE, CRLF conversion, a non-string → exit 3) and the include refusals (a YAML include root targeted directly, or changed or deleted through an ancestor → exit 3; a `file:` VALUE whose configuration does not load → exit 3). Verify with tests for every config-set "Target file", "Refusing to replace an include" and "Values that are includes" scenario

## 7. set: structure and layout

- [x] 7.1 Implement indentation-unit and sequence-offset detection, and the insertion point after trailing comments (`edit/layout.py`). Verify with unit tests on real sample files, including a comment indented less than the entries and trailing blank lines
- [x] 7.2 Implement `edit/blocks.py` block-collection emission (new keys, intermediates, list appends, a scalar replaced by a block collection with and without a comment, CRLF files, files without a final newline). Verify with byte-exact tests for "Creating new keys", "Appending to lists", "New collection values", "Placement of new entries" and "Scalar replaced by a block collection"
- [x] 7.3 Implement flow-collection edits (append on the last entry's line, an empty `{}`/`[]`, a flow-style new collection, a double-quoted multi-line value in a flow parent) with comment realignment. Verify with byte-exact tests for the flow scenarios
- [x] 7.4 Implement diff semantics (D5): recursive mapping and list diffs, block and flow entry deletion, collection → scalar replacement, and remove events in old document order before set events. Verify with byte-exact tests for "Setting a collection value" and the "Scalar replaced by a mapping" and "Unchanged leaves are not recorded" history scenarios

## 8. set: block scalars

- [x] 8.1 Implement literal-block emission and block-scalar replacement (header parsing, kept indentation, `required_chomping`, kept chomping when it can represent the value, an indentation indicator for a leading space, a double-quoted fallback). Verify with byte-exact tests for each "Multi-line strings and block scalars" scenario, plus a CRLF block scalar
- [x] 8.2 Implement `edit/folded.py` (paragraph alignment, kept bytes for unchanged paragraphs, greedy re-wrap at the paired or global width, long words, separator blank lines, more-indented → exit 3). Verify with byte-exact tests for each "Folded block scalars" scenario, plus a paragraph insertion and a paragraph deletion

## 9. Integration and documentation

- [x] 9.1 Add a subprocess smoke suite that runs `uv run troupe config show|set|history` from the repository root against a realistic multi-file theatre (includes, comments, CRLF text include). Verify exit codes, stdout and file bytes
- [x] 9.2 Write `README.md` (installation, the three commands, exit codes, the open-question decisions from design.md) and verify each documented example command runs as written
- [x] 9.3 Run `uv run pytest`, `uv run mypy --strict src tests` and `uv run ruff check`. Verify all three are clean and record the output in the final summary
