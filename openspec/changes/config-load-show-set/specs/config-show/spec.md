# Spec Delta

## Purpose

Lets a user read a single setting from a theatre's configuration, following includes, printed in a stable textual
form.

## ADDED Requirements

### Requirement: Show a scalar value
`troupe config show PATH` SHALL print the value at `PATH` using the scalar printing rules when that value is a
scalar. A text include SHALL count as a string scalar. The value SHALL reflect the current contents of the
configuration files, including edits made by hand since the last command.

#### Scenario: Plain scalar
- **WHEN** the config is `model: claude-opus-5-5\n` and `show model` is run
- **THEN** stdout is `claude-opus-5-5\n` and the exit code is 0

#### Scenario: Value through a YAML include
- **WHEN** `agents.coder` is `file:agents/coder.yaml`, which contains `temperature: 0.2`
- **THEN** `show agents.coder.temperature` prints `0.2\n`

#### Scenario: Hand edit is visible
- **WHEN** a command has already run, the user then edits `model: a` to `model: b` by hand, and `show model` runs
- **THEN** stdout is `b\n`

### Requirement: Show refuses collections and missing paths
`show` SHALL exit 5, naming the path, when the value at `PATH` is a mapping or list, when `PATH` does not exist, when
an index is out of range, or when a segment would have to descend into a scalar.

#### Scenario: Mapping
- **WHEN** `agents` is a mapping and `show agents` is run
- **THEN** the exit code is 5, stdout is empty, and stderr names `agents`

#### Scenario: Missing key
- **WHEN** `show nope` is run and there is no `nope` key
- **THEN** the exit code is 5 and stderr names `nope`

#### Scenario: Descending into a scalar
- **WHEN** `model` is a string and `show model.x` is run
- **THEN** the exit code is 5 and stderr names `model.x`
