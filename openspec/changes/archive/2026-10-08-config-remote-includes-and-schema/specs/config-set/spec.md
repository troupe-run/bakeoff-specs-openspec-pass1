# Spec Delta

In the scenarios below, `<base>` is the URL of a directory served over HTTP, and a *remote* value is one written in
content fetched from a URL (see config-loading, "Remote includes").

## MODIFIED Requirements

### Requirement: Values that are includes
A string in `VALUE` that would be read as an include, because it starts with `file:`, `https://` or `http://`, is
**include-looking**. This applies to `VALUE` itself and to every string inside a mapping or list `VALUE`, each at
its own path. Unless `--include` is given, an include-looking string whose path the schema does not mark
`format: uri` (see config-schema) SHALL be written tagged `!literal`, so that it reads back as that string (see
"Writing literal strings"). An include-looking string at a path the schema marks `format: uri` SHALL be written
untagged, since it is a literal there anyway.

With `--include`, include-looking strings SHALL be written untagged and SHALL then be includes. If the resulting
configuration cannot be loaded (missing target, failed fetch, cycle, or not valid against the schema), the write SHALL
be refused with exit 3 and no file SHALL change. `--include` on a `set` that would write an include-looking string at
a path the schema marks `format: uri` SHALL be refused with exit 3, naming that path, since the string cannot be an
include there. `--include` SHALL NOT change anything else: strings that are not include-looking, and the text written
into a text include's target file, are written as without it.

#### Scenario: A file: string is written literally
- **WHEN** the file is `a: 1\n` and `set prompt file:p.md` runs
- **THEN** the file becomes `a: 1\nprompt: !literal file:p.md\n` and `get prompt` prints `file:p.md\n`

#### Scenario: A URL is written literally
- **WHEN** the file is `a: 1\n` and `set docs https://example.invalid/team.yaml` runs
- **THEN** the file becomes `a: 1\ndocs: !literal https://example.invalid/team.yaml\n` and nothing is fetched

#### Scenario: Strings inside a collection VALUE
- **WHEN** the file is `a: 1\n` and `set links "[https://example.invalid/a, plain]"` runs
- **THEN** the file becomes `a: 1\nlinks:\n  - !literal https://example.invalid/a\n  - plain\n`

#### Scenario: A path the schema marks as a URI
- **WHEN** the schema marks `endpoint` as `format: uri`, the file is `a: 1\n`, and `set endpoint https://api.example.invalid/v1` runs
- **THEN** the file becomes `a: 1\nendpoint: https://api.example.invalid/v1\n`

#### Scenario: --include writes an include
- **WHEN** the file is `a: 1\n`, `.troupe/p.md` contains `hello\n`, and `set prompt file:p.md --include` runs
- **THEN** the file becomes `a: 1\nprompt: file:p.md\n` and `get prompt` prints `hello\n`

#### Scenario: --include with a remote target
- **WHEN** `<base>/team.yaml` serves `model: m\n`, the file is `a: 1\n`, and `set team <base>/team.yaml --include` runs
- **THEN** the file becomes `a: 1\nteam: <base>/team.yaml\n` and `get team.model` prints `m\n`

#### Scenario: Include to a missing file
- **WHEN** `set prompt file:nope.md --include` runs and `nope.md` does not exist
- **THEN** the exit code is 3 and no file changes

#### Scenario: Include whose fetch fails
- **WHEN** `set team <base>/missing.yaml --include` runs and the server answers 404
- **THEN** the exit code is 3, stderr names `team`, and no file changes

#### Scenario: --include at a URI path
- **WHEN** the schema marks `endpoint` as `format: uri` and `set endpoint https://api.example.invalid/v1 --include` runs
- **THEN** the exit code is 3, stderr names `endpoint`, and no file changes

#### Scenario: Setting an include to its own string
- **WHEN** `agents.coder` is `file:agents/coder.yaml` (no overrides) and `set agents.coder file:agents/coder.yaml --include` runs
- **THEN** the exit code is 0 and no file changes; without `--include` the same command is refused with exit 3 (it would replace the include with a string)

#### Scenario: Text written into a text include is not tagged
- **WHEN** `prompt` is `file:prompt.md` and `set prompt https://example.invalid/x` runs
- **THEN** `prompt.md` becomes `https://example.invalid/x` and `troupe.yml` is unchanged

## ADDED Requirements

### Requirement: Writing literal strings
A string written tagged `!literal` SHALL be written as `!literal`, one space, and the scalar as it would be written
without the tag (under "Scalar quoting", "Double-quoted escaping" and "Multi-line strings and block scalars"), so a
block scalar is written `!literal |`. When the value of a scalar already tagged `!literal` is changed to a string,
the tag SHALL be kept and only the scalar after it SHALL change, whether or not the new string is include-looking.
When it is changed to anything that is not a string (a number, boolean, null, mapping or list), the tag SHALL be
removed with the scalar. An untagged scalar changed to a string that must be written `!literal` SHALL get the tag in
front of the new scalar. Replacing a scalar with any other tag remains refused (exit 3).

#### Scenario: Keeping the tag
- **WHEN** the file is `docs: !literal https://a.example.invalid\nb: 1\n` and `set docs other` runs
- **THEN** the file becomes `docs: !literal other\nb: 1\n`

#### Scenario: Dropping the tag for a non-string
- **WHEN** the file is `a: !literal file:x\n` and `set a 5` runs
- **THEN** the file becomes `a: 5\n`

#### Scenario: Adding the tag to an existing value
- **WHEN** the file is `docs: 'old'\n` and `set docs https://example.invalid/new` runs
- **THEN** the file becomes `docs: !literal 'https://example.invalid/new'\n`

#### Scenario: Multi-line literal
- **WHEN** the file is `a: 1\n` and `set note "file:x\nmore\n"` runs
- **THEN** the file becomes `a: 1\nnote: !literal |\n  file:x\n  more\n`

### Requirement: Values from remote includes are read-only
A `set` that would change or delete a remote value, append an item to or delete an item from a remote list, add a
key to a remote mapping other than as an override, change a remote text include, or expand an alias written in
remote content SHALL be refused with exit 3. No file SHALL change and no event of the `set` SHALL be recorded. This
holds for a `PATH` that names the value and for a mapping or list `VALUE` on an ancestor that would make any of
these changes. stderr SHALL name `PATH` and contain the include string through which the remote content is reached,
exactly as it is written in the local file that holds it, together with that file's path and the include's line
number. With nested remote includes, that is the outermost one, the include written in a local file.

A value that a local override sets is not remote, and SHALL be changed in the override as before. A new key under a
remote include SHALL be written as an override, as in "New keys under includes are written as overrides", except
that the include it overrides SHALL be the nearest one whose reference is written in a local file. With
`--in-include`, a new key whose deepest existing ancestor is in remote content SHALL be refused with exit 3, as
above. A delete of a key that remote content sets SHALL be refused with exit 3 even if an override also sets it,
since overrides cannot delete it.

#### Scenario: Changing a remote value
- **WHEN** `<base>/coder.yaml` serves `model: m1\n`, `troupe.yml` is `agents:\n  coder: <base>/coder.yaml  # shared\n`, and `set agents.coder.model m2` runs
- **THEN** the exit code is 3, stdout is empty, stderr contains `agents.coder.model`, `<base>/coder.yaml`, `.troupe/troupe.yml` and line `2`, `troupe.yml` is unchanged, and `history` has no `cli` event

#### Scenario: The include string as written
- **WHEN** `troupe.yml` is `coder: "<base>/coder.yaml"\n` and `set coder.model m2` runs
- **THEN** the exit code is 3 and stderr contains `"<base>/coder.yaml"`

#### Scenario: A new key becomes a local override
- **WHEN** `<base>/coder.yaml` serves `model: m1\n`, `troupe.yml` is `coder: <base>/coder.yaml  # shared\n`, and `set coder.temperature 0.3` runs
- **THEN** `troupe.yml` becomes `coder:  # shared\n  $ref: <base>/coder.yaml\n  temperature: 0.3\n` and `show coder` prints `model: m1\ntemperature: 0.3\n`

#### Scenario: An overridden value is local
- **WHEN** `troupe.yml` is `coder:\n  $ref: <base>/coder.yaml\n  temperature: 0.3\n`, `<base>/coder.yaml` serves `temperature: 0.2\n`, and `set coder.temperature 0.5` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: <base>/coder.yaml\n  temperature: 0.5\n`

#### Scenario: Deleting a remote key
- **WHEN** `<base>/coder.yaml` serves `model: m1\ntemperature: 0.2\n`, `troupe.yml` is `coder: <base>/coder.yaml\n`, and `set coder "{model: m1}"` runs
- **THEN** the exit code is 3, stderr contains `<base>/coder.yaml`, and no file changes

#### Scenario: Appending to a remote list
- **WHEN** `<base>/coder.yaml` serves `tools: [read]\n`, `troupe.yml` is `coder: <base>/coder.yaml\n`, and `set coder.tools.1 write` runs
- **THEN** the exit code is 3 and no file changes

#### Scenario: A remote text include
- **WHEN** `<base>/prompt.md` serves `Hi\n`, `troupe.yml` is `prompt: <base>/prompt.md\n`, and `set prompt "Bye\n"` runs
- **THEN** the exit code is 3, stderr contains `<base>/prompt.md`, and no file changes

#### Scenario: --in-include under a remote include
- **WHEN** `troupe.yml` is `coder: <base>/coder.yaml\n` and `set coder.temperature 0.3 --in-include` runs
- **THEN** the exit code is 3, stderr contains `<base>/coder.yaml`, and no file changes

#### Scenario: Nested remote includes name the local include line
- **WHEN** `<base>/coder.yaml` serves `limits: file:limits.yaml\n`, `<base>/limits.yaml` serves `calls: 5\n`, `troupe.yml` is `coder: <base>/coder.yaml\n`, and `set coder.limits.calls 9` runs
- **THEN** the exit code is 3 and stderr contains `<base>/coder.yaml` and `.troupe/troupe.yml`

#### Scenario: A new key under nested remote includes
- **WHEN** with the same files, `set coder.limits.burst 2` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: <base>/coder.yaml\n  limits:\n    burst: 2\n` and `get coder.limits.calls` prints `5\n`

#### Scenario: A remote include in a local included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `limits: <base>/limits.yaml\n`, and `set coder.limits.calls 9` runs
- **THEN** the exit code is 3 and stderr contains `<base>/limits.yaml` and `.troupe/agents/coder.yaml`
