# Spec Delta

## MODIFIED Requirements

### Requirement: Show sources
`show [PATH] --sources` SHALL print the same YAML as `show [PATH]` would print for a mapping or list, and add an
end-of-line comment ` # from <file>` (one space, `#`, one space) to every line that holds a scalar value. For a scalar
written as a literal block, the comment goes on the line with the `|` indicator. Lines that hold only a key whose
value starts on the next line, the content lines of a literal block, and lines whose value is `{}` or `[]` get no
comment. `<file>` SHALL be the file the scalar is written in (for a value that an include override sets, the file holding
the override), relative to the theatre directory, with `/` separators
and no `.` segments. For a text include, `<file>` SHALL be the included file, not the file holding the `file:` string.
For a value written in remote content (see config-loading, "Remote includes"), `<file>` SHALL be the URL of the
content it is written in: the include string's URL, or for a `file:` include inside remote content, the URL it
resolves to.
When the value at `PATH` is a scalar, `--sources` SHALL print it as a one-scalar YAML document with the comment, not in
the `get` form. With or without the comments, the output SHALL read back as the same data.

#### Scenario: Sources across includes
- **WHEN** the theatre from "Whole configuration with includes" and `show --sources` is run
- **THEN** stdout is `model: claude-opus-5-5 # from .troupe/troupe.yml\nagents:\n  coder:\n    model: m1 # from .troupe/agents/coder.yaml\n    temperature: 0.2 # from .troupe/agents/coder.yaml\nprompt: | # from .troupe/prompt.md\n  Hello\n  World\ntools:\n  - read # from .troupe/troupe.yml\n  - write # from .troupe/troupe.yml\n`

#### Scenario: Sources for a section
- **WHEN** the same theatre and `show agents.coder --sources` is run
- **THEN** stdout is `model: m1 # from .troupe/agents/coder.yaml\ntemperature: 0.2 # from .troupe/agents/coder.yaml\n`

#### Scenario: Sources for a scalar
- **WHEN** the same theatre and `show model --sources` is run, or `show prompt --sources`
- **THEN** stdout is `claude-opus-5-5 # from .troupe/troupe.yml\n`, or `| # from .troupe/prompt.md\n  Hello\n  World\n` respectively

#### Scenario: Empty included YAML file
- **WHEN** `agents.coder` is `file:agents/coder.yaml`, that file is empty, and `show agents --sources` is run
- **THEN** stdout is `coder: null # from .troupe/agents/coder.yaml\n`

#### Scenario: Include through a parent directory
- **WHEN** `troupe.yml` has `a: file:sub/a.yaml`, `sub/a.yaml` has `b: file:../b.yaml`, `b.yaml` has `c: 1`, and `show --sources` is run
- **THEN** the line for `c` ends with `# from .troupe/b.yaml`

#### Scenario: config.yaml name
- **WHEN** the config file is `.troupe/troupe.yaml` containing `a: 1\n` and `show --sources` is run
- **THEN** stdout is `a: 1 # from .troupe/troupe.yaml\n`

#### Scenario: Sources with overrides
- **WHEN** `troupe.yml` is `coder:\n  $ref: file:agents/coder.yaml\n  temperature: 0.3\n`, `agents/coder.yaml` is `model: m1\ntemperature: 0.2\n`, and `show --sources` is run
- **THEN** stdout is `coder:\n  model: m1 # from .troupe/agents/coder.yaml\n  temperature: 0.3 # from .troupe/troupe.yml\n`

#### Scenario: Sources from a remote include
- **WHEN** `<base>` is the URL of a directory served over HTTP, `<base>/coder.yaml` serves `model: m1\nprompt: file:coder.md\n`, `<base>/coder.md` serves `Hi\n`, `troupe.yml` is `coder:\n  $ref: <base>/coder.yaml\n  temperature: 0.3\n`, and `show --sources` is run
- **THEN** stdout is `coder:\n  model: m1 # from <base>/coder.yaml\n  prompt: | # from <base>/coder.md\n    Hi\n  temperature: 0.3 # from .troupe/troupe.yml\n`
