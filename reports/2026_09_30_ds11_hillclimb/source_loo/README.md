# Satellite-source deletion: local stability diagnostic

Exact deletion refits reject the local influence approximation: all 16 fits
qualify, but only 6 meet all approximation tolerances. No approximate predictive
ranking proceeds, and no positioning improvement or model selection is
established. Exact refits confirm kilometre-scale position dependence on some
conditionally assigned satellites.

Only original DS11 scan indices 0 and 16 were evaluated, using their original
causal orbit banks and four existing fitted endpoints. Satellite membership is
frozen from the original IID training fit at probability at least 0.90, grouped
by physical NORAD across receivers and RFs. These remain conditional identities,
not authenticated satellite associations. No reference coordinates or held
measurement values enter this phase.

| Scan index | Eligible satellites | Available family/source folds | Largest predicted E/N shift across families |
|---|---:|---:|---:|
| 0 | 14 | 56/56 | 6.562 km |
| 16 | 18 | 72/72 | 2.071 km |

All 128 folds pass the finite, symmetry, positive-curvature, conditioning,
step-halving and unchanged-bound checks. The largest relative step-halving
disagreement is 0.0006404 against a 0.005 limit; maximum Hessian condition number
is 914.30. The separately recorded effect of the full endpoint's nonzero
gradient is at most 0.00445 m in E/N. Neither numerical convergence residuals
nor these local curvature checks explain away the large predicted shifts.

For scan 0, all four families identify NORAD 65512 as the largest influence.
Its two assigned tracks both come from receiver 0, at 10.71 and 11.21 GHz.
Predicted timing shifts span 0.47–0.97 seconds and cross multiple interpolation
intervals. This is a reason to test the approximation, not evidence that either
track is wrong or should be discarded.

The maximum and lower-median displacement source for each family and scan are
sealed in the phase-one JSON outputs before any exact refit. All eligible folds
must be available; a failed fold cannot be replaced by another source. The
exact audit compares 16 fixed deletion fits with their approximations,
including common-model held prediction. It is complete.

All four scan-0 median-influence cases pass; all four largest-influence cases
fail. For scan 16, only the t8/100 and t4/200 median cases pass. The largest
approximation errors are 2842.0 m in E/N, 0.4152 seconds in timing, and 48.9503
held nats. Several other cases fail only the held-score tolerance; thresholds
are not relaxed. All 16 jobs complete in 5.3–13.6 seconds and qualify under the
original optimizer gates. See [exact protocol](EXACT_PROTOCOL.md) and
[verified exact assessment](exact-assessment.json).

For NORAD 65512 in scan 0, the exact deletion shifts are 2657.3 m (IID),
3724.1 m (source weighting), 2879.3 m (t8/100), and 2972.1 m (t4/200).
These are movements between fitted positions, not errors against a reference.
They establish substantial model sensitivity without identifying which position
is closer to truth. Ten combined component tests pass; the independent review
checks training-only CFO profiling, unchanged refit gates, frozen weights and
input bindings. The assessment verifies all 16 terminal receipts and source
hashes. A future fully exact source-holdout experiment would be a separate
bounded follow-up; this failed approximation cannot rank endpoints.

A read-only check of the existing four-hour delayed-orbit inventory finds
identical original and later element bytes for scan 0's NORAD 65512; its
original element epoch was about 23.63 hours before capture. Thus that archive
window does not supply a newer revision for the strongest scan-0 sensitivity.
No offline position fit was run, and this does not establish orbit accuracy.

Both processes exited successfully in 28.25 and 27.65 seconds, below their
90-second caps, using one numerical worker and single-thread BLAS. Six owned
tests pass, including actual source-weighted evaluator additivity. Independent
review found no launch blocker, and subsequent verification matched all 21
recorded source bindings per scan. Frozen implementations and prior endpoints
were not edited during execution.

Evidence: [protocol](PROTOCOL.md), [scan 0](runs/phase1/00.json),
[scan 16](runs/phase1/16.json), and their adjacent terminal receipts. This is
exploratory work on previously examined recordings; no offline orbit data,
new RF collection, production change, or geographic gain is claimed.
