# config-set Specification

## Purpose

Lets a user change one setting from the command line and have the change written back into the hand-edited file
that holds it. The file diff contains only the bytes the change requires, so comments, quoting and layout elsewhere
stay exactly as the user wrote them.

In the scenarios below, file contents are written with `\n` for a line feed and `⏎` where a value contains a newline.

## Requirements

### Requirement: Byte-surgical write-back
After a successful `troupe config set PATH VALUE`, the only bytes that differ in any file SHALL be those the rules
in this capability require to change. Bytes are compared after UTF-8 decoding, and columns count Unicode code points.
Lines that `set` inserts SHALL use the line ending of the file they go into (CRLF if the file's first line break is
CRLF, otherwise LF). If a file being appended to does not end with a line break, one SHALL be added before the new
lines. A `set` whose VALUE equals the current value SHALL change no file and exit 0.

#### Scenario: Only the value bytes change
- **WHEN** the file is `# top\nmodel:   'a'   # pick\nother: 1\n` and `set model b` runs
- **THEN** the file becomes `# top\nmodel:   'b'   # pick\nother: 1\n`

#### Scenario: No-op set
- **WHEN** `model` is `a` and `set model a` runs
- **THEN** no file's modification time or content changes, the exit code is 0, and no event is recorded

#### Scenario: CRLF file
- **WHEN** the file is `a: 1\r\nb:\r\n  c: 2\r\n` and `set b.d 3` runs
- **THEN** the file becomes `a: 1\r\nb:\r\n  c: 2\r\n  d: 3\r\n`

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

### Requirement: Scalar quoting
A changed scalar SHALL keep its quoting style (plain, single-quoted or double-quoted) if that style can represent the
new value. Otherwise it SHALL be written plain if possible, else single-quoted, else double-quoted. A new key, and a
new string value, SHALL copy the quoting style of the preceding sibling key or value (subject to the same fallback).
With no preceding sibling, or one whose value is not a flow scalar, it SHALL be plain if possible, with the same
fallback. A plain style can represent a value only if the text reads back as the same value and type in its context
(block or flow). A non-string value (number, boolean, null) SHALL always be written plain.

#### Scenario: Style kept
- **WHEN** the file is `a: "x"\n` and `set a y` runs
- **THEN** the file becomes `a: "y"\n`

#### Scenario: Style cannot represent the value
- **WHEN** the file is `a: x\n` and `set a "'true'"`, i.e. the string `true`, runs
- **THEN** the file becomes `a: 'true'\n`

#### Scenario: Quoted string to number
- **WHEN** the file is `a: '1'\n` and `set a 2` runs
- **THEN** the file becomes `a: 2\n`

#### Scenario: Copying the sibling's style
- **WHEN** the file is `m:\n  "k1": 'v1'\n` and `set m.k2 v2` runs
- **THEN** the file becomes `m:\n  "k1": 'v1'\n  "k2": 'v2'\n`

### Requirement: Double-quoted escaping
A double-quoted scalar SHALL escape only `\` (as `\\`), `"` (as `\"`) and control characters (C0, DEL and C1),
using the short forms `\0 \a \b \t \n \v \f \r \e \N` where they exist and `\xNN` otherwise. Every other character
SHALL be written literally.

#### Scenario: Literal non-ASCII
- **WHEN** the file is `a: "x"\n` and `set a` is given the VALUE `"é\ttab"` (the string `é`, TAB, `tab`)
- **THEN** the file becomes `a: "é\ttab"\n`

### Requirement: New collection values
A new mapping or list value SHALL be written in block style at the file's indentation unit (default 2), unless its
parent is a flow collection, where it SHALL be written in flow style (`{k: v, …}` / `[a, …]`). The indentation unit
SHALL be detected from the first nested block mapping in the file. Block lists under a mapping key SHALL copy the
offset of the file's first such list (so indentless `key:\n- a` files stay indentless). Empty collections SHALL be
written as `{}` and `[]`.

#### Scenario: Block mapping at the file's indentation
- **WHEN** the file is `a:\n    b: 1\n` and `set c "{d: 1, e: [x, y]}"` runs
- **THEN** the file becomes `a:\n    b: 1\nc:\n    d: 1\n    e:\n        - x\n        - y\n`

#### Scenario: Flow parent
- **WHEN** the file is `a: {b: 1}\n` and `set a.c "[1, 2]"` runs
- **THEN** the file becomes `a: {b: 1, c: [1, 2]}\n`

### Requirement: Multi-line strings and block scalars
A multi-line string replacing a plain or quoted scalar, or set as a new key's value in a block parent, SHALL be
written as a literal block scalar: `|` if the value ends with exactly one newline, `|-` if it has none, and `|+` if
it has more than one. Its content SHALL be indented one indentation unit deeper than the line that owns the
key or item. An indentation indicator SHALL be added when the first line starts with a space. A value that a literal
block cannot represent (such as one with control characters other than TAB) SHALL be written double-quoted. In a flow
parent, a new multi-line value SHALL be written double-quoted. A block scalar being changed SHALL keep its indicator
(`|` or `>`), indentation and chomping, changing the chomping only when the value's trailing newlines require it.

#### Scenario: Plain to literal block
- **WHEN** the file is `p: x\nq: 1\n` and `set p "a\nb\n"` runs
- **THEN** the file becomes `p: |\n  a\n  b\nq: 1\n`

#### Scenario: Literal block without trailing newline
- **WHEN** the file is `p: x\n` and `set p "a\nb"` runs
- **THEN** the file becomes `p: |-\n  a\n  b\n`

#### Scenario: Block scalar keeps indicator, chomping changes only when needed
- **WHEN** the file is `p: |+\n    a\n\nq: 1\n` and `set p "b\n"` runs
- **THEN** the file becomes `p: |+\n    b\nq: 1\n`
- **WHEN** instead `set p "b"` runs
- **THEN** the file becomes `p: |-\n    b\nq: 1\n`

### Requirement: Folded block scalars
When a folded (`>`) value changes, its paragraphs (one per line of the value) SHALL be matched with the old
value's paragraphs by sequence alignment. A paragraph whose text is unchanged SHALL keep its bytes. A changed
paragraph SHALL be re-wrapped, greedily by word, at the width of the longest content line of its old counterpart. A
single word longer than the width SHALL take a line of its own. A paragraph with no counterpart SHALL be wrapped at
the width of the longest content line of the old value. Words SHALL be separated at single spaces between non-space
characters. A change that would put a more-indented line (a line starting with a space or TAB) into the folded value
SHALL be refused with exit 3.

#### Scenario: Unchanged paragraph keeps bytes, changed one re-wraps
- **WHEN** the file is `d: >\n  one two\n  three\n\n  alpha beta\n` (value `one two three⏎alpha beta⏎`) and `set d "one two three\nalpha beta gamma\n"` runs
- **THEN** the file becomes `d: >\n  one two\n  three\n\n  alpha beta\n  gamma\n`. The first paragraph is unchanged, and the second is re-wrapped at width 10

#### Scenario: Long word
- **WHEN** a changed paragraph with width 5 contains the word `extraordinary`
- **THEN** `extraordinary` is on a line of its own

#### Scenario: More-indented line refused
- **WHEN** the new value for a folded scalar contains a line starting with a space
- **THEN** the exit code is 3 and no file changes

### Requirement: Placement of new entries
A new block list item or mapping key SHALL go after the collection's last entry, including the whole of that entry's
value, and after any comment lines that follow it before the next line indented less than the collection's entries.
A comment line indented less than the collection's entries SHALL end the collection. Blank lines after the last such
comment SHALL stay after the new entry. In a flow collection, a new entry SHALL be appended directly after the last
entry, on that entry's line, as `, <entry>` (an empty flow collection gets the entry between its brackets).

#### Scenario: Below trailing comments
- **WHEN** the file is `a:\n  b: 1\n  # more b things\n\n# about c\nc: 2\n` and `set a.x 1` runs
- **THEN** the file becomes `a:\n  b: 1\n  # more b things\n  x: 1\n\n# about c\nc: 2\n`

#### Scenario: Flow list append
- **WHEN** the file is `t: [a,\n  b]  # c\n` and `set t.2 z` runs
- **THEN** the file becomes `t: [a,\n  b, z] # c\n` (the comment keeps its column until the line reaches it, then has one space before it)

### Requirement: Scalar replaced by a block collection
When a scalar in a block mapping or list is replaced by a non-empty block collection, the owning line SHALL keep its
bytes up to and including its end-of-line comment, with the scalar's text removed. Without a comment, the whitespace
before the removed scalar SHALL be removed too. With a comment, the comment SHALL stay at its column. The collection
SHALL be written on the following lines.

#### Scenario: With comment
- **WHEN** the file is `a: 1  # note\n` and `set a "{b: 2}"` runs
- **THEN** the file becomes `a:    # note\n  b: 2\n` (the comment stays at column 6)

#### Scenario: Without comment
- **WHEN** the file is `a: 1\n` and `set a "[x]"` runs
- **THEN** the file becomes `a:\n  - x\n`

### Requirement: End-of-line comment alignment
When a changed value's length changes on a line that has an end-of-line comment, the whitespace before the comment
SHALL be adjusted so that the comment starts at its previous column. If the value now reaches that column, exactly
one space SHALL separate the value and the comment. No other line SHALL change.

#### Scenario: Shorter value
- **WHEN** the file is `a: long  # c\n` and `set a x` runs
- **THEN** the file becomes `a: x     # c\n`

#### Scenario: Value reaches the column
- **WHEN** the file is `a: x  # c\n` and `set a longer` runs
- **THEN** the file becomes `a: longer # c\n`

### Requirement: Values that are includes
A string `VALUE` that starts with `file:` SHALL be written like any other string and SHALL then be an include. If the
resulting configuration cannot be loaded (missing target or cycle), the write SHALL be refused with exit 3 and no file
SHALL change.

#### Scenario: Include to a missing file
- **WHEN** `set prompt file:nope.md` runs and `nope.md` does not exist
- **THEN** the exit code is 3 and no file changes

### Requirement: Verified, all-or-nothing writes
Before writing, `set` SHALL re-parse every edited file and reload the configuration from the edited texts. It SHALL
refuse with exit 3 (no file changed) if the result differs from the intended configuration. If the configuration
cannot be loaded before the change, `set` SHALL exit 4.

#### Scenario: Unrepresentable edit refused
- **WHEN** an edit would produce text that parses to a different configuration than intended
- **THEN** the exit code is 3, stderr names the path, and every file is byte-identical to before

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

### Requirement: Writing new keys into the included file on request
With `--in-include`, every new key that a `set` creates (whether `PATH` itself is new, or a mapping `VALUE` adds
keys) SHALL be written into the file that holds its deepest existing ancestor mapping, with any missing intermediate
mappings created there, and no override SHALL be written for it. When that ancestor mapping is merged from included
content and overrides, the file SHALL be the one holding the included content. When the ancestor exists only in an
override, the file SHALL be the one holding that override. With nested includes, the file SHALL be the innermost
included file that holds the ancestor. The flag SHALL NOT change anything else: existing values (overridden or not),
list appends, deletions, the placement, quoting and layout rules for new entries, the exit codes, and the events
recorded are as without it. Where no include is involved, `--in-include` SHALL give the same result as without it.

#### Scenario: New key into the included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml  # c\n`, `agents/coder.yaml` is `model: m\n`, and `set coder.temperature 0.3 --in-include` runs
- **THEN** `agents/coder.yaml` becomes `model: m\ntemperature: 0.3\n` and `troupe.yml` is unchanged

#### Scenario: Mapping-form include with overrides
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n`, `agents/coder.yaml` is `model: m\n`, and `set --in-include coder.top_p 0.9` runs
- **THEN** `agents/coder.yaml` becomes `model: m\ntop_p: 0.9\n` and `troupe.yml` is unchanged

#### Scenario: Ancestor merged from included content and an override
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  limits:\n    calls: 9\n`, `agents/coder.yaml` is `limits:\n  tokens: 100\n`, and `set coder.limits.burst 2 --in-include` runs
- **THEN** `agents/coder.yaml` becomes `limits:\n  tokens: 100\n  burst: 2\n` and `troupe.yml` is unchanged

#### Scenario: Ancestor only in an override
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  extra:\n    a: 1\n` and `set coder.extra.b 2 --in-include` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  extra:\n    a: 1\n    b: 2\n` and `agents/coder.yaml` is unchanged

#### Scenario: Missing intermediates in the included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `model: m\n`, and `set coder.a.b x --in-include` runs
- **THEN** `agents/coder.yaml` becomes `model: m\na:\n  b: x\n` and `troupe.yml` is unchanged

#### Scenario: Nested includes: the innermost file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `limits: file:limits.yaml\n`, `agents/limits.yaml` is `calls: 5\n`, and `set coder.limits.burst 2 --in-include` runs
- **THEN** `agents/limits.yaml` becomes `calls: 5\nburst: 2\n`, and `troupe.yml` and `agents/coder.yaml` are unchanged

#### Scenario: Mapping VALUE adds keys into the included file
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is `limits:\n  tokens: 100\n`, and `set coder.limits "{tokens: 100, calls: 9}" --in-include` runs
- **THEN** `agents/coder.yaml` becomes `limits:\n  tokens: 100\n  calls: 9\n` and `troupe.yml` is unchanged

#### Scenario: Existing overridden value still changes the override
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n`, `agents/coder.yaml` is `temperature: 0.2\n`, and `set coder.temperature 0.5 --in-include` runs
- **THEN** `troupe.yml` becomes `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.5\n` and `agents/coder.yaml` is unchanged

#### Scenario: No include involved
- **WHEN** the file is `a:\n  b: 1\n` and `set a.c 2 --in-include` runs
- **THEN** the file becomes `a:\n  b: 1\n  c: 2\n`, the same as without the flag

#### Scenario: Errors are unchanged
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n`, `agents/coder.yaml` is empty, and `set coder.x 1 --in-include` runs
- **THEN** the exit code is 5 and no file changes, as without the flag

#### Scenario: Events are unchanged
- **WHEN** `set coder.temperature 0.3 --in-include` runs on a scalar-form include whose file has no `temperature`
- **THEN** `history` gains one event, `set coder.temperature` (old null, new 0.3) via `cli`, exactly as it would without the flag

### Requirement: Setting a value defined at an anchor
When `PATH` is not reached through an alias or a merge key (see "Refusing to set through an alias" and "Merge keys
are never written"), `set` SHALL change the value where it is written, by the other rules of this capability. That
holds when the value is an anchored node or lies inside one. The anchor (`&name`) SHALL stay in place, in front of
the new value, so every alias of the anchor, and every mapping that merges it, has the new value. A whole anchored
node replaced by a value of another kind (for example a scalar by a block collection) SHALL keep its anchor on the
owning line. The events recorded SHALL be one per path whose value changed, including paths reached through
aliases and merge keys, all in the one change. A `set` that would delete an anchored node that an alias still
refers to SHALL be refused with exit 3, and no file SHALL change.

#### Scenario: Changing the anchor changes every alias
- **WHEN** the file is `defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n` and `set defaults.model sonnet` runs
- **THEN** the file becomes `defaults: &d\n  model: sonnet\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n`, `get coder.settings.model` and `get reviewer.settings.model` print `sonnet\n`, and `history` gains three `set` events, for `defaults.model`, `coder.settings.model` and `reviewer.settings.model` (old `opus`, new `sonnet`), sharing one `change` id

#### Scenario: Anchored scalar
- **WHEN** the file is `a: &x 1\nb: *x\n` and `set a 2` runs
- **THEN** the file becomes `a: &x 2\nb: *x\n`

#### Scenario: Anchored scalar replaced by a list
- **WHEN** the file is `a: &x 1\nb: *x\n` and `set a "[1, 2]"` runs
- **THEN** the file becomes `a: &x\n  - 1\n  - 2\nb: *x\n` and `show b` prints `- 1\n- 2\n`

#### Scenario: Deleting an anchor that is still used
- **WHEN** the file is `c:\n  a: &x 1\n  k: 2\nb: *x\n` and `set c "{k: 2}"` runs
- **THEN** the exit code is 3, stderr names `c`, and the file is unchanged

### Requirement: Refusing to set through an alias
A value is **reached through an alias** when the alias (`*name`) is its own value or the value of one of its
ancestors. Without `--expand-alias`, a `set` SHALL be refused with exit 3, no file SHALL change and no event of
its own SHALL be recorded, when it would change, add or delete a value reached through an alias. That covers:
- `PATH` itself, or an ancestor of it, reached through an alias, including a new key or list item below an alias;
- a mapping or list `VALUE` whose differences reach into an alias.

This holds in every file, including included files. stderr SHALL name `PATH`, the alias (`*name`) and the path
where the alias is written, and SHALL mention `--expand-alias`. The existing rules still apply: a `VALUE` equal to
the current value changes nothing and exits 0. Removing an entry or item whose value is an alias, without
changing anything reached through it, is not setting through the alias and SHALL proceed.

#### Scenario: Setting one user of a shared anchor is refused
- **WHEN** the file is `defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n` and `set coder.settings.model sonnet` runs
- **THEN** the exit code is 3, stdout is empty, stderr contains `coder.settings.model`, `*d` and `--expand-alias`, the file is unchanged, and `history` gains no `cli` event

#### Scenario: Setting the alias itself is refused
- **WHEN** the same file and `set coder.settings "{model: sonnet}"` runs
- **THEN** the exit code is 3 and the file is unchanged

#### Scenario: New key below an alias is refused
- **WHEN** the same file and `set coder.settings.temperature 0.3` runs
- **THEN** the exit code is 3 and the file is unchanged

#### Scenario: Mapping VALUE that reaches into an alias is refused
- **WHEN** the same file and `set coder "{settings: {model: sonnet}}"` runs
- **THEN** the exit code is 3 and the file is unchanged

#### Scenario: Unchanged value through an alias
- **WHEN** the same file and `set coder.settings.model opus` runs
- **THEN** the exit code is 0 and no file changes

#### Scenario: Removing an alias entry
- **WHEN** the file is `defaults: &d\n  model: opus\ncoder:\n  settings: *d\n  model: x\n` and `set coder "{model: x}"` runs
- **THEN** the file becomes `defaults: &d\n  model: opus\ncoder:\n  model: x\n`

### Requirement: Expanding an alias on request
With `--expand-alias`, each alias for which the `set` would otherwise be refused (by "Refusing to set through an
alias") SHALL first be replaced by a block-style copy of its anchored node, and then `VALUE` SHALL be set in the
copy by the other rules of this capability. When an alias is replaced:
- the `*name` text, and the whitespace before it, SHALL be removed;
- the end-of-line comment `# expanded from *<name> by troupe` SHALL be put on the line of the alias's key (the
  dash's line, for a list item), with exactly two spaces before `#`. If that line already ends with a comment, the
  comment SHALL be kept and the new comment SHALL follow it, after two spaces;
- the copy SHALL reproduce the anchored node as it is written. It has the same keys and items in the same order,
  each scalar keeps its written text (quoting included), and include strings stay include strings. Aliases inside
  the anchored node stay aliases. The node's own anchors and comments are not copied. A scalar copy SHALL go on the
  key's line, before the comment. A collection copy SHALL be written in block style by the rules of "New
  collection values", one indentation level below the key or dash.

When a copy still holds an alias that the `set` reaches through, that alias SHALL be expanded the same way, with
its own comment. No other byte SHALL change: the anchor, its value and every other alias SHALL stay as they were.
Only the paths whose value changes SHALL be recorded as events (the expansion itself changes no value). With
nothing to expand, the flag SHALL have no effect. A `VALUE` equal to the current value SHALL change nothing, and no
alias SHALL be expanded. An alias inside a flow collection cannot take a block-style copy: setting through it SHALL
be refused with exit 3 even with the flag, and stderr SHALL name the alias.

#### Scenario: Giving one agent its own copy
- **WHEN** the file is `defaults: &d\n  model: opus\ncoder:\n  settings: *d\nreviewer:\n  settings: *d\n` and `set --expand-alias coder.settings.model sonnet` runs
- **THEN** the file becomes `defaults: &d\n  model: opus\ncoder:\n  settings:  # expanded from *d by troupe\n    model: sonnet\nreviewer:\n  settings: *d\n`, `get reviewer.settings.model` and `get defaults.model` print `opus\n`, and `history` gains one `set` event, `coder.settings.model` from `opus` to `sonnet`

#### Scenario: Scalar alias
- **WHEN** the file is `a: &x 1\nb: *x\n` and `set b 2 --expand-alias` runs
- **THEN** the file becomes `a: &x 1\nb: 2  # expanded from *x by troupe\n`

#### Scenario: The copy keeps written text and becomes block style
- **WHEN** the file is `d: &d {model: 'opus', limits: {tokens: 0x10}}\nc: *d\n` and `set --expand-alias c.limits.calls 5` runs
- **THEN** the file becomes `d: &d {model: 'opus', limits: {tokens: 0x10}}\nc:  # expanded from *d by troupe\n  model: 'opus'\n  limits:\n    tokens: 0x10\n    calls: 5\n`

#### Scenario: Nested aliases stay aliases
- **WHEN** the file is `t: &t [read]\nd: &d\n  model: opus\n  tools: *t\nc: *d\n` and `set --expand-alias c.model sonnet` runs
- **THEN** the file becomes `t: &t [read]\nd: &d\n  model: opus\n  tools: *t\nc:  # expanded from *d by troupe\n  model: sonnet\n  tools: *t\n`

#### Scenario: Nested alias on the way is expanded too
- **WHEN** the file is `t: &t\n  - read\nd: &d\n  tools: *t\nc: *d\n` and `set --expand-alias c.tools.1 write` runs
- **THEN** the file becomes `t: &t\n  - read\nd: &d\n  tools: *t\nc:  # expanded from *d by troupe\n  tools:  # expanded from *t by troupe\n    - read\n    - write\n`

#### Scenario: Existing comment is kept
- **WHEN** the file is `d: &d\n  model: opus\nc: *d  # shared\n` and `set --expand-alias c.model sonnet` runs
- **THEN** the file becomes `d: &d\n  model: opus\nc:  # shared  # expanded from *d by troupe\n  model: sonnet\n`

#### Scenario: Alias as a list item
- **WHEN** the file is `d: &d\n  model: opus\nagents:\n  - *d\n  - *d\n` and `set --expand-alias agents.0.model sonnet` runs
- **THEN** the file becomes `d: &d\n  model: opus\nagents:\n  -  # expanded from *d by troupe\n    model: sonnet\n  - *d\n`

#### Scenario: Alias in a flow collection
- **WHEN** the file is `d: &d {model: opus}\nc: {settings: *d}\n` and `set --expand-alias c.settings.model sonnet` runs
- **THEN** the exit code is 3, stderr contains `*d`, and the file is unchanged

#### Scenario: Nothing to expand
- **WHEN** the file is `a:\n  b: 1\n` and `set --expand-alias a.b 2` runs
- **THEN** the file becomes `a:\n  b: 2\n`, the same as without the flag

#### Scenario: Unchanged value expands nothing
- **WHEN** the file is `d: &d\n  model: opus\nc: *d\n` and `set --expand-alias c.model opus` runs
- **THEN** the exit code is 0 and no file changes

### Requirement: Merge keys are never written
`set` SHALL never add, change or delete a merge key (`<<`) entry, including its value and the aliases in it. A value
is **supplied by a merge key** when the mapping that holds the merge key does not set that key itself. A `set` SHALL
be refused with exit 3, with no file changed, when it would:
- change a value supplied by a merge key, or anything below one, including a new key below it;
- delete a value supplied by a merge key (for example, a mapping `VALUE` that leaves out a merged key);
- change, replace or delete a mapping that holds a merge key in a way that changes or removes the `<<` entry,
  including deleting an entry or item that contains it;
- expand an alias whose anchored node contains a merge key.

This holds with or without `--expand-alias`. stderr SHALL name `PATH` and the merge key, and SHALL say that merge
keys are not written, so `--expand-alias` cannot help. A mapping that holds a merge key SHALL otherwise be set like
any mapping: its own keys are changed where they are written, and a new key that no merged mapping supplies is
added after its last entry. Setting a value at the anchor that a merge key names follows "Setting a value defined at
an anchor".

#### Scenario: Own key next to a merge key
- **WHEN** the file is `base: &b\n  model: opus\n  temperature: 0.2\ncoder:\n  <<: *b\n  temperature: 0.5\n` and `set coder.temperature 0.7` runs
- **THEN** the file becomes `base: &b\n  model: opus\n  temperature: 0.2\ncoder:\n  <<: *b\n  temperature: 0.7\n`

#### Scenario: Merged value is refused
- **WHEN** the same file and `set coder.model sonnet` runs, with or without `--expand-alias`
- **THEN** the exit code is 3, stderr contains `coder.model` and `<<`, and the file is unchanged

#### Scenario: New key next to a merge key
- **WHEN** the same file and `set coder.top_p 0.9` runs
- **THEN** the file becomes `base: &b\n  model: opus\n  temperature: 0.2\ncoder:\n  <<: *b\n  temperature: 0.5\n  top_p: 0.9\n`

#### Scenario: Changing the merged anchor
- **WHEN** the same file and `set base.model sonnet` runs
- **THEN** `base.model` becomes `sonnet` in the file, `get coder.model` prints `sonnet\n`, and `history` gains `set` events for `base.model` and `coder.model`

#### Scenario: Leaving out a merged key is refused
- **WHEN** the same file and `set coder "{temperature: 0.5}"` runs
- **THEN** the exit code is 3 and the file is unchanged

#### Scenario: Replacing the mapping that holds a merge key is refused
- **WHEN** the same file and `set coder none` runs
- **THEN** the exit code is 3 and the file is unchanged
