# config-cli Specification

## Purpose

Defines how the `troupe config` command line is invoked, how paths and command-line values are interpreted, how
scalars are printed, and how failures are reported through exit codes and messages.

## Requirements

### Requirement: Invocation and theatre selection
The CLI SHALL be invocable as `uv run troupe config <subcommand> [--theatre <dir>] [arguments]` from the repository
root, with subcommands `get PATH`, `show [PATH] [--sources]`, `set PATH VALUE [--reason TEXT] [--in-include] [--expand-alias] [--include]`, `history [PATH]` and
`watch`. `--theatre` SHALL default to the current working directory.

#### Scenario: Explicit theatre
- **WHEN** `uv run troupe config get model --theatre /tmp/t` is run and `/tmp/t/.troupe/troupe.yml` contains `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Default theatre is the current directory
- **WHEN** `troupe config get model` is run with the current directory set to a theatre whose config has `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Unknown subcommand or missing argument
- **WHEN** `troupe config frobnicate`, `troupe config get` (no PATH), `troupe config set model` (no VALUE), `troupe config set model b --reason` (no TEXT), `troupe config set model b --in-include x` (an extra argument), `troupe config set model b --expand-alias x` (an extra argument) or `troupe config set model b --include x` (an extra argument) is run
- **THEN** the exit code is 2, stdout is empty and stderr has a usage message

#### Scenario: show takes an optional PATH
- **WHEN** `troupe config show` and `troupe config show --sources` are run against a theatre that loads
- **THEN** each exits 0 and prints the whole configuration

#### Scenario: set takes an optional reason
- **WHEN** `troupe config set model b --reason "why"` and `troupe config set --reason "why" model c` are run against a theatre that loads
- **THEN** each exits 0 and changes `model`

#### Scenario: watch takes no positional argument
- **WHEN** `troupe config watch extra` is run
- **THEN** the exit code is 2, stdout is empty and stderr has a usage message

#### Scenario: set takes an optional --in-include
- **WHEN** `troupe config set a.x 1 --in-include` and `troupe config set --in-include a.y 2 --reason why` are run against a theatre that loads, with `a` a mapping
- **THEN** each exits 0 and creates its key

#### Scenario: set takes an optional --expand-alias
- **WHEN** `troupe config set a.x 1 --expand-alias` and `troupe config set --expand-alias a.y 2 --reason why` are run against a theatre that loads, with `a` a mapping and no alias involved
- **THEN** each exits 0 and creates its key

#### Scenario: set takes an optional --include
- **WHEN** `troupe config set a.x 1 --include` and `troupe config set --include a.y 2 --reason why` are run against a theatre that loads, with `a` a mapping
- **THEN** each exits 0 and creates its key

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
The configuration cannot be loaded (exit 4) also when a remote include cannot be fetched, when the schema file is not
a usable schema, and when the configuration is not valid against the schema. A write is also refused (exit 3) when it
would change remote content, and when its result would not be valid against the schema.
On any non-zero exit, stdout SHALL be empty and stderr SHALL contain a message naming the offending path or file.

#### Scenario: Error message names the path
- **WHEN** `show agents.nobody` is run and there is no such path
- **THEN** the exit code is 5, stdout is empty, and stderr contains `agents.nobody`

#### Scenario: Error message names the URL
- **WHEN** `get a` is run and `troupe.yml` is `a: http://127.0.0.1:<a closed port>/a.yaml\n`
- **THEN** the exit code is 4, stdout is empty, and stderr contains `http://127.0.0.1:<a closed port>/a.yaml`

### Requirement: State confined to `.troupe/`
The implementation SHALL keep its own state only under `<theatre>/.troupe/`. It SHALL NOT create or modify any other
file except as `set`'s write-back rules require, and SHALL NOT create any state when the configuration cannot be
loaded.

#### Scenario: show leaves user files untouched
- **WHEN** `get`, `show`, `show --sources`, `history` and `watch` run against a theatre, including while files are edited by hand during `watch`
- **THEN** no configuration file is created or modified by troupe, and new files appear only under `.troupe/`

#### Scenario: Unloadable theatre creates no state
- **WHEN** any subcommand runs against a directory with no `.troupe/troupe.yml` or `.yaml`
- **THEN** the exit code is 4 and no file or directory is created
