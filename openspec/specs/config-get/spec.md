# config-get Specification

## Purpose

Lets a user or a script read one scalar setting from a theatre's configuration, following includes, printed in a
stable textual form. Anything larger is read with `show`.

## Requirements

### Requirement: Get a scalar value
`troupe config get PATH` SHALL print the value at `PATH` using the scalar printing rules when that value is a scalar.
A text include SHALL count as a string scalar. The value SHALL reflect the current contents of the configuration
files, including edits made by hand since the last command.

#### Scenario: Plain scalar
- **WHEN** the config is `model: claude-opus-5-5\n` and `get model` is run
- **THEN** stdout is `claude-opus-5-5\n` and the exit code is 0

#### Scenario: Value through a YAML include
- **WHEN** `agents.coder` is `file:agents/coder.yaml`, which contains `temperature: 0.2`
- **THEN** `get agents.coder.temperature` prints `0.2\n`

#### Scenario: Text include
- **WHEN** `p` is `file:p.txt` and `p.txt` contains `no newline` (no line break)
- **THEN** `get p` prints `no newline\n`

#### Scenario: Hand edit is visible
- **WHEN** a command has already run, the user then edits `model: a` to `model: b` by hand, and `get model` runs
- **THEN** stdout is `b\n`

### Requirement: Get refuses collections and missing paths
`get` SHALL exit 5 when the value at `PATH` is a mapping or list, when `PATH` does not exist, when an index is out of
range, or when a segment would have to descend into a scalar. Stderr SHALL name the path. When the value is a mapping
or list, stderr SHALL also mention `config show`, the command that prints it.

#### Scenario: Mapping
- **WHEN** `agents` is a mapping and `get agents` is run
- **THEN** the exit code is 5, stdout is empty, and stderr contains both `agents` and `config show`

#### Scenario: List
- **WHEN** `tools` is a list and `get tools` is run
- **THEN** the exit code is 5, stdout is empty, and stderr contains both `tools` and `config show`

#### Scenario: Missing key
- **WHEN** `get nope` is run and there is no `nope` key
- **THEN** the exit code is 5, stdout is empty, and stderr names `nope`

#### Scenario: Descending into a scalar
- **WHEN** `model` is a string and `get model.x` is run
- **THEN** the exit code is 5 and stderr names `model.x`
