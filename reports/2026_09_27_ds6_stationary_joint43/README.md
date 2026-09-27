# DS6 joint position with stationary offset profiling

This experiment revalidates the earlier joint static-site result after replacing the twelve-iteration offset approximation with the corrected stationary penalized-offset solver on every track and candidate. It does not substitute pooled accuracy for independent per-scan accuracy.

The frozen protocol retains all 43 DS6 scans and the original seed-2026092729 complementary whole-scan subsets (A:22, B:21). Each fit estimates one shared horizontal position, one timing offset per scan, and independently profiled track offsets. Student-t4 scale is fixed at 100 Hz. Candidate shortlists, causal element selection, and randomized whole-visit training/evaluation masks remain inherited. No ground-truth location is loaded by the fitting program.

Two starts use the mean of included corrected per-scan training positions and the inherited donor center, respectively, with included corrected timing estimates. Bounds remain +/-12 km horizontally and +/-5 seconds per scan. Winner selection uses training likelihood only. Sparse envelope derivatives accumulate shared position gradients and keep timing derivatives scan-local. Exact orbit propagation checks each selected winner and compares held-out prediction against the corrected independent fits.

Preflight tests check the joint gradient against independent full-objective differences, invariance to changing held-out observations, the original randomized partition, and hashes of frozen dependencies. Completion tests require all three results, selected-run convergence, no bounds hit, all expected scan audits, stationary offsets, and interpolation errors below 0.05 Hz. The post-fit summarizer alone reads the operator reference.

Limitations: inherited local geographic search and candidate shortlists, finite scalar-mode brackets, reused development observations, and an operator-provided unsurveyed reference with unknown altitude. The earlier 761.85 m pooled result uses the old offset model and is not evidence of this experiment's outcome.

All three fits completed both starts, with all six starts converged and none touching bounds. All nine tests pass, including independent full-profile gradient audits for every fitted scan at each selected joint winner.

| Fit | Scans | Corrected error (m) | Previous offset-model error (m) | Held-out log-score gain versus corrected independent fits |
|---|---:|---:|---:|---:|
| All | 43 | 754.938 | 761.850 | -2906.737 |
| A | 22 | 935.176 | 941.203 | -1745.623 |
| B | 21 | 637.095 | 649.877 | -1118.636 |

The randomized subset estimates are 625.825 m apart. All exact-orbit interpolation errors are below 0.021 Hz. Maximum differences between assembled envelope and numerical gradients are 0.000143776 (all), 0.000101266 (A), and 0.000026416 (B). Optimization reports relative-objective convergence; the gradient comparison verifies derivative accuracy, not a claim of zero gradient or global optimality.

These are combined static-site estimates, conditional on the inherited local search and candidate model. They do not establish independent per-scan sub-kilometre accuracy. The corrected independent result remains 6/43 below 1 km, with mean error 3.333 km. Worse held-out prediction under pooling remains evidence of physical-model mismatch despite better geographic estimates. See PREDICTION_DIAGNOSTIC.md for its distribution across scans and sample rates.
