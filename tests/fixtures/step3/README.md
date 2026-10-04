# Event store written by step 3 (before lineage)

`events.sqlite` was written by troupe at commit `4ef5d76`, the last commit before lineage. `test_lineage_legacy.py`
checks that later code still reads it. Steps used to make it:

```sh
git worktree add --detach /tmp/troupe-step3 4ef5d76
mkdir -p /tmp/step3-theatre/.troupe && printf 'a: 1\n' > /tmp/step3-theatre/.troupe/troupe.yml
cd /tmp/troupe-step3
uv run troupe config history --theatre /tmp/step3-theatre   # Created + Imported a=1
uv run troupe config set a 2 --theatre /tmp/step3-theatre   # LeafSet a: 1 -> 2
cp /tmp/step3-theatre/.troupe/troupe.yml /tmp/step3-theatre/.troupe/events.sqlite tests/fixtures/step3/
git worktree remove /tmp/troupe-step3
```

Stored events (`stored_events` table): version 1 `TheatreConfig.Created`, 2 `TheatreConfig.Imported` (`a`, new 1),
3 `TheatreConfig.LeafSet` (`a`, old 1, new 2), all without `class_version`.
