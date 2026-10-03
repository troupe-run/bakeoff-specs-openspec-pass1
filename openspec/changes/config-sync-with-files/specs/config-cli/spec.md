# Spec Delta

## MODIFIED Requirements

### Requirement: Invocation and theatre selection
The CLI SHALL be invocable as `uv run troupe config <subcommand> [--theatre <dir>] [arguments]` from the repository
root, with subcommands `show`, `set`, `history` and `watch`. `--theatre` SHALL default to the current working
directory.

#### Scenario: Explicit theatre
- **WHEN** `uv run troupe config show model --theatre /tmp/t` is run and `/tmp/t/.troupe/troupe.yml` contains `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Default theatre is the current directory
- **WHEN** `troupe config show model` is run with the current directory set to a theatre whose config has `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Unknown subcommand or missing argument
- **WHEN** `troupe config frobnicate` or `troupe config set model` (no VALUE) is run
- **THEN** the exit code is 2, stdout is empty and stderr has a usage message

#### Scenario: watch takes no positional argument
- **WHEN** `troupe config watch extra` is run
- **THEN** the exit code is 2, stdout is empty and stderr has a usage message

### Requirement: State confined to `.troupe/`
The implementation SHALL keep its own state only under `<theatre>/.troupe/`. It SHALL NOT create or modify any other
file except as `set`'s write-back rules require, and SHALL NOT create any state when the configuration cannot be
loaded.

#### Scenario: show leaves user files untouched
- **WHEN** `show`, `history` and `watch` run against a theatre, including while files are edited by hand during `watch`
- **THEN** no configuration file is created or modified by troupe, and new files appear only under `.troupe/`

#### Scenario: Unloadable theatre creates no state
- **WHEN** any subcommand runs against a directory with no `.troupe/troupe.yml` or `.yaml`
- **THEN** the exit code is 4 and no file or directory is created
