# config-cli Specification

## Purpose

Defines how the `troupe config` command line is invoked, how paths and command-line values are interpreted, how
scalars are printed, and how failures are reported through exit codes and messages.

## Requirements

### Requirement: Invocation and theatre selection
The CLI SHALL be invocable as `uv run troupe config <subcommand> [--theatre <dir>] [arguments]` from the repository
root, with subcommands `show`, `set` and `history`. `--theatre` SHALL default to the current working directory.

#### Scenario: Explicit theatre
- **WHEN** `uv run troupe config show model --theatre /tmp/t` is run and `/tmp/t/.troupe/troupe.yml` contains `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Default theatre is the current directory
- **WHEN** `troupe config show model` is run with the current directory set to a theatre whose config has `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Unknown subcommand or missing argument
- **WHEN** `troupe config frobnicate` or `troupe config set model` (no VALUE) is run
- **THEN** the exit code is 2, stdout is empty and stderr has a usage message

### Requirement: Path syntax
A `PATH` SHALL be a sequence of keys separated by `.`. A segment of only ASCII digits SHALL index a list (0-based)
when the node it applies to is a list. A `PATH` that is empty or has an empty segment (such as `a..b` or `a.`) SHALL be
a usage error (exit 2). Keys containing `.` and mappings with digit-only keys are out of contract.

#### Scenario: List indexing
- **WHEN** the config is `tools: [a, b]` and `show tools.1` is run
- **THEN** stdout is `b\n`

#### Scenario: Empty segment
- **WHEN** `show a..b` is run
- **THEN** the exit code is 2 and stderr names `a..b`

### Requirement: Command-line VALUE parsing
`VALUE` SHALL be parsed as one YAML 1.2 core-schema flow node. Plain scalars resolve as follows: `null`, `Null`,
`NULL`, `~` and the empty string to null; `true`/`True`/`TRUE`/`false`/`False`/`FALSE` to booleans; decimal, `0o` octal
and `0x` hex integers to integers; core-schema floats (including `.inf`, `-.inf` and `.nan` in their spellings) to
floats; everything else to strings. Quoted scalars SHALL be strings, with double-quoted escapes such as `\n`
interpreted. `{…}` and `[…]` SHALL be a mapping and a list. A `VALUE` that is not a single valid flow node (for
example `[a, b` or `a: b: c`) SHALL be a usage error (exit 2).

#### Scenario: Scalar types
- **WHEN** VALUE is `0.2`, `true`, `null`, `abc`, `"0.2"` or `2001-01-01`
- **THEN** it is the float 0.2, the boolean true, null, the string `abc`, the string `0.2` and the string `2001-01-01` respectively

#### Scenario: Collections
- **WHEN** VALUE is `{a: 1}` or `[a, b]`
- **THEN** it is the mapping `{"a": 1}` or the list `["a", "b"]`

#### Scenario: Multi-line string
- **WHEN** VALUE is `"line one\nline two\n"`
- **THEN** it is the string `line one⏎line two⏎`

#### Scenario: Malformed value
- **WHEN** `set model "[a, b"` is run
- **THEN** the exit code is 2, no file changes, and stderr names the value

### Requirement: Printing scalars
A string SHALL be printed exactly, followed by `\n` unless it already ends with `\n`. Booleans SHALL print as
`true`/`false`, null as `null`, integers in decimal, and floats as Python's `repr()`.

#### Scenario: Each scalar type
- **WHEN** the values shown are the string `hi`, the string `hi⏎`, `true`, `~`, `0x1F` and `0.2`
- **THEN** the outputs are `hi\n`, `hi\n`, `true\n`, `null\n`, `31\n` and `0.2\n`

#### Scenario: Special floats
- **WHEN** the value shown is `.inf`
- **THEN** the output is `inf\n`

### Requirement: Exit codes and error reporting
The CLI SHALL exit with `0` on success, `2` on a usage error, `3` when a write is refused (no file changed), `4` when
the configuration cannot be loaded, and `5` when the path is not found or is the wrong kind of node for the command.
On any non-zero exit, stdout SHALL be empty and stderr SHALL contain a message naming the offending path or file.

#### Scenario: Error message names the path
- **WHEN** `show agents.nobody` is run and there is no such path
- **THEN** the exit code is 5, stdout is empty, and stderr contains `agents.nobody`

### Requirement: State confined to `.troupe/`
The implementation SHALL keep its own state only under `<theatre>/.troupe/`. It SHALL NOT create or modify any other
file except as `set`'s write-back rules require, and SHALL NOT create any state when the configuration cannot be
loaded.

#### Scenario: show leaves user files untouched
- **WHEN** `show` and `history` run against a theatre
- **THEN** every file outside `.troupe/` and every configuration file inside it is byte-identical to before, and new files appear only under `.troupe/`

#### Scenario: Unloadable theatre creates no state
- **WHEN** any subcommand runs against a directory with no `.troupe/troupe.yml` or `.yaml`
- **THEN** the exit code is 4 and no file or directory is created
