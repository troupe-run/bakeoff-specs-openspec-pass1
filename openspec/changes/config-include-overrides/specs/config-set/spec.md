# Spec Delta

## ADDED Requirements

### Requirement: New keys under includes are written as overrides
Let A be the deepest existing ancestor mapping of a new key's `PATH`. Going up from A towards the root, if a YAML
include is reached (A itself, or an ancestor of A, being an included value) before any list item is left, the new key
SHALL be written as an override of the nearest such include, in the file that contains that include's reference (the
*including* file), and the included file SHALL NOT change. The override SHALL be at the path of the new key relative
to the include: it SHALL go into the deepest mapping of that path that the include's overrides already have, with any
missing intermediate override mappings created there, under the placement and quoting rules for new entries. If a list
item is left first (A is inside a list item), or the root is reached with no include, the key SHALL be written into
the file that holds A, as in "Creating new keys".

A scalar-form include that gets its first override SHALL first be converted to mapping form, in the including file:
- for a block mapping entry `KEY: STRING`, the include string and the whitespace before it SHALL be removed from the
  line, keeping the rest of the line (such as an end-of-line comment) unchanged, and the lines `$ref: STRING` and then
  the override entries SHALL follow, indented one indentation unit of the including file deeper than `KEY`;
- for a block list item `- STRING`, `$ref: ` SHALL be inserted before the include string, and the override entries
  SHALL follow on the next lines at the column where the include string started;
- for an include string that is the whole document, `$ref: ` SHALL be inserted before it, and the override entries
  SHALL follow at column 0;
- in a flow collection, the include string SHALL be replaced by `{$ref: STRING, <override entries>}`.
`STRING` SHALL be the include string exactly as written, including its quotes. Lines are inserted with the including
file's line ending, and a line whose value grows keeps its end-of-line comment under "End-of-line comment alignment".

#### Scenario: Scalar-form include converted, comment kept
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml  # c\n`, `agents/coder.yaml` is `model: m\n`, and `set coder.temperature 0.3` runs
- **THEN** `troupe.yml` becomes `coder:  # c\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n`, `agents/coder.yaml` is unchanged, and `get coder.temperature` prints `0.3\n`

#### Scenario: Conversion at the including file's indentation
- **WHEN** `troupe.yml` is `agents:\n    coder: file:agents/coder.yaml\n` and `set agents.coder.temperature 0.3` runs
- **THEN** `troupe.yml` becomes `agents:\n    coder:\n        $ref: file:agents/coder.yaml\n        temperature: 0.3\n`

#### Scenario: Existing mapping-form include gains an override
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n` and `set coder.top_p 0.9` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n  top_p: 0.9\n` and `agents/coder.yaml` is unchanged

#### Scenario: Ancestor deeper inside the included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `limits:\n  tokens: 100\n`, and `set coder.limits.calls 9` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n` and `show coder.limits` prints `tokens: 100\ncalls: 9\n`

#### Scenario: Into an existing override mapping
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n`, `agents/coder.yaml` is `limits:\n  tokens: 100\n`, and `set coder.limits.burst 2` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n    burst: 2\n`

#### Scenario: Missing intermediate mappings under an include
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n` and `set coder.a.b x` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  a:\n    b: x\n`

#### Scenario: A file included twice stays shared
- **WHEN** `troupe.yml` is `a: file:common.yaml\nb: file:common.yaml\n`, `common.yaml` is `x: 1\n`, and `set a.k 1` runs
- **THEN** `troupe.yml` becomes `a:\n  $ref: file:common.yaml\n  k: 1\nb: file:common.yaml\n`, `common.yaml` is unchanged, and `get b.k` exits 5

#### Scenario: Quoted include string
- **WHEN** `troupe.yml` is `coder: 'file:agents/coder.yaml'\n` and `set coder.t 1` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: 'file:agents/coder.yaml'\n  t: 1\n`

#### Scenario: Include in a flow mapping
- **WHEN** `troupe.yml` is `agents: {coder: file:agents/coder.yaml}\n` and `set agents.coder.t 1` runs
- **THEN** `troupe.yml` becomes `agents: {coder: {$ref: file:agents/coder.yaml, t: 1}}\n`

#### Scenario: Include as a list item
- **WHEN** `troupe.yml` is `steps:\n  - file:step.yaml\n`, `step.yaml` is `name: a\n`, and `set steps.0.k v` runs
- **THEN** `troupe.yml` becomes `steps:\n  - $ref: file:step.yaml\n    k: v\n` and `step.yaml` is unchanged

#### Scenario: Whole document is an include
- **WHEN** `troupe.yml` is `file:base.yaml\n`, `base.yaml` is `a: 1\n`, and `set k v` runs
- **THEN** `troupe.yml` becomes `$ref: file:base.yaml\nk: v\n` and `base.yaml` is unchanged

#### Scenario: Nested include: the nearest including file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `limits: file:limits.yaml\n`, `agents/limits.yaml` is `calls: 5\n`, and `set coder.limits.burst 2` runs
- **THEN** `agents/coder.yaml` becomes `limits:\n  $ref: file:limits.yaml\n  burst: 2\n`, and `troupe.yml` and `agents/limits.yaml` are unchanged

#### Scenario: Key inside a list item of an included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `steps:\n  - name: a\n`, and `set coder.steps.0.n 1` runs
- **THEN** `agents/coder.yaml` becomes `steps:\n  - name: a\n    n: 1\n` and `troupe.yml` is unchanged

#### Scenario: CRLF including file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\r\n` and `set coder.t 1` runs
- **THEN** `troupe.yml` becomes `coder:\r\n  $ref: file:agents/coder.yaml\r\n  t: 1\r\n`

## MODIFIED Requirements

### Requirement: Target file for an existing value
An existing value SHALL be changed in the file that holds it, including files reached through YAML includes: the file
that `show --sources` names for it. For a value that an override sets, that is the file holding the override, and the
included file SHALL NOT change; a value that no override sets is changed in the included file it comes from.
When `PATH` names a text include, the target file's content SHALL become `VALUE` exactly, except that if the target
file contains a CRLF line ending, every LF in `VALUE` not already preceded by CR SHALL be written as CRLF. A non-string
`VALUE` for a text include SHALL be refused with exit 3.

#### Scenario: Value inside an included file
- **WHEN** `agents.coder` is `file:agents/coder.yaml` and `set agents.coder.model m2` runs
- **THEN** only `agents/coder.yaml` changes, and only the model's value bytes change

#### Scenario: Overridden value changes the override
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n`, `agents/coder.yaml` is `model: m\ntemperature: 0.2\n`, and `set coder.temperature 0.5` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.5\n` and `agents/coder.yaml` is unchanged

#### Scenario: Value that is not overridden changes where it lives
- **WHEN** the same theatre and `set coder.model m2` runs
- **THEN** `agents/coder.yaml` becomes `model: m2\ntemperature: 0.2\n` and `troupe.yml` is unchanged

#### Scenario: Text include
- **WHEN** `prompt` is `file:prompt.md` and `set prompt "New\ntext\n"` runs
- **THEN** `prompt.md` contains exactly `New\ntext\n` and `troupe.yml` is unchanged

#### Scenario: Text include with CRLF
- **WHEN** `prompt.md` contains `a\r\nb\r\n` and `set prompt "x\ny\n"` runs
- **THEN** `prompt.md` contains exactly `x\r\ny\r\n`

#### Scenario: Non-string into a text include
- **WHEN** `prompt` is a text include and `set prompt 5` runs
- **THEN** the exit code is 3, no file changes, and stderr names `prompt`

### Requirement: Refusing to replace an include
Replacing the value at a path whose whole value comes from a YAML include (the path names the include string itself,
or the mapping that holds a `$ref`) SHALL be refused with exit 3, naming the path, and no file SHALL change. This
applies whatever the new value is, and also when a `set` on an ancestor would change or delete such a value. A `set`
on an ancestor that leaves the included value (with its overrides merged) equal is allowed and does not touch the
included file. A `VALUE` equal to the include string counts as leaving the value equal only when the include has no
overrides.

#### Scenario: Replacing an included mapping
- **WHEN** `agents.coder` is `file:agents/coder.yaml` and `set agents.coder "{model: x}"` runs
- **THEN** the exit code is 3, stderr names `agents.coder`, and no file changes

#### Scenario: Changing an include through its parent
- **WHEN** `agents.coder` is `file:agents/coder.yaml` and `set agents VALUE` runs where VALUE's `coder` differs from the included content, or omits `coder`
- **THEN** the exit code is 3 and no file changes

#### Scenario: Replacing an included scalar
- **WHEN** `limit` is `file:limit.yaml`, which contains `5`, and `set limit 6` runs
- **THEN** the exit code is 3 and no file changes

#### Scenario: Dropping overrides by setting the include string
- **WHEN** `coder` is `{$ref: file:agents/coder.yaml, temperature: 0.3}` in block form and `set coder file:agents/coder.yaml` runs
- **THEN** the exit code is 3, stderr names `coder`, and no file changes

#### Scenario: Parent set that keeps the merged value
- **WHEN** `troupe.yml` is `agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    temperature: 0.3\n  other: 1\n`, `agents/coder.yaml` is `model: m\n`, and `set agents "{coder: {model: m, temperature: 0.3}, other: 2}"` runs
- **THEN** the exit code is 0, only `other`'s value bytes in `troupe.yml` change, and `agents/coder.yaml` is unchanged

### Requirement: Setting a collection value
When both the existing value and `VALUE` are mappings, or both are lists, `set` SHALL apply the difference: keys
(or indexes) present in both are set recursively, so unchanged leaves keep their bytes, including across YAML include
boundaries that the include rules allow. New keys or items are added under the new-entry rules, and keys (or trailing
items) missing from `VALUE` are deleted. Deleting a block entry SHALL remove the lines from the entry's first line
through the end of its value, including that value's end-of-line comment, and SHALL keep comment lines before and
after it. Deleting a flow entry SHALL remove the entry and one adjacent separator. A key that is deleted SHALL be
removed from every file that sets it (the included content and each override that sets it), so that it is absent from
the result; an override mapping that is left with no entries SHALL be deleted in turn (a mapping holding `$ref` is
never deleted this way). In every other case the existing node SHALL be replaced as a whole: in the override that sets
it when there is one, leaving the included content unchanged, and otherwise in the file that holds it.

#### Scenario: Partial mapping update keeps unchanged bytes
- **WHEN** the file is `a:\n  b: 1  # keep\n  c: 2\n` and `set a "{b: 1, c: 3}"` runs
- **THEN** the file becomes `a:\n  b: 1  # keep\n  c: 3\n`

#### Scenario: Key removed by a mapping value
- **WHEN** the file is `a:\n  b: 1\n  c: 2\n` and `set a "{b: 1}"` runs
- **THEN** the file becomes `a:\n  b: 1\n`

#### Scenario: Deleting an overridden key
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n`, `agents/coder.yaml` is `limits:\n  tokens: 100\n  calls: 5\n`, and `set coder.limits "{tokens: 100}"` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n`, `agents/coder.yaml` becomes `limits:\n  tokens: 100\n`, and `show coder.limits` prints `tokens: 100\n`

#### Scenario: Replacing an overridden mapping
- **WHEN** the same theatre and `set coder.limits 5` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  limits: 5\n` and `agents/coder.yaml` is unchanged

### Requirement: Creating new keys
A `PATH` whose final key does not exist SHALL be written into the file containing the deepest existing ancestor
mapping of `PATH`, with any missing intermediate mappings created there, except where "New keys under includes are
written as overrides" sends it to an including file as an override. Descending into an existing scalar (including
null) or a text include SHALL exit 5. A digit-only segment that would need a missing intermediate created, or that is
applied to a mapping, SHALL exit 5. An empty (or comment-only) file SHALL be treated as an empty block mapping at
column 0.

#### Scenario: New key in an existing mapping
- **WHEN** the file is `agents:\n  coder:\n    model: m\n` and `set agents.coder.temperature 0.2` runs
- **THEN** the file becomes `agents:\n  coder:\n    model: m\n    temperature: 0.2\n`

#### Scenario: Missing intermediate mappings
- **WHEN** the file is `a: 1\n` and `set b.c.d x` runs
- **THEN** the file becomes `a: 1\nb:\n  c:\n    d: x\n`

#### Scenario: Digit segment for a missing intermediate
- **WHEN** `a` is a mapping without `b` and `set a.b.0 x` runs
- **THEN** the exit code is 5 and no file changes

#### Scenario: New key inside an included mapping
- **WHEN** `troupe.yml` is `agents:\n  coder: file:agents/coder.yaml\n` (`agents/coder.yaml` a mapping) and `set agents.coder.temperature 0.2` runs
- **THEN** `agents/coder.yaml` is unchanged and `troupe.yml` becomes `agents:\n  coder:\n    $ref: file:agents/coder.yaml\n    temperature: 0.2\n`

#### Scenario: Parent is a scalar
- **WHEN** `model` is `m` and `set model.x 1` runs
- **THEN** the exit code is 5 and no file changes

#### Scenario: Parent is null
- **WHEN** the file is `agents:\n` and `set agents.coder x` runs
- **THEN** the exit code is 5 and no file changes

### Requirement: Appending to lists
A `PATH` whose final segment is an index equal to the list's length SHALL append `VALUE` to the list, in the file that
holds the list (for a list that an override sets, the file holding the override). Appending is never written as an
override. A larger index SHALL exit 5.

#### Scenario: Append to a block list
- **WHEN** the file is `tools:\n  - a\n  - b\n` and `set tools.2 c` runs
- **THEN** the file becomes `tools:\n  - a\n  - b\n  - c\n`

#### Scenario: Append to a list in an included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `tools:\n  - read\n`, and `set coder.tools.1 write` runs
- **THEN** `agents/coder.yaml` becomes `tools:\n  - read\n  - write\n` and `troupe.yml` is unchanged

#### Scenario: Append to an overridden list
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  tools: [read]\n`, `agents/coder.yaml` is `tools: [read, write]\n`, and `set coder.tools.1 exec` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  tools: [read, exec]\n` and `agents/coder.yaml` is unchanged

#### Scenario: Index past the end
- **WHEN** `tools` has 2 items and `set tools.3 c` runs
- **THEN** the exit code is 5 and no file changes
