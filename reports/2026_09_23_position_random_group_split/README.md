# Retrospective random group split

This manifest replaces chronological splitting for future analyses of the 113
currently usable scans. It does not relabel or alter any earlier result. All 113
scans have already been exposed through prior development or validation work,
so the `test` partition is a retrospective audit set and is not an untouched
test set.

Scans are first placed in fixed, non-overlapping two-hour UTC intervals anchored
at the Unix epoch. This keeps nearby and potentially correlated scans together.
Generation fails if any nominal five-minute capture crosses an interval boundary;
none of these 113 captures does, so no capture interval can overlap partitions.
Seed `20260923` shuffles the 13 whole groups. Exact dynamic programming then
chooses the whole-group allocation nearest the requested 60/20/20 scan counts;
the seeded order resolves equally good allocations. No position outcome,
reference error, residual, or model score enters grouping or assignment.

| partition | groups | scans | fraction |
|---|---:|---:|---:|
| train | 9 | 68 | 60.2% |
| validation | 2 | 22 | 19.5% |
| test | 2 | 23 | 20.4% |

The source universe is exactly the old 64-scan training partition plus the old
49-scan development-validation partition. Existing embargo/quarantine scans and
the unopened prospective reserve remain excluded. `manifest.json` records every
group, session ID, assignment, seed, rule, and the SHA-256 digest of its source
manifest.

Two-hour groups support short and medium-duration retrospective studies. This
small corpus cannot provide independent contiguous eight-hour validation and
test windows under this grouping. Disjoint groups must not be stitched and
described as continuous eight-hour evidence. A future long-duration randomized
study should randomize whole groups of at least eight hours once enough ordinary
recordings already exist; this report neither authorizes nor waits for new RF
collection.

Two hours is a conservative grouping heuristic, not proof of independence.
Adjacent groups can still share longer-lived receiver conditions, clock behavior,
and recurring satellite visits; uncertainty analyses must retain group-level
resampling and state this limitation.

Reproduce the manifest with:

```bash
uv run python tools/research/generate_position_random_group_split.py \
  --source reports/2026_09_23_position_train_val_test/dataset/manifest.json \
  --inventory reports/2026_09_23_day_position_validation/inventory.json \
  --output /tmp/position-random-group-manifest.json \
  --seed 20260923
```
