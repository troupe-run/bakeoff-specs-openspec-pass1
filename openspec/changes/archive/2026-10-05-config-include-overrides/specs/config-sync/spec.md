# Spec Delta

## MODIFIED Requirements

### Requirement: Includes added by hand are followed
When a hand edit adds an include (in scalar or mapping form) or changes overrides, reconcile SHALL follow it like any other include: each leaf of the included content
SHALL be recorded as a `set` event (and a leaf it replaces as a `remove` event). From then on `watch` SHALL also watch
the newly included file. When an include is removed by hand, its leaves SHALL be recorded as `remove` events and
`watch` SHALL stop treating the file as part of the configuration. Reconcile compares merged values, so converting an include
between scalar and mapping form without overrides records nothing.

#### Scenario: New YAML include
- **WHEN** `watch` is running on `agents: {}\n`, `agents/tester.yaml` containing `model: t1\n` exists, and `troupe.yml` is edited to `agents:\n  tester: file:agents/tester.yaml\n`
- **THEN** within 2 seconds `set agents.tester.model` (old null, new `"t1"`) is recorded

#### Scenario: Newly included file is watched
- **WHEN** after that, `agents/tester.yaml` is edited by hand to `model: t2\n`
- **THEN** within 2 seconds `set agents.tester.model` (old `"t1"`, new `"t2"`) is recorded

#### Scenario: New include added while nothing runs
- **WHEN** no command is running, a hand edit adds `prompt: file:prompt.md`, and `show prompt` runs
- **THEN** `history` lists `set prompt` whose new value is the text of `prompt.md`

#### Scenario: Override added by hand
- **WHEN** `troupe.yml` is `coder: file:agents/coder.yaml\n` (`agents/coder.yaml` is `temperature: 0.2\n`), a hand edit changes it to `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n`, and `get coder.temperature` runs
- **THEN** `history` lists `set coder.temperature` (old 0.2, new 0.3) via `file`

#### Scenario: Converting to mapping form records nothing
- **WHEN** a hand edit changes `coder: file:agents/coder.yaml\n` to `coder:\n  $ref: file:agents/coder.yaml\n` and `show` runs
- **THEN** no event is recorded

#### Scenario: File included through $ref is watched
- **WHEN** `watch` is running on `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n` and `agents/coder.yaml` is edited by hand from `model: m1\n` to `model: m2\n`
- **THEN** within 2 seconds `set coder.model` (old `"m1"`, new `"m2"`) is recorded
