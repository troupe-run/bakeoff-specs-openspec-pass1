# Proposal

## Why

Contract step 7 ("Remote includes and schema"). Teams want to share one configuration between theatres by URL,
so includes may now name `https://` (and `http://`) locations. troupe cannot write to a URL, so values that come
from one are read-only, and the user needs to be told which include line in their own file to change instead.

Some settings are URLs themselves (an API endpoint, a docs link). Once `https://…` strings are includes, such a
setting would be fetched and its value replaced by the response. To prevent that, the configuration can now be
described by a JSON Schema at `.troupe/troupe.schema.json`. A string the schema marks `"format": "uri"` is taken
literally, and so is any string tagged `!literal`. The schema also checks the configuration's shape: a configuration
that does not validate does not load, and `set` refuses to make one.

## What Changes

- **Remote includes**: a string starting `https://` or `http://` is an include, in scalar form and as a `$ref`. It
  is fetched when the configuration loads. A URL whose path ends `.yml`/`.yaml` is embedded as YAML, any other is
  text. A failed fetch (network error, non-2xx status, body that is not UTF-8, or invalid YAML) fails to load
  (exit 4), naming the URL. Includes inside remote content are resolved against the remote file's URL.
- **Remote values are read-only**: a `set` that would change, delete or append to anything written in remote
  content is refused with exit 3, and no file changes. stderr contains the include string exactly as it is written
  in the local file, and that file's name and line number. New keys under a remote include are still written as
  local overrides (step 5). With `--in-include`, a new key whose section lives in remote content is refused.
- **`!literal` tag**: a scalar tagged `!literal` is a string, and never an include. Today any non-core tag fails to
  load. `!literal` on a mapping or list still fails to load (exit 4).
- **Schema**: `<theatre>/.troupe/troupe.schema.json` (JSON Schema 2020-12), when present, is read on every load.
  A string whose schema, found from the root through `properties`, `items` and `additionalProperties`, has
  `"format": "uri"` is a literal, including `file:` strings. The loaded configuration (includes resolved) must
  validate against the schema, or loading fails (exit 4). A schema file that is not valid JSON, or not a valid
  2020-12 schema, also fails to load (exit 4).
- **`set` and the schema**: a `set` whose result would not validate is refused (exit 3), and no file changes.
- **BREAKING — `set` writes include-looking strings literally**: a string in `VALUE` that would be read as an
  include (`file:`, `https://`, `http://`), at a path the schema does not mark `format: uri`, is written tagged
  `!literal` (`prompt: !literal file:p.md`). The new flag `--include` writes it as an include instead, which is
  what `set prompt file:p.md` did before.
- **`show --sources`** names a remote value's source by its URL (`# from https://…`).
- **`watch`** also watches `troupe.schema.json`. It does not poll URLs: a change to remote content is picked up by
  the next reconcile (the next command, or the next local change while `watch` runs).
- README: remote includes, the schema, `!literal`, `--include`, the new exit-3 and exit-4 causes, and the
  decisions this change makes where the contract leaves a choice open. Decision 4 ("a string VALUE starting `file:`
  becomes an include") is replaced.

## Capabilities

### New Capabilities
- `config-schema`: the optional JSON Schema file, how it is read, which strings it marks as literals, and that the
  loaded configuration and every `set` result must validate against it.

### Modified Capabilities
- `config-loading`: "Includes" adds remote (`https://`/`http://`) includes and the literal exceptions (`!literal`,
  schema `format: uri`). "YAML 1.2 core-schema parsing" accepts the `!literal` tag. New requirement "Remote
  includes" covers fetching, YAML or text, failures, and includes inside remote content.
- `config-set`: "Values that are includes" is replaced: include-looking string VALUEs are written `!literal`
  unless `--include` is given. New requirement "Values from remote includes are read-only". "Scalar quoting"
  covers rewriting a `!literal` scalar.
- `config-show`: "Show sources" names the URL for values from remote includes.
- `config-cli`: "Invocation and theatre selection" lists `set … [--include]`. "Exit codes and error reporting" lists
  the new causes of exits 3 and 4.
- `config-sync`: "Watch command" also watches the schema file and says that URLs are not polled.

## Impact

- Code: a new `includes.py` decides what is an include (one place: prefix, tag, schema), and a new `remote.py`
  fetches with a per-command cache. `loader.py` passes the configuration path and the schema through expansion,
  and records each source's origin (local path or URL). `tree.py` accepts `!literal`. A new `schema_file.py`
  loads the schema and validates against it. `edit/plan.py` refuses writes into remote content. `edit/scalars.py`
  and `edit/ops.py` handle writing and keeping `!literal`. `edit/apply.py` validates the result. `render.py`
  handles URL source labels, `commands.py` watches the schema file, and `cli.py` adds `--include`.
- Dependency: `jsonschema` (Draft 2020-12 validation). Fetching uses the standard library (`urllib.request`).
- Tests: a real local HTTP server (`http.server` on 127.0.0.1) serves remote includes, and real schema files
  sit on disk. Three existing tests that `set` a `file:` string as an include gain `--include`.
- Compatibility: configurations that loaded before load the same, unless they hold `https://`/`http://` strings,
  which are now fetched (add `!literal` or a schema to keep them as strings), or `!literal` tags, which failed
  before. Scripts that relied on `set X file:…` creating an include must add `--include`. Event stores need no
  migration.
