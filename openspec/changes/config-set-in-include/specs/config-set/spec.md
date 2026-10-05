# Spec Delta

## ADDED Requirements

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
