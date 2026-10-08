# Spec Delta

## MODIFIED Requirements

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

