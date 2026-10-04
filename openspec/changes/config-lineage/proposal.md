# Proposal

## Why

Configuration in troupe is changed by people and by AI agents, but `history` only says *what* changed. To audit a
setting we must also know who changed it (a human or an agent, and which one), how (the CLI, a hand edit, or the
first import), when, why, and what else changed in the same step. Where the answer is not known, as for a hand
edit in a text editor, the history must say so instead of guessing. Step 4 adds this lineage to every event.

## What Changes

- Every `history` event gains five fields, stored with the event so they survive restarts:
  - `actor`: `{"kind": "human" | "agent" | "unknown", "id": <string or null>}`
  - `via`: `"import"`, `"cli"` or `"file"`
  - `at`: an RFC 3339 UTC timestamp ending in `Z`
  - `reason`: the text given with `set --reason TEXT`, else `null`
  - `change`: an id shared by every event one command (or one file reconcile, or the import) produces, and by
    no other event
- The actor of a CLI command comes from the `TROUPE_ACTOR` environment variable, `human:<id>` or `agent:<id>`.
  Any other value is a usage error (exit 2). When it is unset, the actor is `{"kind": "human", "id": <login name>}`.
- Imports and reconciled hand edits (by any command, including `watch`) have actor `{"kind": "unknown", "id": null}`,
  with `via` `"import"` and `"file"` respectively. A `set`'s own events have `via` `"cli"` and the command's actor.
- `troupe config set PATH VALUE` takes an optional `--reason TEXT`, recorded on that `set`'s own events.
- Event stores written before step 4 still load. Their events are read with lineage that says what is not known
  (design D7). Nothing in them is rewritten.

No existing field changes meaning, and no existing output changes except that each history line has more keys.

## Capabilities

### New Capabilities
- `config-lineage`: who, how, when, why and with what else each recorded event happened: the five fields, where
  their values come from (`TROUPE_ACTOR`, login name, import, reconcile, `set --reason`), how change ids group
  events, and that lineage persists.

### Modified Capabilities
- `config-history`: "Listing history" requires each event object to carry the lineage fields as well.
- `config-cli`: the invocation requirement lists `set PATH VALUE [--reason TEXT]`. (The `TROUPE_ACTOR` rules, including
  exit 2 for an invalid value, are in `config-lineage`.)

## Impact

- Code:
  - New module `lineage.py`: the actor parsing, the login-name fallback, the clock and change-id generation, and the
    `Lineage` value. Each of these decisions lives there and nowhere else.
  - `store.py`: leaf events carry lineage; event classes move to version 2 with an upcaster for older stored
    events. `import_leaves` and `record` take a `Lineage`; `Record` exposes it.
  - `sync.py`, `commands.py`: the import, each reconcile and each `set` build their own `Lineage`. `history`
    prints the new fields.
  - `cli.py`: `--reason` on `set`; `TROUPE_ACTOR` is read and checked for every subcommand.
- Tests: new lineage tests (actor kinds, login fallback, invalid values, via, timestamps, reasons, change grouping,
  persistence, pre-step-4 stores). The existing history, store, reconcile and watch tests keep passing; the ones
  that call `ConfigStore` directly pass a `Lineage`. README updated.
- No new dependencies. Configuration files and write-back are unchanged.
