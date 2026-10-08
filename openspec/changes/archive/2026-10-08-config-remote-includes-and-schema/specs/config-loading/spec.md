# Spec Delta

In the scenarios below, `<base>` is the URL of a directory served over HTTP (for example
`http://127.0.0.1:8123/team`).

## MODIFIED Requirements

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

## ADDED Requirements

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
