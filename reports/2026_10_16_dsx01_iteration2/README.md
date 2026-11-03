# DSX01 iteration 2: exact timing profiles

The fixed-bank exact profile associates 422/693 window observations and 13,784/20,084 full-recording observations; 6/15 windows reach at least 80% net restoration of originally missing assignments. It gains 3,304 assignments and loses 742 original assignments. 4/5 profile endpoints pass strict KKT. These are full-data warm-start development results; satellite identity hypotheses are not truth labels and higher association does not establish better localization.

The profile ranks signed changes in the unchanged all-point conditional NLL and exact timing prior. It debits old support lost elsewhere in the recording. It removes A's global 48-arc selection, 16-point arc subsampling, 70% coherence gate and top-eight arc-proposal restriction. See [arc diagnosis](arc_diagnostics.md) for the measured failures of those gates.

Profile and continuation have a 1,000-full-objective/120-second allowance per recording; orbit projections are reported separately. Frozen A used 180 evaluations. Therefore A180 versus profile1000 combines an algorithm and budget change. Continuation1000 is the available matched-budget control; Arc A1000 is included automatically when its saved results exist. Incomplete optional arms retain all-recording denominators and show their completed coverage.

## Fixed-bank fitted-c results

| Method | Completed / 5 | Full associations / 20,084 | Window associations / 693 | New / lost original full support | Assigned RMS Hz | Intersection RMS original → variant Hz | ≥80% net-restored windows / 15 | Strict KKT passes / 5 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Original | 5 | 11222 (55.88%) | 96 (13.85%) | 0 / 0 | 160.29 | 160.29 → 160.29 | 0 | 4 |
| Frozen A (180) | 5 | 11880 (59.15%) | 253 (36.51%) | 932 / 274 | 159.57 | 158.28 → 157.08 | 4 | 0 |
| Continuation (1000) | 5 | 11226 (55.90%) | 95 (13.71%) | 18 / 14 | 160.38 | 159.97 → 160.02 | 0 | 4 |
| Exact profile (1000) | 5 | 13784 (68.63%) | 422 (60.89%) | 3304 / 742 | 155.82 | 157.06 → 152.44 | 6 | 4 |
| Arc A (1000) | 5 | 12006 (59.78%) | 249 (35.93%) | 1202 / 418 | 158.54 | 157.80 → 155.72 | 3 | 4 |

Assigned RMS uses each method's assigned set. The intersection RMS pair uses the same observations assigned by that method and the original; selected satellite identities may change. Missing/unassociated observations stay in all association and CDF denominators.

## All 15 windows

A major restored window requires `(new assignments − lost original assignments) / originally missing observations ≥ 0.80`. This is distinct from 80% association over all window rows.

| Window | Source | All rows | Original | Frozen A (180) | Continuation (1000) | Exact profile (1000) | Arc A (1000) | Expanded continuation | Expanded profile | Profile net missing restored |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 001 | S01 | 86 | 13 (15.1%) | 74 (86.0%) | 13 (15.1%) | 79 (91.9%) | 70 (81.4%) | 13 (15.1%) | 45 (52.3%) | 90.4% |
| 002 | S01 | 35 | 1 (2.9%) | 2 (5.7%) | 1 (2.9%) | 11 (31.4%) | 2 (5.7%) | 2 (5.7%) | 13 (37.1%) | 29.4% |
| 003 | S01 | 27 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0.0% |
| 004 | S02 | 44 | 6 (13.6%) | 6 (13.6%) | 6 (13.6%) | 10 (22.7%) | 6 (13.6%) | 7 (15.9%) | 11 (25.0%) | 10.5% |
| 005 | S02 | 33 | 1 (3.0%) | 1 (3.0%) | 1 (3.0%) | 31 (93.9%) | 1 (3.0%) | 1 (3.0%) | 33 (100.0%) | 93.8% |
| 006 | S02 | 72 | 12 (16.7%) | 11 (15.3%) | 11 (15.3%) | 33 (45.8%) | 11 (15.3%) | 13 (18.1%) | 36 (50.0%) | 35.0% |
| 007 | S03 | 54 | 16 (29.6%) | 54 (100.0%) | 16 (29.6%) | 54 (100.0%) | 54 (100.0%) | 20 (37.0%) | 54 (100.0%) | 100.0% |
| 008 | S03 | 50 | 8 (16.0%) | 9 (18.0%) | 8 (16.0%) | 48 (96.0%) | 10 (20.0%) | 10 (20.0%) | 48 (96.0%) | 95.2% |
| 009 | S03 | 34 | 4 (11.8%) | 31 (91.2%) | 4 (11.8%) | 34 (100.0%) | 31 (91.2%) | 8 (23.5%) | 34 (100.0%) | 100.0% |
| 010 | S04 | 46 | 2 (4.3%) | 3 (6.5%) | 2 (4.3%) | 25 (54.3%) | 3 (6.5%) | 7 (15.2%) | 33 (71.7%) | 52.3% |
| 011 | S04 | 43 | 9 (20.9%) | 10 (23.3%) | 9 (20.9%) | 15 (34.9%) | 10 (23.3%) | 11 (25.6%) | 11 (25.6%) | 17.6% |
| 012 | S04 | 66 | 14 (21.2%) | 14 (21.2%) | 14 (21.2%) | 16 (24.2%) | 14 (21.2%) | 15 (22.7%) | 27 (40.9%) | 3.8% |
| 013 | S05 | 28 | 1 (3.6%) | 1 (3.6%) | 1 (3.6%) | 22 (78.6%) | 0 (0.0%) | 1 (3.6%) | 23 (82.1%) | 77.8% |
| 014 | S05 | 39 | 3 (7.7%) | 3 (7.7%) | 3 (7.7%) | 11 (28.2%) | 2 (5.1%) | 2 (5.1%) | 32 (82.1%) | 22.2% |
| 015 | S05 | 36 | 6 (16.7%) | 34 (94.4%) | 6 (16.7%) | 33 (91.7%) | 35 (97.2%) | 8 (22.2%) | 34 (94.4%) | 90.0% |

## Source-level profile regressions, timing and position

| Source | New / lost full support | New / lost outside windows | Assigned RMS Hz | Intersection RMS original → profile Hz | Configured-reference km original → profile | Common timing s original → profile | Relative timing RMS s original → profile | KKT | Strict pass |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | ---: | --- |
| S01 | 1179 / 305 | 1102 / 304 | 157.14 | 157.60 → 158.22 | 132.18 → 132.47 | -1.59 → -3.37 | 11.11 → 10.26 | 0.004055 | False |
| S02 | 591 / 146 | 531 / 141 | 168.06 | 167.04 → 169.69 | 133.79 → 135.38 | -0.65 → -1.87 | 9.82 → 8.98 | 0.000154 | True |
| S03 | 423 / 47 | 315 / 47 | 140.84 | 140.79 → 138.78 | 5.24 → 3.28 | 1.90 → 0.88 | 6.80 → 3.42 | 0.000845 | True |
| S04 | 548 / 126 | 513 / 122 | 147.44 | 159.20 → 139.71 | 258.66 → 260.09 | 3.87 → 4.88 | 8.69 → 6.18 | 0.000635 | True |
| S05 | 563 / 118 | 506 / 117 | 169.78 | 167.75 → 165.52 | 7.44 → 4.71 | 0.46 → -0.65 | 8.04 → 5.02 | 0.000113 | True |

A strict endpoint requires projected KKT ≤0.001. A feasible lower-objective state that fails this threshold remains a research iterate. Position is distance to the previously operator-configured station, not surveyed independent truth. Frequency-fit improvements are reported separately from position. Common and relative timing describe a parameter gauge; changes do not prove physical ephemeris error. The original table uses the present broad endpoint audit (4/5); the immutable original receipts passed their original audit options (5/5). S02 has the known broad-audit discrepancy, and is not silently reclassified as a newly accepted original fit.

| Source | Profile full-objective calls | Profile orbit projections | Declared full-objective cap |
| --- | ---: | ---: | ---: |
| S01 | 866 | 200 | 1000 |
| S02 | 831 | 200 | 1000 |
| S03 | 779 | 200 | 1000 |
| S04 | 883 | 200 | 1000 |
| S05 | 663 | 200 | 1000 |

## Controlled c=0 sensitivity

Fitted-c and c=0 use identical observations, fixed candidate banks, other priors and search allowances. Zero-c starts by setting the original fitted coefficient to zero while retaining the other original parameters. It therefore has its own matched continuation; comparing it only to the saved fitted-c original would conflate calibration and optimization.

| Arm | Method | Completed / 5 | Full associations / 20,084 | Window associations / 693 | Assigned RMS Hz | KKT passes / 5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fitted-c | Continuation (1000) | 5 | 11226 | 95 | 160.38 | 4 |
| fitted-c | Exact profile (1000) | 5 | 13784 | 422 | 155.82 | 4 |
| fitted-c | Arc A (1000) | 5 | 12006 | 249 | 158.54 | 4 |
| zero-c | Continuation (1000) | 5 | 9864 | 95 | 177.11 | 4 |
| zero-c | Exact profile (1000) | 5 | 12311 | 292 | 169.40 | 3 |
| zero-c | Arc A (1000) | 5 | 10300 | 225 | 173.79 | 4 |

Source-level c, timing, configured-reference position and frequency metrics for both arms are retained in `iteration-summary.json`; calibration sensitivity is not localization accuracy evidence. Expanded-bank arms, when present, change the candidate population and are a separately labelled experiment.

| Source | Profile fitted-c / zero-c associations | Profile fitted-c / zero-c RMS Hz | Profile fitted-c / zero-c configured-reference km |
| --- | ---: | --- | --- |
| S01 | 2517 / 2514 | 157.14 / 161.42 | 132.47 / 133.32 |
| S02 | 2102 / 1756 | 168.06 / 178.17 | 135.38 / 134.43 |
| S03 | 3467 / 2587 | 140.84 / 175.52 | 3.28 / 3.75 |
| S04 | 2803 / 2569 | 147.44 / 164.44 | 260.09 / 259.86 |
| S05 | 2895 / 2885 | 169.78 / 169.51 | 4.71 / 9.68 |

## Restricted zero-contrast temporal stress test

These runs exclude held measured CFO, but permanently fix both receiver high-minus-low band offsets to zero instead of relearning them from training data. Original learned offsets are approximately −14 to −17 kHz for RX1 and +37 to +44 kHz for RX2. The missing band columns add two independent calibration directions in every training fold. Thus this protocol does not match the original band-calibration learning procedure; low held coverage cannot be attributed entirely to generalization failure. See the [cold protocol audit](cold_protocol_audit.md).

Profile and continuation are internally matched under this zero-contrast restriction. They use neutral training seeds and measured CFO only in the declared training half. Candidate banks originated from complete recordings, so this is also retrospective candidate-conditioned evaluation, not an untouched discovery test.

| Direction | Arm | Method | Completed / 5 | Held associations / all held | Held assigned RMS Hz | Held-window associations / all held-window | Training KKT passes / 5 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| early_to_late | fitted-c | continuation | 5 | 1227 / 10041 (12.22%) | 200.21 | 25 / 248 | 5 |
| early_to_late | fitted-c | profile | 5 | 1212 / 10041 (12.07%) | 194.06 | 22 / 248 | 5 |
| early_to_late | zero-c | continuation | 5 | 1245 / 10041 (12.40%) | 192.58 | 26 / 248 | 5 |
| early_to_late | zero-c | profile | 5 | 1297 / 10041 (12.92%) | 192.23 | 26 / 248 | 5 |
| late_to_early | fitted-c | continuation | 5 | 1171 / 10043 (11.66%) | 199.82 | 50 / 445 | 5 |
| late_to_early | fitted-c | profile | 5 | 1195 / 10043 (11.90%) | 193.90 | 50 / 445 | 5 |
| late_to_early | zero-c | continuation | 5 | 1210 / 10043 (12.05%) | 198.55 | 52 / 445 | 4 |
| late_to_early | zero-c | profile | 5 | 1117 / 10043 (11.12%) | 191.99 | 42 / 445 | 5 |

Across both fitted-c directions, exact profile gives 72/693 held-window assignments versus continuation's 75/693. Full held assignments total 2,407/20,084 versus 2,398/20,084. This supplies no clear held-window advantage within the restricted stress class. It does not adjudicate the complete production calibration procedure. Assigned-only RMS must be read with these differing support counts.

## Separate expanded-bank sensitivity

These endpoints add candidates and therefore change the model population. They are not fixed-bank algorithm controls. This separately reported population contains S01, S02, S03, S04, S05: 20,084 original observations and 693 window rows. Pending or unattempted endpoints remain in the denominator and completed coverage is explicit. Expanded-bank arms are omitted from primary plots to preserve equal population and timing counts.

| Arm | Method | Completed / 5 | Full associations / 20,084 | Window associations / 693 | New / lost original full support | KKT passes / 5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fitted-c | Expanded continuation | 5 | 11603 | 118 | 611 / 230 | 3 |
| fitted-c | Expanded profile | 5 | 14248 | 434 | 3817 / 791 | 4 |
| zero-c | Expanded continuation | 5 | 10139 | 111 | 1161 / 2244 | 4 |
| zero-c | Expanded profile | 5 | 12617 | 337 | 3773 / 2378 | 4 |

On exactly these same sources (fitted-c), fixed-bank profile has 13,784/20,084 full and 422/693 window associations; expanded profile has 14,248/20,084 and 434/693. More candidates do not guarantee better support in every window; per-window changes remain in the table above.

On exactly these same sources (zero-c), fixed-bank profile has 12,311/20,084 full and 292/693 window associations; expanded profile has 12,617/20,084 and 337/693. More candidates do not guarantee better support in every window; per-window changes remain in the table above.

## Plots and verification

![Full context comparison](iteration-context.png)

![All fixed windows](iteration-windows.png)

![Residual CDFs with all observations retained in denominators](iteration-distributions.png)

![Common and relative timing distributions](iteration-timing.png)

![Configured-reference position comparison](iteration-position.png)

![Matched c sensitivity](iteration-calibration.png)

![Restricted zero-contrast temporal stress test](iteration-temporal.png)

Verified 60 saved full-recording endpoints and 40 temporal endpoints. NPZ observation times match the frozen source ordering to 1 ns; full and challenge association totals match saved JSON; every window membership count and original assignment count matches DSX01. The timing histograms use five common shifts and 215 original-candidate relative contrasts for each complete method. The separate expanded-bank arms are omitted from these plots.

Rebuild with the pinned scientific Python: `python report_iteration.py`. The generator only reads saved JSON/NPZ endpoints, adds optional `results/*-arc` and `expanded-results` endpoints when present, and writes this report, `iteration-summary.json`, `window-comparison.csv` and `iteration-*.png`. No model evaluation or new fit occurs.

## Latest checkpoint and outstanding work

The [checkpoint](CHECKPOINT.md) adds the separate bounded numerical-cleanup audit, the failed training-only calibration-bootstrap smoke, the complete expanded-window plot, and the next experiments. These are not silently substituted into the original result tables above. The recovery goal remains active.
