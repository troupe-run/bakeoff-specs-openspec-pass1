# Design

## Context

See proposal.md for the motivation and `specs/` for the behaviour. Today:

- Whether a string is an include is decided in one function, `tree.include_target(node)`: an untagged string
  starting `file:`. It knows nothing of where the node sits. It is used by `loader._Loader._expand`,
  `loader._Loader.include_mapping` and `overrides.ref_entry`, and `ref_entry` is also used by `edit/apply.py` on
  mappings as written.
- `loader._Loader` keeps every file it reads in `files: dict[Path, SourceFile]`, keyed by resolved path. That dict
  is the basis of the `set` overlay and write-back (`apply.compute_set` builds `texts` from `config.files` and writes
  only keys of it) and of `watch`'s baseline (`commands._baseline`). Includes resolve with `base / target`, where
  `base` is a directory `Path`, and cycles are found with a stack of resolved paths.
- `compute_set` reloads the configuration (`load(theatre, overlay=texts)`) after every operation and finally checks
  that the result reads back as intended (`_matches`). Any `LoadError` on reload becomes exit 3 in `_reload`.
- The builder (`tree._Builder.scalar`) refuses any non-core tag (`resolve_tagged` raises). `ScalarNode.tagged`
  records that a tag was present, `ops.replace` refuses to rewrite tagged scalars, and `blocks.copy_value` re-renders
  a tagged scalar from its value, which drops the tag.
- `schema.same` compares with `type(a) is type(b)`.
- Tests run the CLI in-process (`conftest.run` calls `cli.main`), so a test process can serve HTTP itself.

## Goals / Non-Goals

**Goals:**
- One place decides "this string is an include" (prefix, tag, schema), and one place decides "this file cannot
  be written" (remote). Every other module asks them.
- Remote content can never be written. Write-back only touches files in `Config.files`, and remote sources never
  go there.
- A command sees one snapshot of each URL, however many times `set` reloads.
- The read-back check stays the last line of defence: anything this design misses becomes exit 3, never a wrong
  file.

**Non-Goals:**
- Caching remote content between commands, offline mode, authentication headers, proxies beyond what
  `urllib` reads from the environment.
- Asserting `format` (or any other annotation) during validation, and fetching schemas or `$ref` targets.
- Following `$ref`, `allOf`/`anyOf`/`oneOf`, `if`/`then`, `prefixItems` or `patternProperties` to find
  `format: uri` (the contract names only `properties`, `items` and `additionalProperties`).
- Writing to remote content, or copying remote values into local overrides automatically.

## Decisions

### D1. `includes.py`: the one place that decides what is an include
A new module holds the prefixes (`file:`, `https://`, `http://`), `LITERAL_TAG = "!literal"`, and:
- `include_target(node: ScalarNode) -> str | None`: the include string's target if `node` is an include. A node
  is not one when it is tagged (any tag, `!literal` included), when the loader marked it a literal (D3), or when its
  value is not a string with one of the prefixes. `file:` gives the path after the prefix, and a URL gives itself.
- `looks_like_include(value: str) -> bool`: the prefix test alone, used by `set` (D7).
- `Location = Path | str` (a local directory, or the URL of remote content), with `resolve(base, target)`. A URL
  target is absolute. A `file:` target under a local base is `base / target`, and under a URL base it is
  `urllib.parse.urljoin(base_url, target)`. So remote content can never name a local file.
- `is_yaml(location)`: `.yml`/`.yaml` suffix, using the URL's path (no query or fragment) for a URL.

`tree.include_target` and `INCLUDE_PREFIX` move here, and `overrides.ref_entry` and the loader import from here.

*Alternative*: let the loader pass a predicate everywhere. Rejected: `ref_entry` is also called by `apply.py` on
trees long after loading, so the decision has to be readable from the node itself (D3).

### D2. Remote sources: `SourceFile.url`, `Config.remote`, and a per-command `Fetcher`
- `SourceFile` gains `url: str | None = None` and a `name` property (the URL, or `str(path)`). Error messages that
  name a source (`tree._Builder.fail`, `parse_events`, loader messages) use `name`. For remote content `path` is
  `Path(url-path)`, kept only so existing code that reads `path` stays typed. Nothing writes to it, since remote
  sources are never in `Config.files`.
- `SourceFile` also gains `included_by: ScalarNode | None`, the include string that first brought it in (set
  for remote sources). D5 follows this chain to the include written in a local file.
- `remote.py` holds `Fetcher`. `fetch(url) -> SourceFile` uses `urllib.request` with a 30-second timeout and
  `User-Agent: troupe`, follows redirects only to `http`/`https` (a custom redirect handler, since `urllib` would
  also follow `ftp`), requires a 2xx status, and decodes the body as strict UTF-8 with no newline translation.
  Every failure raises `LoadError` naming the URL. Results are cached by URL for the `Fetcher`'s lifetime.
- `load(theatre, overlay=None, fetcher=None, *, validate=True)`. `Config` gains `remote: dict[str, SourceFile]`,
  `fetcher: Fetcher` and `schema: Schema | None`. `compute_set._reload` passes `config.fetcher`, so every reload in
  one `set` sees the same remote bytes and fetches nothing new except URLs a `--include` adds. `theatre_session`
  creates a fresh `Fetcher` for each session, so each command, and each `watch` reconcile, fetches afresh.
- The loader's cycle stack holds `Path | str` keys (resolved path or URL).

*Alternative*: put remote sources into `Config.files` under a synthetic key. Rejected: the overlay, write-back and
watch baseline would all need a "but not remote" filter, and forgetting one would mean writing a URL's bytes to
disk. Keeping them out of `files` makes that impossible by construction.

### D3. The schema, and literal marking during expansion
`schema_file.py` holds `SCHEMA_NAME = "troupe.schema.json"` and `Schema`:
- `Schema.read(state_dir) -> Schema | None` reads strict UTF-8 JSON. It runs `Draft202012Validator.check_schema`,
  and it refuses any string `$ref`/`$dynamicRef` that does not start with `#` (found by walking the schema's
  keyword positions, so a property *named* `$ref` is not mistaken for one). A `referencing.Registry` whose
  `retrieve` raises keeps anything from being fetched. Every failure is a `LoadError` naming the schema file.
- `Schema.at(path) -> dict | bool | None` walks `properties` → `additionalProperties` (mapping keys) and `items`
  (list indexes) only, the rule in the config-schema spec. `Schema.is_uri(path)` is `at(path)` having
  `"format": "uri"`.
- `Schema.validate(data)` uses `Draft202012Validator` with no format checker. On failure it raises `LoadError`
  naming the schema file and the dotted path of `jsonschema.exceptions.best_match`'s error.

`_Loader._expand` gains a `path: Path` (configuration path) argument. On a `ScalarNode` that looks like an
include (D1), if `schema.is_uri(path)` it sets `node.literal = True` (a new `ScalarNode` field) and returns the node.
Otherwise it includes it. For a mapping, `ref_entry` is decided after the `$ref` value at `(*path, "$ref")` has been
marked. Included roots continue the including path, and overrides use their own path. The memo by node identity
(anchors) means that an anchored node is judged at the first path that reaches it, which is where it is written,
since an anchor precedes its aliases in the file. `load` reads the schema first, expands, then (with
`validate=True`) validates `to_data(root)`.

Validation is a separate step, so `compute_set` reloads with `validate=False` between operations: an intermediate
state of a multi-operation `set` may be invalid even when the result is valid. It validates once, on the final
tree, before writing, and turns a failure into `WriteRefused` naming `PATH` and the schema file.

*Alternative*: decide literals after loading by walking the finished tree. Rejected: by then the string has
already been included (and possibly fetched), and a failed fetch of a URL the schema marks as a literal would fail
loading.

### D4. `!literal` in the tree
`tree._Builder.scalar` accepts the tag `!literal` as `!!str` (value = the text). `ScalarNode` gains `tag: str | None`,
the tag as written, with `tagged` kept as `tag is not None`. `!literal` on a mapping or sequence start event fails in
`collection_tag_ok`, as every non-core collection tag does today. Any other non-core scalar tag still fails in
`resolve_tagged`.

### D5. Remote content is read-only: one check where edits are made
`remote.refuse_remote(src: SourceFile, path) -> None` raises `RemoteWrite` (a `WriteRefused`, exit 3) when
`src.url` is set. Its message names `PATH`, the URL, and the outermost include: it follows `included_by` up while
the including string's file is remote. It quotes that include string's source text
(`file.text[string.start:string.end]`, quotes included), the local file (relative to the theatre, like
`show --sources`) and its line, and says to change that include line or add an override for new keys.

It is called in `apply._apply`. Every `FileEdits` an operation produces, and the `WriteText` target and
`ExpandAlias` file, is checked before any text changes. That covers replace, delete (every layer
`_delete_key` touches), append, add-key (including `--in-include`), text includes, alias expansion, and an
override whose include string itself lives in remote content.

Where new keys go: `plan.new_key_target` skips includes whose reference (`include.string.file`) is remote when it
picks the nearest include to override, so the override lands next to the nearest include written in a local file.
`apply._add_override` then walks the overrides from there, as it already does for deeper paths.

*Alternative*: check in the planner, op by op. Rejected: the planner does not know which layer a delete or add will
touch. That is decided in `apply`, and checking where the edit is made cannot miss a case.

### D6. Writing `!literal`
`edit/scalars.py` gets `Literal(str)`, a marker subclass meaning "write this string tagged `!literal`". The scalar
writers (`render_scalar`, and `blocks.literal` / `render_value` for block scalars) write `!literal ` in front of
the text they would write for the plain string. `ops.replace` on a scalar whose `tag` is `!literal`, given a
string, rewrites only the text after the tag and the space that follows it, writing the string untagged (a
`Literal` there does not add a second tag). Given a non-string, it replaces the whole span, tag included. Any other
tag stays refused. `blocks.copy_value` copies a tagged single-line scalar from its source text (tag included), so
an `--expand-alias` copy of `&x !literal file:y` stays a literal.

`schema.same` treats `str` subclasses as `str` (a one-line change in the one place equality is decided), so a
`Literal` VALUE equals the string it reads back as, in no-op checks, `_matches` and events. `overrides.is_bare`
rejects a `Literal`: without `--include`, setting an include's own string means a literal string, not "the same
include".

### D7. Deciding which VALUE strings become literals
In `compute_set`, before planning, `mark_literals(value, path, schema, include)` walks `VALUE` with each string's
own path. Without `--include`, every include-looking string at a path that `schema.is_uri` does not mark becomes a
`Literal`. With `--include`, an include-looking string at a URI-marked path raises `WriteRefused` naming that path,
and nothing is marked. A string written into a text include goes through `WriteText` as raw text, so a `Literal`
there is just its text.

*Alternative*: apply the rule only to a scalar `VALUE`, as the contract's sentence reads literally. Rejected: then
`set links "[https://…]"` would silently become a fetch, which is exactly what the change exists to prevent. The
per-path rule gives the same answer for a scalar `VALUE` and extends it to strings nested inside a collection.

### D8. CLI, `show --sources`, `watch`
- `cli.py` adds `--include` (`store_true`) to `set`, passed through `commands.set_value` to `compute_set`.
- `render.source_label` returns `file.url` for remote sources.
- `commands._baseline` adds `.troupe/troupe.schema.json` (as `None` when absent), as it does for both config
  names, so creating, editing or deleting the schema triggers a reconcile. Remote sources are not in `files`, so
  they are not polled.

### D9. Dependency
`jsonschema` (with its `referencing` dependency) for draft 2020-12, added with `uv add 'jsonschema>=4.18,<5'`.
`types-jsonschema` goes into the dev group so that `mypy --strict` stays clean. If the stubs lag the library, the
few calls are wrapped in `schema_file.py`, the only module that imports it. Fetching uses the standard library.

*Alternative*: write a validator by hand. Rejected: draft 2020-12 is large, and "validate against the schema" means
the whole of it.

### D10. Points the contract leaves open, and what we chose
These go into the README decisions list, with their reasons:
- **`file:` inside remote content resolves against its URL.** The step-1 rule is "relative to the file containing
  it", and that file is remote. Reading a local file named by remote content would let a shared config read the
  user's disk.
- **Every include-looking string in VALUE is literal unless `--include`**, nested ones included (D7).
- **`--include` at a URI-marked path is refused (exit 3)**, rather than silently writing a literal the user did not
  ask for.
- **Setting an include to its own string without `--include` is refused (exit 3)**: it asks for a literal string in
  place of an include. With `--include` it is a no-op, as before.
- **A `!literal` tag is kept when its scalar becomes another string**, the smallest diff, and dropped for a
  non-string, which it would otherwise turn into a string.
- **The error names the outermost include written in a local file**: that is the only line the user can change.
- **New keys under nested remote includes become overrides of the nearest include written locally**, deep enough
  to reach the key, since the nearer include's reference is itself remote.
- **Deleting a remotely set key is refused even if an override also sets it**: removing only the override would
  bring the remote value back (decision 29).
- **`show --sources` names a remote value by its URL.**
- **Fetching**: 30-second timeout, redirects followed to http/https only, 2xx required, UTF-8 required, no
  cache between commands, at most one fetch per URL per command.
- **`watch` does not poll URLs.** It watches the schema file. Remote changes are recorded at the next reconcile, as
  hand edits.
- **Schema `$schema` is ignored (always 2020-12), `format` is not asserted, and non-local `$ref` is refused**: the
  contract names 2020-12, the draft makes `format` an annotation by default, and fetching a schema would add a
  second, unannounced network dependency.
- **A node reached through an alias is judged as a literal or not at its anchor's path.** That is where it is
  written, and it is read once.
- **`$ref` of a mapping-form include is looked up at `<path>.$ref`**: that is where the string is written. The
  mapping's own path describes the merged value.

## Risks / Trade-offs

- [Every command now needs the network when the configuration has remote includes, and a flaky server makes
  `get` fail with exit 4] → The contract says a failed fetch is exit 4. The message names the URL. Users can
  vendor the file and switch to `file:`.
- [Strings that start `https://` in existing configurations become includes on upgrade, and are fetched] → Called
  out as a compatibility note in the README with the fix (`!literal` or a schema). A string whose fetch fails
  shows up as exit 4 naming that URL, so it cannot go unnoticed.
- [BREAKING: `set X file:…` no longer creates an include] → `--include` restores it. The written `!literal` tag is
  visible in the diff, and reads back as the string the user typed, so no data is lost.
- [Test servers and timeouts make tests slow or flaky] → Tests use a `ThreadingHTTPServer` on `127.0.0.1` with a
  random port, and "unreachable" uses a port that was bound and then closed, which fails fast with connection
  refused.
- [Reconcile records remote changes as `file` events with an unknown actor, so history cannot tell them from local
  hand edits] → Accepted for this step. Lineage already says troupe cannot know who edited a file.
- [`jsonschema`'s best_match may name a different failing path than a user expects when several fail] → The spec
  asks for "a value that fails". The message names the schema file, so the user can run their own validator.

## Migration Plan

No data migration. Event stores are unchanged. Going back to step-6 code: configurations with `!literal` tags or
remote includes fail to load (exit 4), and a `.troupe/troupe.schema.json` is ignored.
