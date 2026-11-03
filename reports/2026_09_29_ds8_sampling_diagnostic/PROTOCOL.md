# DS8 matched-observation diagnostic at two fixed geographic fits

The original and rank-selected N24 fits differ by 2.078 km and share eight scans. Freeze their positions. Score the union of 40 scans, partitioned into eight shared, sixteen original-only and sixteen rank-only recordings. Verify identical artifact digests for shared scans. Keep original masks, likelihood, candidate banks and height zero.

For each scan and each fixed position, refit timing on training data only. Initializations are the best of the existing 41-point timing grid plus every available inherited timing from the original/rank fit, deduplicated by exact value. Use the existing timing-only optimizer and qualification; choose highest qualified training score. Positions cannot move. Preserve failed starts and any unsupported scan/arm without replacement.

Report per-scan and partitioned rank-minus-original training/held scores, qualified coverage, conditional top-candidate changes and visible-candidate-count changes. No reference coordinate enters the diagnostic. Held values neither fit timing nor select a start. The position endpoints were already trained on their respective scan sets, so this is exploratory matched scoring, not independent location validation or a calibrated identity test. No new RF, propagation, archive export or production change.
