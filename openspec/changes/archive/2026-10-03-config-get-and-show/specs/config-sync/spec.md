# Spec Delta

## MODIFIED Requirements

### Requirement: Commands reconcile first
`get`, `show`, `set` and `watch` SHALL reconcile after the configuration loads (and, on a theatre's first command,
after the import) and before doing their own work, so they pick up edits made while nothing was running. The
reconcile's events SHALL persist even if the command then exits 3 or 5. `history` SHALL never reconcile: it reports
only what has been recorded. Nothing SHALL be reconciled when the command line is invalid (exit 2) or the
configuration cannot be loaded (exit 4).

#### Scenario: set after a hand edit
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `set a 3` runs
- **THEN** two events are added, in this order: `set a` (old 1, new 2), then `set a` (old 2, new 3)

#### Scenario: get and show reconcile
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `get a` runs (or, separately, `show` runs)
- **THEN** `history` lists `set a` (old 1, new 2) exactly once

#### Scenario: Reconcile persists when the command fails
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `show nope` (or `get nope`) runs and exits 5
- **THEN** a later `history` includes `set a` (old 1, new 2)

#### Scenario: history does not reconcile
- **WHEN** the theatre was imported with `a: 1\n`, the file is edited by hand to `a: 2\n`, and `history` runs
- **THEN** no event mentions the value 2. After `show a` runs, `history` lists `set a` (old 1, new 2)

#### Scenario: Invalid command line or unloadable configuration records nothing
- **WHEN** the file was edited by hand after import, and then `set a "[x"` (exit 2) runs, or the file is made invalid YAML and `show a` (exit 4) runs
- **THEN** no event is added
