# config-show Specification

## Purpose

Lets a user read any part of a theatre's configuration, from a single value to the whole configuration, with
includes resolved, and see which file each value comes from.

## Requirements

### Requirement: Show a scalar value
`troupe config show [PATH] [--sources]` SHALL print the value at `PATH`, or the whole configuration when `PATH` is
omitted. Without `--sources`, a scalar SHALL be printed exactly as `get PATH` prints it, and a text include SHALL count
as a string scalar. The value SHALL reflect the current contents of the configuration files, including edits made by
hand since the last command. `show` SHALL exit 5, naming the path, when `PATH` does not exist, when an index is out of
range, or when a segment would have to descend into a scalar.

#### Scenario: Plain scalar
- **WHEN** the config is `model: claude-opus-5-5\n` and `show model` is run
- **THEN** stdout is `claude-opus-5-5\n` and the exit code is 0

#### Scenario: Value through a YAML include
- **WHEN** `agents.coder` is `file:agents/coder.yaml`, which contains `temperature: 0.2`
- **THEN** `show agents.coder.temperature` prints `0.2\n`

#### Scenario: Text include as a scalar
- **WHEN** `prompt` is `file:prompt.md`, which contains `Hello\nWorld\n`, and `show prompt` is run
- **THEN** stdout is `Hello\nWorld\n`, the same as `get prompt`

#### Scenario: Hand edit is visible
- **WHEN** a command has already run, the user then edits `model: a` to `model: b` by hand, and `show model` runs
- **THEN** stdout is `b\n`

#### Scenario: Missing key
- **WHEN** `show nope` is run and there is no `nope` key
- **THEN** the exit code is 5, stdout is empty, and stderr names `nope`

#### Scenario: Descending into a scalar
- **WHEN** `model` is a string and `show model.x` is run
- **THEN** the exit code is 5 and stderr names `model.x`

### Requirement: Show collections as YAML
When the value at `PATH` (or, with `PATH` omitted, the whole configuration) is a mapping or list, `show` SHALL print
it as one YAML document in block style, with includes resolved: the content of an included YAML file appears in place
of its `file:` string. The output SHALL satisfy all of the following:
- Read as YAML 1.2 with the core schema, it gives exactly the same data as the value at `PATH`, with the same types.
- Mapping keys appear in the order they have in the files, and list items in their order.
- Nesting is indented by two spaces. List items are written `- item`, and a list or mapping that is a mapping's value
  starts on the line after its key.
- Non-string scalars are written as `null`, `true`/`false`, decimal integers, and floats in Python `repr()` form, with
  `.inf`, `-.inf` and `.nan` for the special values.
- A string is written plain when the plain form reads back as the same string. Otherwise it is single-quoted when
  single quotes can hold it, and double-quoted when they cannot. This is the rule `set` uses for new values.
- A text include's value is written as a literal block scalar (`|`, `|-` or `|+`, as its trailing line breaks require),
  even when it is one line or empty. Any other string that contains a line break is written the same way. The only
  exception is a string that a literal block cannot hold exactly (such as one containing a carriage return or a
  control character). That string is written double-quoted.
- An empty mapping is written `{}` and an empty list `[]`.
The output SHALL end with a single line break, and nothing SHALL be written to stderr.

#### Scenario: Whole configuration with includes
- **WHEN** `troupe.yml` is `model: claude-opus-5-5\nagents:\n  coder: file:agents/coder.yaml\nprompt: file:prompt.md\ntools: [read, write]\n`, `agents/coder.yaml` is `model: m1\ntemperature: 0.2\n`, `prompt.md` is `Hello\nWorld\n`, and `show` is run
- **THEN** the exit code is 0 and stdout is `model: claude-opus-5-5\nagents:\n  coder:\n    model: m1\n    temperature: 0.2\nprompt: |\n  Hello\n  World\ntools:\n  - read\n  - write\n`

#### Scenario: A section
- **WHEN** the same theatre and `show agents` is run
- **THEN** stdout is `coder:\n  model: m1\n  temperature: 0.2\n`

#### Scenario: A list
- **WHEN** the same theatre and `show tools` is run
- **THEN** stdout is `- read\n- write\n`

#### Scenario: List of mappings
- **WHEN** the config is `steps:\n  - {name: a, n: 1}\n  - name: b\n` and `show steps` is run
- **THEN** stdout is `- name: a\n  n: 1\n- name: b\n`

#### Scenario: One-line text include
- **WHEN** the config is `p: file:p.txt\n`, `p.txt` contains `no newline` (no line break), and `show` is run
- **THEN** stdout is `p: |-\n  no newline\n`

#### Scenario: Strings that need quoting
- **WHEN** the config is `a: "true"\nb: '0.2'\nc: ""\nd: "x: y"\n` and `show` is run
- **THEN** stdout is `a: 'true'\nb: '0.2'\nc: ''\nd: 'x: y'\n`

#### Scenario: Scalar types are kept
- **WHEN** the config is `a: 0x1F\nb: 1e3\nc: ~\nd: .inf\ne: TRUE\n` and `show` is run
- **THEN** stdout is `a: 31\nb: 1000.0\nc: null\nd: .inf\ne: true\n`

#### Scenario: Empty collections and empty configuration
- **WHEN** the config is `agents: {}\ntools: []\n` and `show` is run, or the config file is empty and `show` is run
- **THEN** stdout is `agents: {}\ntools: []\n`, or `{}\n` respectively

#### Scenario: Output reads back as the same data
- **WHEN** `show` is run on any configuration that loads, including multi-line strings, special floats, nested lists and strings that look like other types
- **THEN** reading stdout as YAML 1.2 core gives data equal to the loaded configuration, with the same types

### Requirement: Show sources
`show [PATH] --sources` SHALL print the same YAML as `show [PATH]` would print for a mapping or list, and add an
end-of-line comment ` # from <file>` (one space, `#`, one space) to every line that holds a scalar value. For a scalar
written as a literal block, the comment goes on the line with the `|` indicator. Lines that hold only a key whose
value starts on the next line, the content lines of a literal block, and lines whose value is `{}` or `[]` get no
comment. `<file>` SHALL be the file the scalar is written in, relative to the theatre directory, with `/` separators
and no `.` segments. For a text include, `<file>` SHALL be the included file, not the file holding the `file:` string.
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
