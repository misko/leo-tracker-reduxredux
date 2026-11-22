# Time regional position scores from local geometry contractions

Four affine geometry patches reduced the cost of an 81-point, fixed-weight marginal grid by about 2.7–2.9× in both calibration arms. On DS30-0374 they saved **0.41 CPU seconds** across both arms at this boundary. The approximate scores kept the winning point of the coarse grid in these two saved inputs, with maximum absolute discrepancies of 132 score units on DS30 and 18.4 on north-far. The approximation is too large for a drop-in replacement of the published objective grid. [Native timing comparison](solver-native-family.md)

## Scope

Start with the stock selected curved-data problem. For each arm use its endpoint track weights, nuisance prior, mask, association and phase references for all trial positions. The direct comparator evaluates the nonlinear line-of-sight projection and assembles the Gaussian marginal from the observed rows at each point. The candidate takes the same physical projection at each patch center and the four 1 m derivative points. It uses the resulting affine row model to construct six normal matrices, then evaluates their quadratic polynomial in east and north before the same Cholesky factorization. This reuses all row contractions with no changes to the catalogue or owner search. The four quadrant centers follow the supplied region width. [Affine contraction](../../../tools/pipeline_eval/variants/algo08_affine_statistics.py)

This boundary freezes the variational weights and measures the curved likelihood without the full predictive and grid construction. The published diagnostic grid instead recomputes its native variational solve at each point. The stock solver still selects the result in the experiment. Both north-far false fixes remain, 52.455 km with zero calibration and 52.491 km with fitted calibration. [Regional reference scores](../regional-release/blind-scores.csv)

## Timed comparisons

Results use the same two saved detectors, TLE histories and offers as the native Schur experiment. The timer covers all 81 evaluations and setup of the affine patches on one low-priority pinned core. The affine run uses 5 physical geometry evaluations for one patch or 20 for four patches instead of 81. Scores omit common normalization constants. The fixed-weight comparators retain the same marginal volume term and matched `c = 0`/fitted calibration settings.

| Saved input and arm | Direct CPU s | One patch CPU s | Four patches CPU s | Maximum score error, one / four | Median score error, one / four |
|---|---:|---:|---:|---:|---:|
| DS30-0374, `c = 0` | 0.3110 | 0.0363 | 0.1098 | 466.76 / 131.53 | 41.50 / 6.62 |
| DS30-0374, fitted `c` | 0.3239 | 0.0351 | 0.1109 | 462.93 / 131.58 | 41.23 / 6.58 |
| North far, `c = 0` | 0.0244 | 0.0045 | 0.0089 | 69.46 / 18.36 | 7.41 / 1.89 |
| North far, fitted `c` | 0.0246 | 0.0046 | 0.0091 | 31.59 / 7.94 | 5.20 / 1.37 |

The observed score spans were about 5,700 for DS30 and 879 / 391 for north-far. The reduction in matrix-assembly work is real, while unchanged 3.125 km grid winners give a weak check on a continuously optimized position. The direct fixed-weight grid is already much cheaper than the published robust diagnostic. The measured saving cannot be extrapolated to the full optimizer or cavity without a way to refresh or certify the weights and score approximations.

A feasible cross-stage test would use the sparse family blocks to propose a joint position and satellite-phase update from a local patch. Each accepted move would be checked against the exact nonlinear marginal with refreshed robust weights. Family exclusions and grid points could reuse that patch only where the same data layout and error bounds hold. A full-catalogue alternative remains in play whenever its score's bound overlaps the incumbent. The measurements here support a proposal mechanism, with an exact acceptance and reporting step. [Trial runner](solver_affine_trial.py) · [Component test](../../../tests/pipeline_eval/test_algo08_affine_statistics.py)
