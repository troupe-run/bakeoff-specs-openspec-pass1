# Tasks

## 1. Reconcile

- [x] 1.1 Move `_changes` from `src/troupe/edit/apply.py` to `leaves.diff_leaves(old, new)` (leaf dicts in, `list[Change]` out) and make `compute_set` use it; verify the existing `tests/test_history.py` and `tests/test_set_*.py` still pass unchanged
- [x] 1.2 Add `src/troupe/sync.py` with `reconcile(config, store)` (D1): diff `store.projection()` against the loaded leaves and record the changes in one save; verify with unit tests in `tests/test_reconcile.py` that it records nothing when the files match and that removes come in recorded order, then sets in document order
- [x] 1.3 Add a test that projection values round-trip through `events.sqlite` with their exact types (`1`, `1.0`, `true`, `"1"`, null, `.inf`, `.nan`, multi-line text), so a reconcile right after import records nothing; verify it passes
- [x] 1.4 Add CLI-level tests in `tests/test_reconcile.py` for every scenario of the config-sync requirement "Reconcile": hand edit to set event, removed and added leaves, scalar replaced by mapping, type change, formatting/comment-only edit emits nothing, edit inside an included text file; verify they fail before 2.x wires reconcile into commands (expected) and pass after

## 2. Sessions, lock and reconcile-first commands

- [x] 2.1 Replace `commands.open_theatre` with the `theatre_session(theatre, command, store=None)` context manager (D2): `find_config` → `flock` on the `.troupe/` directory → load → import → reconcile; keep the set of reconciling commands in one named constant; verify `uv run pytest` passes
- [x] 2.2 Make `set` hold the session (and so the lock) through compute, file writes and event recording; verify with a test that, while the test process holds `flock` on `.troupe/`, a `set` subprocess blocks and completes only after release
- [x] 2.3 Wire `show` and `set` to reconcile first and `history` not to; verify the config-sync "Commands reconcile first" scenarios with tests (set after hand edit gives two events in order, reconcile persists when `show nope` exits 5, history does not reconcile but a later `show` does, exit 2 / exit 4 record nothing)
- [x] 2.4 Replace `test_hand_edits_are_not_reconciled` with `test_hand_edits_are_not_imported` and update `test_set_records_old_value_from_the_files` to expect the reconcile event followed by the set event (config-history delta); verify both pass
- [x] 2.5 Check that a theatre with no config file still creates nothing (lock taken only after `find_config`) and that invalid YAML creates no `events.sqlite`; verify the existing `test_cli.py` / `test_loading.py` state tests pass and add one for invalid YAML if missing
- [x] 2.6 Update README ("State" section and decisions list) to say hand edits are now recorded by reconciling, `history` never reconciles, and commands on one theatre are serialised; verify the README example still runs as written

## 3. The watch command

- [x] 3.1 Add the `watch` subparser (no positional arguments) and the `<dir>` display rule (D4) in `cli.py`; verify `troupe config watch extra` exits 2 with a usage message and empty stdout
- [x] 3.2 Implement `commands.watch` (D3–D6): signal handlers → initial session → baseline from `Config.files` texts plus config-file candidates → print and flush `watching <dir>` → poll every `POLL_INTERVAL` with the `SETTLE_POLLS` settle rule → reconcile under the session → new baseline; LoadError while watching reported once to stderr and retried every poll; verify with `uv run mypy` and `uv run ruff check`
- [x] 3.3 Add a subprocess helper in `tests/test_watch.py` (start `python -m troupe.cli config watch`, wait for the ready line with a timeout, poll `history` up to a 2 s deadline, stop with a signal) and tests for: ready line text and flush, live edit reconciled within 2 s, edit to an included file, save-by-rename, comment-only edit records nothing, SIGINT and SIGTERM each exit 0 with exact stdout and empty stderr; verify they pass
- [x] 3.4 Add tests for startup and failure handling: unloadable theatre at start exits 4 with no line and creates nothing; broken-then-fixed file reports once on stderr, keeps running and records only the final `set a`; verify they pass
- [x] 3.5 Add tests for write-backs: `set model b` while `watch` runs adds exactly its own event after waiting 2.5 s; same for a `set` into an included YAML file; a hand edit after that `set` records `old` equal to the set's new value (D8); verify they pass
- [x] 3.6 Add tests for includes added by hand: new YAML include recorded as `set` events within 2 s, then an edit to the newly included file recorded within 2 s; an include added while nothing runs is picked up by `show`; verify they pass
- [x] 3.7 Add a smoke test in `tests/test_smoke.py` that runs `uv run troupe config watch --theatre DIR`, waits for the line, makes a hand edit, sees the event within 2 s, sends SIGTERM and gets exit 0; verify it passes
- [x] 3.8 Document `watch` in README (commands table, what reconcile means, exit on SIGINT/SIGTERM, decisions from design.md); verify the documented commands run as written

## 4. Integration

- [ ] 4.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check` and `uv run ruff format --check`; verify all are clean and show the output
- [ ] 4.2 Run `openspec validate config-sync-with-files --strict`; verify it reports the change as valid
- [ ] 4.3 Commit the work on `main` in small steps with messages that say why (no push, no PR); verify `git status` is clean and `git log` shows the commits
