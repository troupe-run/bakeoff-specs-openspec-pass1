# config-loading Specification

## Purpose

Defines how a theatre's configuration is located, parsed as YAML 1.2, and assembled from includes (local files and
URLs) into one configuration tree in which every value knows the file or URL it came from.

In the scenarios below, `<base>` is the URL of a directory served over HTTP (for example
`http://127.0.0.1:8123/team`).

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
A string scalar (in any quoting style) whose value starts with `file:`, `https://` or `http://` SHALL be an include,
unless it is a **literal**: a scalar tagged `!literal` (see "The `!literal` tag"), or a string that the schema marks
`format: uri` (see config-schema). Only these two make an include-looking string a literal.

A `file:` include names the path after `file:`, resolved relative to the directory of the file that contains the
string. A `file:` include inside remote content is resolved against the URL of that content, as a relative URL
reference (see "Remote includes"). An `https://` or `http://` include names that URL (see "Remote includes"). If the
target's name ends in `.yml` or `.yaml` (for a URL: its path, without query or fragment), its parsed content SHALL
take the place of the string, as if written there. Any other target SHALL make the value a string equal to the
target's exact text, with line endings unchanged. Includes SHALL be followed recursively. A missing (or unreadable)
target, or a cycle of includes, SHALL fail with exit 4 and a message naming the target.

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

#### Scenario: A tagged include string is a literal
- **WHEN** the config is `a: !literal file:nope.md\nb: !literal https://example.invalid/x.yaml\n` and neither target exists
- **THEN** `get a` prints `file:nope.md\n`, `get b` prints `https://example.invalid/x.yaml\n`, and nothing is fetched

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

### Requirement: Remote includes
An include whose target is an `https://` or `http://` URL SHALL be fetched with an HTTP GET each time the
configuration is loaded, following redirects. The response body of a 2xx response is the target's content, decoded
as UTF-8. The fetch SHALL fail when the server cannot be reached, the response is not 2xx after redirects, no
response arrives within 30 seconds, or the body is not valid UTF-8. A failed fetch, or remote YAML content that is
not valid YAML, SHALL fail loading with exit 4 and a message naming the URL.

Remote content SHALL be loaded like a local file of the same kind: YAML content can hold includes, anchors, aliases
and merge keys, and can be the target of a mapping-form include with overrides (with the same exit-4 rules as for a
local target). A `file:` include inside remote content SHALL name the URL formed by resolving the path after `file:`
against the URL of the content that holds it. Within one command, each URL SHALL be fetched at most once, and every
use of it SHALL see the same content. A cycle of remote includes SHALL fail with exit 4, naming a URL in the cycle.

#### Scenario: Remote YAML include
- **WHEN** `<base>/coder.yaml` serves `model: m1\n` and `troupe.yml` is `agents:\n  coder: <base>/coder.yaml\n`
- **THEN** `get agents.coder.model` prints `m1\n`

#### Scenario: Remote text include
- **WHEN** `<base>/prompt.md` serves `Hello\r\nWorld\n` and `troupe.yml` is `prompt: <base>/prompt.md\n`
- **THEN** `get prompt` prints `Hello\r\nWorld\n` exactly

#### Scenario: The URL path decides YAML or text
- **WHEN** `troupe.yml` is `a: <base>/a.yaml?v=2\nb: <base>/b.txt\n`, and both serve `x: 1\n`
- **THEN** `get a.x` prints `1\n` and `get b` prints `x: 1\n`

#### Scenario: Remote include in mapping form with overrides
- **WHEN** `<base>/coder.yaml` serves `model: m1\ntemperature: 0.2\n` and `troupe.yml` is `coder:\n  $ref: <base>/coder.yaml\n  temperature: 0.3\n`
- **THEN** `show coder` prints `model: m1\ntemperature: 0.3\n`

#### Scenario: Relative include inside remote content
- **WHEN** `<base>/agents/coder.yaml` serves `prompt: file:coder.md\n`, `<base>/agents/coder.md` serves `Hi\n`, and `troupe.yml` is `coder: <base>/agents/coder.yaml\n`
- **THEN** `get coder.prompt` prints `Hi\n`

#### Scenario: Remote include from an included local file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `limits: <base>/limits.yaml\n`, and `<base>/limits.yaml` serves `calls: 5\n`
- **THEN** `get coder.limits.calls` prints `5\n`

#### Scenario: Not found
- **WHEN** `troupe.yml` is `coder: <base>/missing.yaml\n` and the server answers 404
- **THEN** every subcommand exits 4, stdout is empty, and stderr names `<base>/missing.yaml`

#### Scenario: Server unreachable
- **WHEN** `troupe.yml` is `coder: http://127.0.0.1:<a closed port>/coder.yaml\n`
- **THEN** every subcommand exits 4 and stderr names the URL

#### Scenario: Invalid remote YAML
- **WHEN** `<base>/coder.yaml` serves `a: [1\n` and `troupe.yml` is `coder: <base>/coder.yaml\n`
- **THEN** every subcommand exits 4 and stderr names `<base>/coder.yaml`

#### Scenario: Fetched once per command
- **WHEN** `troupe.yml` is `a: <base>/c.yaml\nb: <base>/c.yaml\n` and `set x 1` runs
- **THEN** the server receives exactly one request for `/c.yaml` during that command

#### Scenario: Remote cycle
- **WHEN** `<base>/a.yaml` serves `b: file:b.yaml\n`, `<base>/b.yaml` serves `a: <base>/a.yaml\n`, and `troupe.yml` is `x: <base>/a.yaml\n`
- **THEN** every subcommand exits 4 and stderr names a URL in the cycle

### Requirement: The `!literal` tag
A scalar tagged `!literal` SHALL load as the string of its text, as if it were tagged `!!str`, in any quoting style
or as a block scalar, and SHALL never be an include. `!literal` on a mapping or a list SHALL fail to load with exit 4,
naming the file. Every other tag that is not a core-schema tag SHALL still fail to load with exit 4.

#### Scenario: Literal strings
- **WHEN** the config is `a: !literal https://example.com/api\nb: !literal 5\nc: !literal "file:x"\n`
- **THEN** `show` prints `a: https://example.com/api\nb: '5'\nc: file:x\n`, and nothing is fetched

#### Scenario: Literal on a collection
- **WHEN** the config is `a: !literal {b: 1}\n`
- **THEN** every subcommand exits 4 and stderr names the config file

#### Scenario: Other tags still refused
- **WHEN** the config is `a: !secret x\n`
- **THEN** every subcommand exits 4 and stderr names the config file
