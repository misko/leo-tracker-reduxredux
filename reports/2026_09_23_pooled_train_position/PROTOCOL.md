# Pooled TRAIN common-position experiment

Use all 151 frozen TRAIN sessions (the two disjoint eight-hour groups), retaining
fixed baseline identities from the sealed per-scan epoch fits. Test both priors
and all scales 0.2/1/5 s. Start at the arithmetic mean of the two sealed group
positions in the same prior's east/north coordinates, with the corresponding
sealed per-scan epochs. This initialization uses no reference position.

Reuse the existing bounded Schur polish to fit one position and 151 scan epochs.
Keep original randomized masks, duration weights, capped loss, CFO profiling,
timing bounds and altitude zero. Do not reassign candidates in this experiment.
Verify exact full TRAIN membership, disjoint VAL/TEST, source and cache hashes,
and uniqueness of track IDs before fitting. Four workers execute six arms.
Seal every fit before computing held-frequency and geographic errors. Retain
all stopping/boundary/visibility diagnostics. This is a conditional pooled fit,
not independent validation, a new blind global acquisition, or 16 continuous
captured hours. The two recording groups are separated in wall-clock time.
