# Original held prediction mainly measures within-track interpolation

All 32 original observation exports verify their declared digests and capture
bindings. The whole-visit split is consistent across tracks and receivers.

| Quantity | Count / value |
|---|---:|
| Exported tracks | 1,923 |
| Training measurement rows | 62,554 |
| Held measurement rows | 41,789 |
| Held rows with training in the same track | 41,789 (100%) |
| Held rows inside that track's training-time span | 39,112 (93.594%) |
| Nearest training-time gap: median / P90 / P99 / max | 0.401 / 1.124 / 2.588 / 8.733s |

This is valid conditional prediction of new visits from the same tracks. It
does not separate source-specific ephemeris, transmitter or persistent tracking
errors from geometry. Slowly varying errors may appear in both partitions.
The proximity calculation does not itself estimate their correlation or prove
which effect explains any particular model's geographic failure.

Source inspection of `tools/ds7_export_baseline.py` confirms the whole-visit
hash partition and training-only candidate shortlist score. Track construction
precedes partitioning, so this is not an end-to-end blind extraction benchmark.
No same-visit partition conflict was found; this report does not allege a
coding leak or invalidate the recorded conditional prediction results.

The recent orbit-uncertainty and free-height pilots demonstrate the practical
limit: held prediction improves on both pilot scans, while each model fails
the geographic gate. Future interpolation gains should be treated as evidence
that a model explains repeatable frequency structure, not evidence that it
identifies the correct geographic explanation.

Changing the score alone is not an established fix. The completed
[source-holdout selector](../source_loo_exact/screen_recovery/README.md) already
tested 448 qualified folds and failed its paired-win/P90 advancement rule.
Neither that result nor these interpolation counts justify another broad
model sweep. The next correction should have independently identifiable
physical parameters or independent measurement evidence, followed by the
existing geographic and replication gates. Measured antenna altitude remains
one concrete missing input; no altitude is inferred from the benchmark errors.

Two tests cover interpolation/extrapolation, nearest-neighbor distances,
unsorted times and empty training support. No position fits or input changes.
See [protocol](PROTOCOL.md) and [per-scan evidence with source hashes](outcome.json).
