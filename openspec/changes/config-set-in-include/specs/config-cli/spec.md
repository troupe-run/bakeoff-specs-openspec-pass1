# Spec Delta

## MODIFIED Requirements

### Requirement: Invocation and theatre selection
The CLI SHALL be invocable as `uv run troupe config <subcommand> [--theatre <dir>] [arguments]` from the repository
root, with subcommands `get PATH`, `show [PATH] [--sources]`, `set PATH VALUE [--reason TEXT] [--in-include]`, `history [PATH]` and
`watch`. `--theatre` SHALL default to the current working directory.

#### Scenario: Explicit theatre
- **WHEN** `uv run troupe config get model --theatre /tmp/t` is run and `/tmp/t/.troupe/troupe.yml` contains `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Default theatre is the current directory
- **WHEN** `troupe config get model` is run with the current directory set to a theatre whose config has `model: x`
- **THEN** stdout is `x\n` and the exit code is 0

#### Scenario: Unknown subcommand or missing argument
- **WHEN** `troupe config frobnicate`, `troupe config get` (no PATH), `troupe config set model` (no VALUE), `troupe config set model b --reason` (no TEXT) or `troupe config set model b --in-include x` (an extra argument) is run
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
