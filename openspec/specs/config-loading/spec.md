# config-loading Specification

## Purpose

Defines how a theatre's configuration is located, parsed as YAML 1.2, and assembled from `file:` includes into one
configuration tree in which every value knows the file it came from.

## Requirements

### Requirement: Locating the configuration file
The configuration SHALL be read from `<theatre>/.troupe/troupe.yml` or `<theatre>/.troupe/troupe.yaml`. If neither
exists, or both exist, loading SHALL fail with exit 4 and a message naming the file(s).

#### Scenario: Either extension works
- **WHEN** only `.troupe/troupe.yaml` exists
- **THEN** it is loaded

#### Scenario: Both present
- **WHEN** both `.troupe/troupe.yml` and `.troupe/troupe.yaml` exist
- **THEN** every subcommand exits 4 and stderr names both files

#### Scenario: Neither present
- **WHEN** `.troupe/` has neither file
- **THEN** every subcommand exits 4 and stderr names `troupe.yml`

### Requirement: YAML 1.2 core-schema parsing
Configuration files SHALL be parsed as YAML 1.2 using the core schema, with plain scalars resolved as in
`VALUE` parsing (so `yes`, `on` and `2001-01-01` are strings and `1_000` is a string). Any byte sequence that is not
valid UTF-8, or text that is not valid YAML, SHALL fail with exit 4, naming the file. An empty (or comment-only) file
SHALL load as an empty mapping.

#### Scenario: Core schema, not YAML 1.1
- **WHEN** the config is `a: yes\nb: 2001-01-01\nc: 0o17\n`
- **THEN** `show a` prints `yes`, `show b` prints `2001-01-01`, and `show c` prints `15`

#### Scenario: Syntax error
- **WHEN** the config is `a: [1, 2\n`
- **THEN** every subcommand exits 4 and stderr names the config file

#### Scenario: Empty file
- **WHEN** the config file is empty
- **THEN** `history` exits 0 with no output, and `show a` exits 5

### Requirement: Includes
A string scalar (in any quoting style) whose value starts with `file:` SHALL be an include of the path after
`file:`, resolved relative to the directory of the file that contains the string. If the target's name ends in `.yml`
or `.yaml`, its parsed content SHALL take the place of the string, as if written there. Any other target SHALL make the
value a string equal to the target file's exact text, with line endings unchanged. Includes SHALL be followed
recursively. A missing (or unreadable) target, or a cycle of includes, SHALL fail with exit 4 and a message naming the
target.

#### Scenario: YAML include
- **WHEN** `troupe.yml` has `agents:\n  coder: file:agents/coder.yaml\n` and `.troupe/agents/coder.yaml` has `model: m1\n`
- **THEN** `show agents.coder.model` prints `m1`

#### Scenario: Text include
- **WHEN** `troupe.yml` has `prompt: file:prompt.md` and `.troupe/prompt.md` contains `Hello\nWorld\n`
- **THEN** `show prompt` prints `Hello\nWorld\n` exactly

#### Scenario: Nested include is relative to its own file
- **WHEN** `.troupe/agents/coder.yaml` contains `prompt: file:coder.md` and `.troupe/agents/coder.md` exists
- **THEN** the prompt resolves to `.troupe/agents/coder.md`

#### Scenario: Missing target
- **WHEN** an include names a file that does not exist
- **THEN** every subcommand exits 4 and stderr names the missing target

#### Scenario: Cycle
- **WHEN** `a.yaml` includes `b.yaml` and `b.yaml` includes `a.yaml`
- **THEN** every subcommand exits 4 and stderr names a file in the cycle

#### Scenario: The same file included twice is not a cycle
- **WHEN** two sibling keys both include `common.yaml`
- **THEN** loading succeeds and both keys hold its content
