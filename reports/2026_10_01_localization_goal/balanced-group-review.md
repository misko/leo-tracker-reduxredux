# Equal aggregate satellite weighting

The unchanged satellite-balanced score improves 9 of 12 development scans and reduces median error by 33.8%, but worsens p90. Preserve it as a research result; do not promote it as a solution to the accuracy goal.

| Same 12 development scans | Original baseline | Satellite-balanced |
| --- | ---: | ---: |
| Accepted | 12/12 | 12/12 |
| Median error | 1,892.15 m | 1,252.58 m |
| p90 error | 3,998.11 m | 4,711.76 m |
| Within 1,000 m | 1/12 | 4/12 |
| Within 3,000 m | 10/12 | 9/12 |
| Median warm fitting wall time | 1.185 s | 1.490 s |
| Maximum warm fitting wall time | 1.287 s | 1.991 s |
| Median process CPU | 1.168 s | 1.469 s |

The controls start at saved stationary baseline states and stop immediately. These warm times exclude acquisition and must not be presented as cold end-to-end performance.

![Paired errors](balanced-group-panel-v1.png)

The first three pilot scans all improved: DS9-F025 2,223.70 to 762.21 m, DS10-F028 7,733.56 to 5,121.55 m, and DS11-F018 1,257.18 to 618.83 m. That triggered an unchanged expansion to the remaining nine scans of the pre-existing development panel. Six of those nine improved. Regressions were DS9-F045 (1,924.61 to 2,735.19 m), DS10-F075 (2,931.54 to 3,743.05 m), and DS9-F065 (4,109.31 to 4,819.40 m). The difficult DS10 pilot improves but remains the largest error.

## Model and verification

For N signal tracks assigned to G satellite groups, with n_s tracks in group s, set each signal-track coefficient to N/(G n_s). The total signal-track weight stays N, and each satellite receives total weight N/G. Clutter coefficients remain one. Preserve all original Gaussian clock/drift/epoch priors, original observations, fixed hard assignments selected at the baseline, uniform Sacramento support, and fixed 30.48 m MSL height. Jointly refit location and active nuisance parameters with the scaled solver.

This is an engineering composite objective, not a normalized generative likelihood or calibrated posterior. It can increase the influence of weak singleton groups. Counts and assignments are frozen before fitting; no reference positions choose groups or weights. The development references have already been exposed in prior experiments, so this panel is not independent validation.

Two weighting tests passed: preservation of total/group weight, unchanged clutter, permutation invariance, and all-one weights for equal-size groups, singletons, or no signal. All 24 control/candidate outcomes passed source/input/height/assignment/weight seals, support, exact objective and initial metric reconstruction, monotonic descent, and full-coordinate finite-difference stationarity checks. All controls reproduce the original objective and position. Every process stayed within its 25 s internal/30 s external diagnostic budget, with at most two fitting processes. No retries, omitted failures, new RF, production changes or fixture edits.

Authoritative results: `balanced-group-v1-evaluation.json`, `balanced-group-expansion-v1-evaluation.json`, and combined `balanced-group-panel-v1.json`, each with a SHA seal. Model, runner, supervisor and evaluator source digests are bound in the two batch directories. The combined plot was visually inspected.

## Decision

The median improvement warrants investigating count-driven group influence, but the tail regression prevents promotion. Do not tune a weight exponent to these exposed errors or select baseline versus balanced positions using GPS. Next, audit how each group's score and local information change between the sealed original and balanced endpoints across all 12 scans, using only radio/model quantities. Check whether singleton amplification or loss of geometric diversity provides a reproducible explanation; compare the same diagnostic across improved and worsened scans only after computing it without reference data. A new weighting rule would require an independently justified design and fresh validation, not a retrospective geographic selector.

No new 64-scan, held-out or uncertainty-calibration result is claimed. The frozen full baseline remains 2,059.90 m median and 5,850.75 m p90 with 64/64 acceptance. The goal remains active and unmet.
