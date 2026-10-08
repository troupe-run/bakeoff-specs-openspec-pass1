# Spec Delta

## Purpose

Lets a theatre describe its configuration with a JSON Schema at `.troupe/troupe.schema.json`. The schema says which
URL-valued settings are literal strings and not includes, and every load and every `set` result must be valid
against it.

In the scenarios below, `<base>` is the URL of a directory served over HTTP.

## ADDED Requirements

### Requirement: The schema file
When `<theatre>/.troupe/troupe.schema.json` exists, it SHALL be read on every load of the configuration as a JSON
Schema, under the rules of JSON Schema draft 2020-12 whatever its `$schema` says. When it does not exist, no
validation takes place and no string is a literal because of a schema. A schema file that is not valid UTF-8, not
valid JSON, not a valid draft 2020-12 schema, or that refers (`$ref`) to anything outside its own document, SHALL
fail loading with exit 4 and a message naming the schema file. troupe SHALL never fetch anything a schema refers to.

#### Scenario: No schema
- **WHEN** `.troupe/troupe.schema.json` does not exist and the config is `a: 1\n`
- **THEN** `get a` prints `1\n`

#### Scenario: Schema that is not JSON
- **WHEN** `.troupe/troupe.schema.json` contains `{"type": "object",`
- **THEN** every subcommand exits 4 and stderr names `troupe.schema.json`

#### Scenario: Schema that is not a valid schema
- **WHEN** `.troupe/troupe.schema.json` contains `{"type": 5}`
- **THEN** every subcommand exits 4 and stderr names `troupe.schema.json`

#### Scenario: Reference outside the schema
- **WHEN** `.troupe/troupe.schema.json` contains `{"$ref": "https://example.invalid/other.json"}`
- **THEN** every subcommand exits 4, stderr names `troupe.schema.json`, and nothing is fetched

### Requirement: Strings the schema marks as URIs are literals
The schema of a position in the configuration SHALL be found from the root schema, one path segment at a time: for
a mapping key `k`, the current schema's `properties` entry for `k` if it has one, otherwise its
`additionalProperties` if that is a schema object; for a list item, the current schema's `items` if that is a schema
object. Nothing else (such as `$ref`, `allOf`, `prefixItems` or `patternProperties`) SHALL be followed. When there is
no such schema at some segment, the position has none. A string at a position whose schema has `"format": "uri"`
SHALL be a literal, not an include, whatever its prefix (`file:`, `https://` or `http://`).

The position of a string is its path in the loaded configuration, with includes resolved: a string inside included
content is at the include's path followed by its path inside that content, and the `$ref` string of a mapping-form
include is at the mapping's path followed by `$ref`. A node reached through an alias or a merge key SHALL be judged
at the position where its anchored node is written.

#### Scenario: A URI setting is not fetched
- **WHEN** the schema is `{"type": "object", "properties": {"endpoint": {"type": "string", "format": "uri"}}}` and the config is `endpoint: https://api.example.invalid/v1.yaml\n`
- **THEN** `get endpoint` prints `https://api.example.invalid/v1.yaml\n` and nothing is fetched

#### Scenario: The same string elsewhere is an include
- **WHEN** with that schema, the config is `endpoint: <base>/x.yaml\nshared: <base>/x.yaml\n` and `<base>/x.yaml` serves `a: 1\n`
- **THEN** `get endpoint` prints `<base>/x.yaml\n` and `get shared.a` prints `1\n`

#### Scenario: Through additionalProperties and items
- **WHEN** the schema is `{"properties": {"agents": {"additionalProperties": {"properties": {"docs": {"items": {"format": "uri"}}}}}}}` and the config is `agents:\n  coder:\n    docs: [https://example.invalid/a.md, file:b.md]\n`
- **THEN** `show agents.coder.docs` prints `- https://example.invalid/a.md\n- file:b.md\n` and nothing is fetched or read

#### Scenario: Inside included content
- **WHEN** the schema marks `agents.coder.homepage` as `format: uri`, `troupe.yml` is `agents:\n  coder: file:agents/coder.yaml\n`, and `agents/coder.yaml` is `homepage: https://example.invalid/coder\n`
- **THEN** `get agents.coder.homepage` prints `https://example.invalid/coder\n`

#### Scenario: Only properties, items and additionalProperties are followed
- **WHEN** the schema is `{"properties": {"endpoint": {"$ref": "#/$defs/url"}}, "$defs": {"url": {"format": "uri"}}}` and the config is `endpoint: file:nope.md\n`
- **THEN** every subcommand exits 4 and stderr names the missing `nope.md`, since `endpoint` is not marked

### Requirement: The configuration must be valid against the schema
After includes, aliases and merge keys are resolved, the configuration's data (mappings as JSON objects, lists as
arrays, literal strings as strings, text includes as strings) SHALL be validated against the schema. A configuration
that is not valid SHALL fail loading with exit 4, with a message naming the schema file and the path of a value that
fails. `format` SHALL be treated as an annotation, not checked, as draft 2020-12 specifies by default.

#### Scenario: Invalid configuration
- **WHEN** the schema is `{"properties": {"temperature": {"type": "number"}}}` and the config is `temperature: hot\n`
- **THEN** every subcommand exits 4, stdout is empty, and stderr names `troupe.schema.json` and `temperature`

#### Scenario: Included content is validated
- **WHEN** the schema is `{"properties": {"coder": {"required": ["model"]}}}`, the config is `coder: file:coder.yaml\n`, and `coder.yaml` is `temperature: 0.2\n`
- **THEN** every subcommand exits 4 and stderr names `troupe.schema.json` and `coder`

#### Scenario: Format is not checked
- **WHEN** the schema marks `endpoint` as `format: uri` and the config is `endpoint: not a url\n`
- **THEN** `get endpoint` prints `not a url\n`

#### Scenario: A hand edit that breaks validity
- **WHEN** the schema requires `temperature` to be a number, the theatre was imported with `temperature: 0.2\n`, and the file is edited by hand to `temperature: hot\n`
- **THEN** `show` exits 4 and no event is recorded

### Requirement: `set` keeps the configuration valid
A `set` whose resulting configuration would not be valid against the schema SHALL be refused with exit 3: no file
changes and no event of the `set` is recorded. stderr SHALL name `PATH` and the schema file.

#### Scenario: Invalid value refused
- **WHEN** the schema requires `temperature` to be a number, the config is `temperature: 0.2\n`, and `set temperature hot` runs
- **THEN** the exit code is 3, the file is unchanged, stderr names `temperature` and `troupe.schema.json`, and `history` has no `cli` event

#### Scenario: Valid value accepted
- **WHEN** with the same schema, `set temperature 0.5` runs
- **THEN** the exit code is 0 and the file becomes `temperature: 0.5\n`
