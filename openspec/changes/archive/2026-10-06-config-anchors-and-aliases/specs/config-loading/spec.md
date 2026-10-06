# Spec Delta

## ADDED Requirements

### Requirement: Anchors, aliases and merge keys
A node in a configuration file MAY carry an anchor (`&name`). An alias (`*name`) SHALL have the value of the node
most recently anchored with that name earlier in the same file. Anchors and aliases do not cross files, so an
alias in one file never refers to an anchor in a file it includes or that includes it. An anchored node that is or
contains an include SHALL be resolved as usual, and every alias to it SHALL have the same resolved value.

A plain (unquoted, untagged) key `<<` SHALL be a **merge key**. Its value SHALL be a mapping (written there or
through an alias), or a list of such mappings. The mapping that holds the merge key SHALL have every entry of the
merged mappings that it does not set itself. Where more than one merged mapping has a key, the first one in the
list SHALL win. Merged entries SHALL take the merge key's position, in the order of the merged mappings, and the
mapping's own keys SHALL keep their positions. The `<<` key itself SHALL NOT appear in the value. A quoted `"<<"`
is an ordinary key.

`get`, `show`, `show --sources`, `history`, import and reconciling SHALL all use these resolved values. A value
reached through an alias or a merge key SHALL be reported as coming from the file in which its anchored node is
written.

Loading SHALL fail with exit 4, with a message naming the file, for an alias with no earlier anchor of its name,
an alias inside the node it refers to, an anchor or alias used as a mapping key, or a merge key whose value is not
a mapping or a list of mappings as written in that file (an include string is not one).

#### Scenario: Alias of an anchored mapping
- **WHEN** the config is `defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n`
- **THEN** `get coder.settings.model` and `get reviewer.settings.model` print `opus\n`, and `show coder` prints `settings:\n  model: opus\n`

#### Scenario: Alias of an anchored scalar
- **WHEN** the config is `a: &x 1\nb: *x\n`
- **THEN** `get b` prints `1\n`

#### Scenario: Merge key
- **WHEN** the config is `base: &b\n  model: opus\n  temperature: 0.2\ncoder:\n  <<: *b\n  temperature: 0.5\n  top_p: 1\n`
- **THEN** `show coder` prints `model: opus\ntemperature: 0.5\ntop_p: 1\n`

#### Scenario: Merge key with a list of mappings
- **WHEN** the config is `a: &a {x: 1, y: 1}\nb: &b {y: 2, z: 2}\nc:\n  <<: [*a, *b]\n`
- **THEN** `show c` prints `x: 1\ny: 1\nz: 2\n`

#### Scenario: Quoted merge key is an ordinary key
- **WHEN** the config is `a: &a {x: 1}\nc:\n  "<<": *a\n`
- **THEN** `get c.<<.x` prints `1\n`

#### Scenario: Import records aliased values at every path
- **WHEN** the first command runs against `defaults: &d\n  model: opus\ncoder:\n  settings: *d\n`
- **THEN** `history` lists import events for `defaults.model` and `coder.settings.model`, both `opus`

#### Scenario: Undefined alias
- **WHEN** the config is `a: *nothing\n`
- **THEN** every subcommand exits 4 and stderr names the config file

#### Scenario: Anchors do not cross files
- **WHEN** `troupe.yml` is `shared: file:shared.yaml\ncoder: *d\n` and `shared.yaml` is `&d {model: opus}\n`
- **THEN** every subcommand exits 4 and stderr names `troupe.yml`

#### Scenario: Alias inside its own anchor
- **WHEN** the config is `a: &a\n  b: *a\n`
- **THEN** every subcommand exits 4 and stderr names the config file

#### Scenario: Merge key with a scalar value
- **WHEN** the config is `c:\n  <<: 1\n`
- **THEN** every subcommand exits 4 and stderr names the config file
