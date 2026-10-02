# Spec Delta

## Purpose

Lets a user change one setting from the command line and have the change written back into the hand-edited file
that holds it. The file diff contains only the bytes the change requires, so comments, quoting and layout elsewhere
stay exactly as the user wrote them.

In the scenarios below, file contents are written with `\n` for a line feed and `⏎` where a value contains a newline.

## ADDED Requirements

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
An existing value SHALL be changed in the file that contains it, including files reached through YAML includes.
When `PATH` names a text include, the target file's content SHALL become `VALUE` exactly, except that if the target
file contains a CRLF line ending, every LF in `VALUE` not already preceded by CR SHALL be written as CRLF. A non-string
`VALUE` for a text include SHALL be refused with exit 3.

#### Scenario: Value inside an included file
- **WHEN** `agents.coder` is `file:agents/coder.yaml` and `set agents.coder.model m2` runs
- **THEN** only `agents/coder.yaml` changes, and only the model's value bytes change

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
Replacing the value at a path whose whole value comes from a YAML include (the path names the include string
itself) SHALL be refused with exit 3, naming the path, and no file SHALL change. This applies whatever the new
value is, and also when a `set` on an ancestor would change or delete such a value. A `set` on an ancestor that
leaves the included value equal is allowed and does not touch the included file.

#### Scenario: Replacing an included mapping
- **WHEN** `agents.coder` is `file:agents/coder.yaml` and `set agents.coder "{model: x}"` runs
- **THEN** the exit code is 3, stderr names `agents.coder`, and no file changes

#### Scenario: Changing an include through its parent
- **WHEN** `agents.coder` is `file:agents/coder.yaml` and `set agents VALUE` runs where VALUE's `coder` differs from the included content, or omits `coder`
- **THEN** the exit code is 3 and no file changes

#### Scenario: Replacing an included scalar
- **WHEN** `limit` is `file:limit.yaml`, which contains `5`, and `set limit 6` runs
- **THEN** the exit code is 3 and no file changes

### Requirement: Setting a collection value
When both the existing value and `VALUE` are mappings, or both are lists, `set` SHALL apply the difference: keys
(or indexes) present in both are set recursively, so unchanged leaves keep their bytes, including across YAML include
boundaries that the include rules allow. New keys or items are added under the new-entry rules, and keys (or trailing items) missing from `VALUE`
are deleted. Deleting a block entry SHALL remove the lines from the entry's first line through the end of its value,
including that value's end-of-line comment, and SHALL keep comment lines before and after it. Deleting a flow entry
SHALL remove the entry and one adjacent separator. In every other case the existing node SHALL be replaced as a whole.

#### Scenario: Partial mapping update keeps unchanged bytes
- **WHEN** the file is `a:\n  b: 1  # keep\n  c: 2\n` and `set a "{b: 1, c: 3}"` runs
- **THEN** the file becomes `a:\n  b: 1  # keep\n  c: 3\n`

#### Scenario: Key removed by a mapping value
- **WHEN** the file is `a:\n  b: 1\n  c: 2\n` and `set a "{b: 1}"` runs
- **THEN** the file becomes `a:\n  b: 1\n`

### Requirement: Creating new keys
A `PATH` whose final key does not exist SHALL be written into the file containing the deepest existing ancestor
mapping of `PATH`, with any missing intermediate mappings created there. Descending into an existing scalar
(including null) or a text include SHALL exit 5. A digit-only segment that would need a missing intermediate created,
or that is applied to a mapping, SHALL exit 5. An empty (or comment-only) file SHALL be treated as an empty block
mapping at column 0.

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
- **WHEN** `agents.coder` is `file:agents/coder.yaml` (a mapping) and `set agents.coder.temperature 0.2` runs
- **THEN** only `agents/coder.yaml` changes, gaining `temperature: 0.2`

#### Scenario: Parent is a scalar
- **WHEN** `model` is `m` and `set model.x 1` runs
- **THEN** the exit code is 5 and no file changes

#### Scenario: Parent is null
- **WHEN** the file is `agents:\n` and `set agents.coder x` runs
- **THEN** the exit code is 5 and no file changes

### Requirement: Appending to lists
A `PATH` whose final segment is an index equal to the list's length SHALL append `VALUE` to the list. A larger
index SHALL exit 5.

#### Scenario: Append to a block list
- **WHEN** the file is `tools:\n  - a\n  - b\n` and `set tools.2 c` runs
- **THEN** the file becomes `tools:\n  - a\n  - b\n  - c\n`

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
