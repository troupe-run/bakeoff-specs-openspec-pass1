# Proposal

## Why

People edit `.troupe/` files by hand in their editor, often while troupe is running. Step 1 deliberately left those
edits out of the event record ("importing is not reconciling"), so `history` misses every hand edit and the
recorded configuration drifts away from the files. Step 2 keeps the record and the files in sync: edits are picked up
as they happen while `watch` runs, and any edits made while nothing was running are picked up by the next command.
troupe's own write-backs must not be picked up a second time.

## What Changes

- **Reconcile**: compare the files, as loaded now, with the recorded configuration (the event projection). Emit one
  `remove` event for each recorded leaf that is gone and one `set` event for each leaf that is new or has a different
  value. A formatting-only or comment-only edit changes no leaf, so it emits nothing.
- New subcommand `troupe config watch [--theatre DIR]`. It runs in the foreground, prints `watching <dir>` (flushed)
  once it can observe changes, reconciles within 2 seconds of any change to the config file or an included file,
  follows includes that hand edits add, and exits 0 on SIGINT or SIGTERM.
- `show`, `set` and `watch` reconcile before doing their own work. `history` never reconciles. It still imports on
  first use, as in step 1. **BREAKING** (behaviour, not interface): a hand edit now produces `set`/`remove` events,
  and a `set` after a hand edit records the reconcile events first, then its own.
- Commands against the same theatre are serialised, so a `set` running while `watch` runs records exactly its own
  events, and its write-back produces no further events.

## Capabilities

### New Capabilities
- `config-sync`: reconciling the files with the recorded configuration, the rule that commands reconcile first (except
  `history`), the `watch` command, and how troupe's own write-backs are kept from being reconciled again.

### Modified Capabilities
- `config-cli`: `watch` joins the subcommands. The rule that commands leave user files untouched now covers `watch`.
- `config-history`: hand edits are no longer ignored. "Import on first command" is replaced by "Import on a
  theatre's first command": the import rules are the same, minus "later hand edits SHALL NOT generate events". The
  `set` event scenario that started from a hand edit now expects the reconcile event before the `set` event.

## Impact

- Code: a new reconcile step (sharing the leaf diff that `set` already uses), a per-theatre lock taken around every
  command's read-modify-write, a `watch` loop with signal handling in `commands.py`/`cli.py`, and `watch` added to the
  argument parser.
- No new runtime dependencies: changes are detected by polling file contents (see design.md).
- State: still only `<theatre>/.troupe/events.sqlite`. The lock is taken on the `.troupe/` directory itself, so no
  new file is created.
- Tests: new reconcile and watch tests, including subprocess tests that run the real `watch` and send it signals.
  The step-1 test `test_hand_edits_are_not_reconciled` is replaced. README updated.
