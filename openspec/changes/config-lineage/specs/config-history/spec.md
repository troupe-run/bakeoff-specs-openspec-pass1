# Spec Delta

## MODIFIED Requirements

### Requirement: Listing history
`troupe config history [PATH]` SHALL print events as JSON Lines, oldest first, one compact JSON object per line. Each
object SHALL have at least `seq` (an integer from 1, increasing by 1), `op` (`import`, `set` or `remove`), `path`
(dotted), `old` and `new` (JSON values: strings, numbers, booleans, null), and the lineage fields `actor`, `via`, `at`,
`reason` and `change` defined in config-lineage. Non-finite floats SHALL be written as the strings `".inf"`, `"-.inf"`
and `".nan"`. With `PATH`, only events whose path equals `PATH` or starts with `PATH.` SHALL be printed, keeping their
original `seq` and lineage. A `PATH` that matches nothing SHALL print nothing and exit 0.

#### Scenario: Filter by prefix
- **WHEN** the events have paths `agents.coder.model`, `agents.coderx`, and `model`, and `history agents.coder` runs
- **THEN** only the `agents.coder.model` event is printed

#### Scenario: Unicode and multi-line values
- **WHEN** a leaf's value is `é⏎`
- **THEN** its event line is valid JSON whose `new` decodes to `é⏎`, and the line contains no raw newline

#### Scenario: Every line carries lineage
- **WHEN** a theatre has import, reconciled and `set` events and `history` runs, with or without a `PATH`
- **THEN** every printed object has the keys `seq`, `op`, `path`, `old`, `new`, `actor`, `via`, `at`, `reason` and `change`
