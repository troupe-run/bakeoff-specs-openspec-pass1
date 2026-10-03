# Proposal

## Why

`show PATH` only prints scalars. A mapping or list exits 5, so people cannot look at a whole agent, a section or the
whole configuration as troupe sees it, with includes followed. Nor can they find out which file a value comes from.
They need both to understand configurations that are split across included files. Step 3 splits reading in two:
`get` for one value, which keeps the step-1 behaviour scripts rely on, and `show` for anything, printed as YAML,
with `--sources` to say where each value comes from.

## What Changes

- New subcommand `troupe config get PATH`. It prints a scalar exactly as `show PATH` did in steps 1 and 2. On a
  mapping or list it exits 5, and stderr names the path and mentions `config show`. Missing paths exit 5 as before.
- **BREAKING**: `troupe config show [PATH] [--sources]` no longer refuses collections.
  - A scalar (including a text include) is printed as `get` prints it.
  - A mapping or list is printed as block-style YAML with includes resolved. The value of a text include is printed
    as a literal block scalar (`|`).
  - With `PATH` omitted, the whole configuration is printed.
  - Missing paths still exit 5, naming the path.
- `--sources` adds an end-of-line comment `# from <file>` to every output line that holds a scalar. `<file>` is the
  file the scalar comes from, relative to the theatre directory, with `/` separators. A text include's value comes
  from the included file, not from the file holding the `file:` string.
- `get` reconciles before it reads, as `show` does. It joins the commands that reconcile first.

## Capabilities

### New Capabilities
- `config-get`: reading one scalar value with `get PATH`. It takes over the step-1 `show PATH` requirements, plus
  the rule that a collection exits 5 with a pointer to `config show`.

### Modified Capabilities
- `config-show`: `show` takes an optional `PATH`, prints collections and the whole configuration as YAML, and adds
  `--sources`. The requirement "Show refuses collections and missing paths" is removed. Missing paths still exit 5.
- `config-cli`: `get` joins the list of subcommands. The rule that commands leave user files untouched now covers
  `get` and `show --sources`.
- `config-sync`: `get` joins `show`, `set` and `watch` as a command that reconciles first.

## Impact

- Code:
  - `cli.py`: a `get` subparser, `show` with an optional `path` and a `--sources` flag.
  - `commands.py`: `get` and `show` share one path lookup. `"get"` is added to `RECONCILING_COMMANDS`.
  - A new module that renders a configuration subtree as YAML, optionally with sources. It has no new dependencies.
- Tests: the existing `tests/test_show.py` scalar tests move to `get` and still pass. New tests cover YAML output,
  output that reads back to the same data, `--sources` comments, and `get` on collections. CLI and smoke tests that
  call `show` on scalars stay valid. README updated.
- No change to state, events or write-back.
