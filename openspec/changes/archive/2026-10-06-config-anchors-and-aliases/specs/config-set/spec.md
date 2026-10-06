# Spec Delta

## ADDED Requirements

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
