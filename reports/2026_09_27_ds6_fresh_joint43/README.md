# DS6 joint location after causal element freshness correction

The all-43 static-site estimate is 761.85 m from the operator roof reference.
Both complementary random whole-scan subsets also remain below 1 km. This
replaces the older 772.34 m pooled result for the corrected element policy;
it does not establish sub-kilometre independent-scan accuracy.

| Fit | Scans | Horizontal error, m | Held log-score change versus independent fits |
|---|---:|---:|---:|
| All | 43 | 761.85 | -2884.84 |
| A | 22 | 941.20 | -1741.54 |
| B | 21 | 649.88 | -1103.37 |

The A/B split is unchanged from the original joint experiment: hash ordering
with seed 2026092729, then alternating whole scans. All five scans affected by
the stale-mirror catalogue issue fall in B; A has identical inputs and
reproduces the previous result. The two subset estimates are 630.33 m apart.

Each fit uses one static position, independent scan timing offsets and
training-profiled track frequency offsets, a fixed 100 Hz Student-t4
likelihood and candidate mixtures. The five affected scans' full-catalogue
proposals were rebuilt under the corrected causal policy; the other 38
inferences were reused only after complete element-record identity checks.
Every model verifies the exact element-source provenance from its input fit.

Training visits alone determine parameters and selection between two starts.
The initial positions come from included scans' training estimates and the
existing donor center; the reference coordinate is read only by the later
summarizer. Neither subset uses excluded scans' observations or fitted clocks,
though both inherit the same development-derived search center. This remains
a local, conditional result rather than blind global validation.

All three selected fits converged within bounds. Exact orbit propagation at
the winners differs from interpolation by at most 0.02037 Hz. Four tests
passed: sparse versus independent finite-difference gradients and held-score
isolation, synthetic shared-location/independent-clock recovery, unchanged
random whole-scan partitions and dependency hashes, and completed real-result
selection/provenance/propagation checks.

Held prediction is worse than the independent fits despite better geographic
accuracy, so unmodelled scan-dependent bias remains. The corrected independent
baseline has 6/43 sub-kilometre scans, median error 2.355 km and mean 3.317 km.
The broader accuracy objective remains active; the pooled result must not be
reported as an independent result for every scan. The reference is
operator-supplied, with no surveyed uncertainty or altitude supplied.
