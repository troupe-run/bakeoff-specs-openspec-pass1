# Design

## Context

See proposal.md for the motivation and `specs/` for the behaviour. Relevant current state (step 1):

- `commands.open_theatre()` loads the configuration, opens `ConfigStore` and imports on first use. `show`, `set` and
  `history` all start with it.
- `store.ConfigStore` wraps one eventsourcing aggregate whose state, `leaves`, is the projection `{path: scalar}`.
  `projection()` already exists but nothing reads it. Step-1 design D10 kept it unreconciled on purpose. This change
  replaces that decision: the projection now follows the files.
- `edit/apply._changes(before, after)` already computes the leaf diff a `set` records (removes in old order, then
  sets in new order, strict comparison via `schema.same`). Reconcile needs exactly the same rule.
- `loader.load()` returns `Config.files`, every file it read keyed by resolved path, with the text as read
  (`SourceFile.text`). That is the set of files `watch` has to watch, and the text it was reconciled against.
- `set` writes files with a plain `open("w")` and records events afterwards (step-1 D11). Nothing stops two
  processes from interleaving.

## Goals / Non-Goals

**Goals:**
- One reconcile function, used by `show`, `set` and `watch`, sharing `set`'s leaf diff rule.
- No reconcile can see a half-finished `set` (files written but events not yet recorded). This is the one way a
  write-back could be picked up again.
- `watch` notices every change made after its ready line, on Linux and macOS, with no new dependency.
- Each policy lives in one named place: which commands reconcile, the poll interval, the settle rule, and the lock.

**Non-Goals:**
- Locking against the user's editor. Hand edits are not coordinated, and a reconcile sees whatever is on disk when it
  runs.
- Identifying who made a change: reconcile events are plain `set`/`remove` events, as the contract says.
- Watching files that are not part of the loaded configuration (unrelated files under `.troupe/`, `events.sqlite`).
- Performance work: configurations are small, so reloading the whole configuration on each change is fine.

## Decisions

### D1. Reconcile is `diff_leaves(projection, files)` recorded in one save
Move `_changes` out of `edit/apply.py` into `leaves.py` as `diff_leaves(old: dict, new: dict) -> list[Change]`, taking
leaf dicts. `set` keeps calling it, with `leaves(to_data(...))` of the configuration before and after. New module
`sync.py` holds `reconcile(config, store) -> list[Change]`: `diff_leaves(store.projection(), leaves(to_data(config.root)))`,
then `store.record(changes)` if the list is not empty (one `save()`, atomic). With one diff rule for both, a `set` and a
hand edit with the same effect record the same events.
- "Recorded order" for removes is the projection's dict order. That is import order, with leaves first created by a
  later event appended at the end. That is the nearest thing to the old document order once the old file is gone.
- Text-include leaves compare the target's text, as `set` already does. A hand edit to `prompt.md` is a `set prompt`.
*Alternative:* diffing the old and new file texts. Rejected: we no longer have the old texts, and leaves are what
events describe.

### D2. One session per command, under a per-theatre lock
Replace `open_theatre()` with a context manager `theatre_session(theatre, *, reconcile: bool)`:
1. `find_config()`. With no config file this exits 4 before anything is created.
2. Open the `.troupe/` **directory** read-only and `fcntl.flock(fd, LOCK_EX)` (blocking). The lock is released when
   the session ends or the process dies.
3. `load()` (exit 4), open `ConfigStore`, import if needed, then reconcile if `reconcile` is true.
4. Yield `(config, store)`. The command does its work, and for `set` that includes writing the files and recording
   its events, before the lock is released.

Which commands reconcile is decided in one place, `RECONCILING_COMMANDS = {"show", "set", "watch"}` in `commands.py`.
`history` uses `reconcile=False`, but it still takes the lock because it may import.

Why this gives "the write-back produces no further events": every reconcile runs inside the lock and loads the files
at that moment. A `set` releases the lock only after its events are recorded. Any reconcile that runs after the
`set`'s writes therefore finds files equal to the projection and records nothing.
- *Lock file under `.troupe/`, rejected:* it would have to be created before the YAML is known to load, which breaks
  "no state when the configuration cannot be loaded". A directory lock creates nothing.
- *SQLite transaction as the lock, rejected:* it cannot cover the file writes, which happen outside the database.
- *Ignoring paths that troupe has just written, rejected:* a hand edit made right after a `set` would be lost. With
  the lock, the projection itself is what makes a write-back a no-op.

Reconcile events are saved in their own `save()` before the command runs, so they persist if the command then exits
3 or 5, as the import already does (step-1 decision 6).

### D3. `watch` detects changes by polling file contents
Every `POLL_INTERVAL = 0.2` s, `watch` reads its *watch set*. That is every path in the last successful load's
`Config.files`, plus both config-file candidates (`troupe.yml`, `troupe.yaml`). It compares what it reads with the
*baseline*: the text each file had when it was loaded (`SourceFile.text`) and whether each candidate existed. A file
that is missing, unreadable or undecodable counts as different. Taking the baseline from the loader's own texts,
rather than from a separate read, means no edit can slip in between "read for reconcile" and "start watching".

When the watch set differs from the baseline and reads the same on two consecutive polls (the *settle rule*,
`SETTLE_POLLS = 2`), `watch` opens a session (lock, load, reconcile) and takes the new baseline from that load.
Includes added by a hand edit then join the watch set, and removed ones leave it. Worst-case latency is about
POLL_INTERVAL × (SETTLE_POLLS + 1) plus one load: well under the 2 s limit.

The settle rule matters because an editor that truncates and then rewrites would otherwise be caught at the moment
the file is empty, and an empty file is a valid (empty) configuration. That would record a `remove` for every leaf
followed by a `set` for every leaf.
- *watchdog / inotify / FSEvents, rejected:* a new dependency with different behaviour on each platform. Editors
  that save by rename also need directory watches and re-arming. Polling by content handles in-place writes,
  renames, creation and deletion the same way on both OSes. Configurations are a few small files.
- *mtime polling, rejected:* coarse mtime resolution on some filesystems can hide a quick second write.

### D4. Ready line and startup
`watch` installs its signal handlers, runs one session (lock, load, import, reconcile), takes the baseline from that
load, then writes `watching <dir>\n` to stdout and flushes. Every change after the line differs from the baseline, so
it will be seen. `<dir>` is the theatre as given (`--theatre`, else `TROUPE_THEATRE`), or `os.getcwd()` when neither
is set. It is not `resolve()`d, because on macOS that would turn `/var/…` into `/private/var/…` and the line would no
longer match what the caller passed. This mapping lives in `cli.py` next to the existing theatre default. If the first
load fails, `watch` exits 4 through the normal error path before printing anything.

### D5. Stopping
SIGINT and SIGTERM handlers only set a `threading.Event`. The loop waits on that event with
`stop.wait(POLL_INTERVAL)`, so it wakes at once. The flag is checked only between cycles, so a reconcile in progress
finishes (it holds the lock and saves atomically). Then `watch` returns, and `main` exits 0 without writing to stderr.
Replacing Python's default SIGINT handler also means no `KeyboardInterrupt` traceback.

### D6. Load failures while watching
A `LoadError` raised during a watch cycle is caught: nothing is recorded, `troupe: <message>` goes to stderr unless it
equals the last message printed, and the loop goes on. While the configuration does not load, there is no
`Config.files` to watch. So every poll retries the session (lock, load) until one succeeds. That is cheap, and it also
catches a missing include target being created. Once a load succeeds, the remembered error is cleared and normal
polling resumes. Any other exception ends `watch` through `main`'s normal error handling. This is conservative:
an unexpected failure stops the watch rather than letting it run and record events silently.

### D7. CLI shape
`watch` is a new subparser with no positional arguments. `cli.run` currently returns the text to print. `watch`
cannot work that way, so it writes its line itself and blocks. `run` calls `commands.watch(theatre, display,
sys.stdout)` and returns `""`. Errors keep flowing through `TroupeError` → exit code in `main`, the one place exit
codes are mapped.

### D8. The store in a long-running process
`watch` opens one `ConfigStore` for its whole life. The eventsourcing `Application` is created without an aggregate
cache, so `repository.get()` rebuilds the projection from the database each time and sees events that other processes
recorded. A test checks this (a `set` while `watch` runs, then a hand edit, must give an `old` equal to the `set`'s
new value). If a cache is ever turned on, reconcile must reopen the store.

### D9. Testing
- Reconcile through the in-process CLI (`conftest.Theatre.run`): hand-edit with `Theatre.write`, run
  `show`/`set`/`history`, and compare the exact event lists. The step-1 test `test_hand_edits_are_not_reconciled` is
  replaced by a test showing that `history` does not reconcile but `show` does.
- `watch` through real subprocesses: `[sys.executable, "-m", "troupe.cli", "config", "watch", "--theatre", dir]`,
  read stdout until the ready line (with a timeout), make the edit, then poll `history` until a deadline of 2 s
  measured from the edit. Assertions that nothing happened wait 2.5 s. Signals are sent with `Popen.send_signal`, and
  the test then checks the exit code 0, the exact stdout and an empty stderr. One smoke test runs `watch` through
  `uv run`, as the contract requires, which also proves that `uv` passes the signal on.
- Lock: a test holds `flock` on `.troupe/` from the test process and checks that `set` blocks until it is released.
  A second test checks that `set` while `watch` runs adds exactly one event.

## Risks / Trade-offs

- [`uv run` does not pass SIGTERM/SIGINT on to the child] → the uv smoke test catches this. Current uv versions do
  forward both signals.
- [`flock` on a directory fd is not supported on some filesystem, such as certain network mounts] → `flock` raises
  `OSError`, which becomes a clear error naming `.troupe/`. Only local Linux and macOS filesystems are in scope.
- [An editor writes in several steps over more than ~0.4 s] → an intermediate state can be reconciled, which adds
  extra but correct events (each one matches what was on disk). The settle rule makes this unlikely, and it never
  loses data.
- [A blocked lock: a hung `set` stalls `watch`] → acceptable, since `set` is short. The lock dies with the process,
  so a crash cannot leave a stale lock.
- [Polling costs a little CPU while idle] → about 5 small reads per second. No performance targets apply.
- [Reconcile events added by `set`/`show` surprise anyone who relied on step-1 "hand edits are not recorded"] → this
  is the step-2 contract. The README and specs are updated in the same change.

## Migration Plan

Existing `events.sqlite` files stay valid: the event types do not change. The first reconciling command after the
upgrade records any hand edits made since import as `set`/`remove` events. To roll back, use the step-1 code. It
reads the same database, because reconcile records only event types that step 1 already defines.

## Decisions on points the contract leaves open (for product-owner review)

1. `watch` on an unloadable theatre at startup exits 4 without printing the line. This matches every other command.
2. A load failure *while* watching does not stop `watch`. It reports once on stderr and resumes when the files load
   again (an editor mid-save must not kill the watcher).
3. `watch` writes nothing to stdout except the ready line. Events go to the store, and `history` shows them.
4. `<dir>` in the ready line is the theatre as given, not resolved. When no theatre is given, it is the absolute
   current directory.
5. `history` still imports on a theatre's first command (step-1 behaviour). Importing is not reconciling.
6. Reconcile events persist even if the command then fails (exit 3 or 5), as the import already does.
7. Removes found by reconcile are listed in recorded order. Sets are listed in the files' document order.
8. Commands against one theatre are serialised by a lock on the `.troupe/` directory, so a second command waits
   rather than failing.
