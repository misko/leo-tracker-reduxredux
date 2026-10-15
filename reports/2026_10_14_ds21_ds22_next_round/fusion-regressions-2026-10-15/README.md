# Case-matched channel-fusion regressions

This inventory uses the exact published curves: DS21 coverage-discovery and DS22 original cohort. Later pilots do not replace their rows. Position/reference distances identify diagnostic cases only; they do not select model parameters or fitted winners. DS22 reference continuity is unconfirmed.

| Dataset | Model | Complete triplets | Worse than both | Worse than one only | No worse than either | Missing full/half |
|---|---|---:|---:|---:|---:|---:|
| DS21 | B | 34 | 8 | 12 | 14 | 0 |
| DS21 | C | 29 | 7 | 12 | 10 | 5 |
| DS22 | B | 44 | 8 | 11 | 25 | 0 |
| DS22 | C | 34 | 11 | 15 | 8 | 10 |

## Every case worse than both halves

| Dataset/model | Case | CH1–4 km | CH5–8 km | CH1–8 km | Excess over worse half km |
|---|---|---:|---:|---:|---:|
| DS21 B | DS21-059 | 6.741 | 2.563 | 333.218 | 326.477 |
| DS21 B | DS21-081 | 8.652 | 10.476 | 15.154 | 4.678 |
| DS21 B | DS21-057 | 5.924 | 6.055 | 9.104 | 3.048 |
| DS21 B | DS21-031 | 4.308 | 5.100 | 6.214 | 1.113 |
| DS21 B | DS21-037 | 1.237 | 1.278 | 2.204 | 0.926 |
| DS21 B | DS21-083 | 2.030 | 2.038 | 2.663 | 0.625 |
| DS21 B | DS21-061 | 8.028 | 7.234 | 8.433 | 0.405 |
| DS21 B | DS21-053 | 59.407 | 242.215 | 242.262 | 0.047 |
| DS21 C | DS21-081 | 11.070 | 7.866 | 253.243 | 242.172 |
| DS21 C | DS21-029 | 85.926 | 74.417 | 100.199 | 14.272 |
| DS21 C | DS21-073 | 12.023 | 13.267 | 22.837 | 9.570 |
| DS21 C | DS21-035 | 172.393 | 101.896 | 177.317 | 4.924 |
| DS21 C | DS21-025 | 2.726 | 2.911 | 4.459 | 1.548 |
| DS21 C | DS21-005 | 1.373 | 1.149 | 2.387 | 1.014 |
| DS21 C | DS21-055 | 2.107 | 1.792 | 2.205 | 0.098 |
| DS22 B | DS22-071 | 10.222 | 3.124 | 324.778 | 314.556 |
| DS22 B | DS22-115 | 2.748 | 24.236 | 44.839 | 20.603 |
| DS22 B | DS22-061 | 3.412 | 1.454 | 14.767 | 11.355 |
| DS22 B | DS22-107 | 1.007 | 1.377 | 3.338 | 1.960 |
| DS22 B | DS22-113 | 1.619 | 5.468 | 7.215 | 1.747 |
| DS22 B | DS22-017 | 2.463 | 1.638 | 3.059 | 0.596 |
| DS22 B | DS22-057 | 0.530 | 0.999 | 1.394 | 0.394 |
| DS22 B | DS22-127 | 0.663 | 0.370 | 0.897 | 0.234 |
| DS22 C | DS22-053 | 27.083 | 30.492 | 75.782 | 45.290 |
| DS22 C | DS22-075 | 23.428 | 51.146 | 77.587 | 26.440 |
| DS22 C | DS22-109 | 3.331 | 0.795 | 12.625 | 9.293 |
| DS22 C | DS22-131 | 2.563 | 0.675 | 8.159 | 5.596 |
| DS22 C | DS22-129 | 1.640 | 3.525 | 4.265 | 0.740 |
| DS22 C | DS22-017 | 3.303 | 2.042 | 3.769 | 0.466 |
| DS22 C | DS22-039 | 1.392 | 0.293 | 1.842 | 0.449 |
| DS22 C | DS22-057 | 0.829 | 1.253 | 1.659 | 0.406 |
| DS22 C | DS22-041 | 3.243 | 2.236 | 3.599 | 0.356 |
| DS22 C | DS22-043 | 1.511 | 0.984 | 1.830 | 0.319 |
| DS22 C | DS22-095 | 2.164 | 1.993 | 2.302 | 0.138 |

## What the existing evidence establishes

- Missing full estimates contribute to C’s lower cumulative curve: 5/34 DS21 and 10/44 DS22. They are not successful estimates with a large numerical error.
- DS21 B059: preserving complete fold-trained states, including timing/calibration, recovered the later 333 km failure to 1.086 km. Position-only initialization discards relevant information. See [numerical repair](../model_a_b059_profile_polish_results.md).
- DS21 C081: an accepted challenger has lower objective than the distant incumbent; subsequent matched control selected 15.115 km, with receiver clocks 13.934 km. This diagnoses an earlier search/eligibility shortfall, while leaving substantial model error. See [clock control](../MODEL_C_081_CLOCK_CONTROL_RESULTS.md).
- DS21 A053 targeted controls: full 1.148 km versus high 0.300 km persists after all nine matched fits converge. The original hard visibility normalizer has a measured boundary discontinuity, but smoothing alone leaves full position essentially unchanged. See [matched controls](../model_a_hard_visibility_control_results.md).
- DS22 B071: numerical repair completed predictive comparisons, but the detectability model does not consistently improve predictive likelihood and the full winner remains distant. This is not explained by the hard-visibility jump seen on A053.
- DS22 C075: complete-prior coverage still selects a distant fit. None of the 20 rejected endpoints has a lower objective than its accepted winner; all are far from stationarity. Matched union-bank half fits are now being evaluated to isolate the remaining fusion conflict.

## Next model directions and discriminating checks

1. **Retain complete solutions from each band and fold.** Re-evaluate and refine full parameter states on a common candidate bank and frame, with identical domains and budgets. A lower feasible full score diagnoses a search shortfall; only accepted full refinements can replace winners.
2. **Model band-dependent detection and calibration only where prediction supports it.** The tested shared-plus-band-contrast detectability model improves DS21-053 predictive NLL but worsens DS21-035. Keep both transfer cases in position tests; do not infer a universal fix.
3. **Separate search coverage, numerical acceptance, and likelihood conflict.** Use deterministic prior coverage where domains exclude possible basins; exact normalized likelihood and gradient checks where score discontinuities occur; channel/receiver/time-block decompositions where accepted full fits still lose. Stronger priors or new weights require predictive evidence.

Fresh audits prioritize B081/B115 and C053/C081; existing B059/B071 and A053 evidence is retained. These are hypotheses and tests, not claims that more parameters guarantee improvement. Each next generation must report fixed-version all/low/high distributions, success denominators, matched-case changes and worst failures using the same plot conventions. No per-case truth-based best-of-models curve will be presented as a deployable method.

[All case classifications, including one-half regressions and missing fits](cases.csv). [Current performance plots](../performance-report-2026-10-15/README.md).
