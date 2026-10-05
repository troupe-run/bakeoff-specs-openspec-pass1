# Spec Delta

## ADDED Requirements

### Requirement: Mapping-form includes and overrides
A mapping that has a `$ref` key whose value is an include string (as defined in "Includes") SHALL be an include in
**mapping form**. The include target SHALL be resolved as for a scalar-form include, relative to the directory of the
file containing the mapping. The mapping's other keys are **overrides**. The value of a mapping-form include SHALL be
the included content deep-merged with the overrides:
- where both the included value and the override value at a key are mappings, they SHALL be merged recursively by
  the same rule;
- otherwise (a scalar or list on either side) the override value SHALL replace the included value;
- a key that only the override has SHALL be added.

Override values SHALL be loaded like any other value of the file that holds them, so an include string inside an
override is resolved relative to that file, and includes inside the included content are resolved relative to the
included file. In the merged mapping, the included content's keys SHALL keep their order (an overridden key keeps its
position) and keys only the overrides have SHALL follow, in the order they are written. The `$ref` key itself SHALL NOT
appear in the value. A mapping-form include with no other keys SHALL load exactly like the scalar-form include of the
same string, including for text includes. A `$ref` key whose value is not an include string (not a string, or not
starting with `file:`) SHALL be an ordinary key.

Loading SHALL fail with exit 4, with a message naming the file that holds the `$ref` mapping and the target, when a
mapping-form include has overrides and its target is not a YAML file (a text include), or its included content is not
a mapping (a list, a scalar, or an empty file).

#### Scenario: Overrides deep-merge with the included content
- **WHEN** `agents/coder.yaml` is `model: m1\ntemperature: 0.2\nlimits:\n  tokens: 100\n  calls: 5\ntools: [read, write]\n` and `troupe.yml` is `agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    temperature: 0.3\n    limits:\n      calls: 9\n    tools: [read]\n    extra: x\n`, and `show agents.coder` runs
- **THEN** stdout is `model: m1\ntemperature: 0.3\nlimits:\n  tokens: 100\n  calls: 9\ntools:\n  - read\nextra: x\n`

#### Scenario: Override replaces a mapping with a scalar
- **WHEN** the included content has `limits: {tokens: 100}` and the override has `limits: none`
- **THEN** `get agents.coder.limits` prints `none\n`

#### Scenario: Mapping form without overrides
- **WHEN** `troupe.yml` is `agents:\n  coder:\n    $ref: file:agents/coder.yaml\n` and `agents/coder.yaml` is `model: m1\n`
- **THEN** `show agents` prints `coder:\n  model: m1\n`, the same as for `agents:\n  coder: file:agents/coder.yaml\n`

#### Scenario: Text include in mapping form
- **WHEN** `troupe.yml` is `prompt:\n  $ref: file:prompt.md\n` and `prompt.md` contains `Hello\n`
- **THEN** `get prompt` prints `Hello\n` and `show --sources` prints `prompt: | # from .troupe/prompt.md\n  Hello\n`

#### Scenario: Text include with overrides
- **WHEN** `troupe.yml` is `prompt:\n  $ref: file:prompt.md\n  extra: 1\n`
- **THEN** every subcommand exits 4 and stderr names `troupe.yml` and `prompt.md`

#### Scenario: Overrides on content that is not a mapping
- **WHEN** `tools.yaml` is `[a, b]\n` (or `5\n`, or empty) and `troupe.yml` is `tools:\n  $ref: file:tools.yaml\n  extra: 1\n`
- **THEN** every subcommand exits 4 and stderr names `troupe.yml` and `tools.yaml`

#### Scenario: Include inside an override resolves against the including file
- **WHEN** `.troupe/troupe.yml` has `coder:\n  $ref: file:agents/coder.yaml\n  prompt: file:prompt.md\n` and both `.troupe/prompt.md` and `.troupe/agents/prompt.md` exist
- **THEN** `coder.prompt` is the text of `.troupe/prompt.md`

#### Scenario: Mapping-form include inside an included file
- **WHEN** `agents/coder.yaml` has `limits:\n  $ref: file:limits.yaml\n  calls: 9\n` and `agents/limits.yaml` has `calls: 5\ntokens: 1\n`
- **THEN** `show agents.coder.limits` (with `agents.coder` included from `agents/coder.yaml`) prints `calls: 9\ntokens: 1\n`

#### Scenario: $ref that is not an include string
- **WHEN** the config is `a:\n  $ref: hello\n  b: 1\n`
- **THEN** `show a` prints `$ref: hello\nb: 1\n`

#### Scenario: Missing target in mapping form
- **WHEN** a mapping-form include names a file that does not exist
- **THEN** every subcommand exits 4 and stderr names the missing target
