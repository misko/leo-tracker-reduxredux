# Controlled relative timing prior sensitivity

Neither tighter prior recovers window 003. For the fitted-c profile, 2 / 1 / 0.5 s priors yield 422 / 347 / 339 window associations and lose 742 / 851 / 1,177 original assignments. Tightening relative timing is not an overall support-recovery fix in this controlled experiment.

This full-data warm-start development experiment changes only relative timing prior σ from 2 s to 1 s or 0.5 s. Common σ stays 3 s; observations, ordered candidate banks, original causal TLE snapshots, calibration/nuisance priors, all physical bounds and original seed policy stay fixed. No configured station coordinate enters fitting or proposal selection. This is not validation or evidence of generalization to a new position.

Each profile/continuation and fitted-c/c=0 arm gets the same 1,000 full-objective/120 s cap. Profile uses at most 200 additional orbit projections (two declared 100-node searches), reported separately from full-objective calls. The σ2 endpoints are reused only after sealed artifact, source, ordered bank, algorithm and budget checks; extra polished endpoints are not substituted. The 40 new fits and 20 reused endpoints complete a 60-record matrix.

Snapshot: 60/60 records, 40/40 new fits and 20/20 reused records. Missing outputs remain in fixed denominators.

| Relative σ s | Arm | Method | Complete /5 | Full associated /20,084 | Window associated /693 | New / lost original full support | Assigned RMS Hz | Retained intersection RMS original → variant Hz | Major windows /15 | Strict passes /5 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 2 | fitted-c | profile | 5 | 13784 | 422 | 3304 / 742 | 155.82 | 157.06 → 152.44 | 6 | 4 |
| 2 | fitted-c | continuation | 5 | 11226 | 95 | 18 / 14 | 160.38 | 159.97 → 160.02 | 0 | 4 |
| 2 | zero-c | profile | 5 | 12311 | 292 | 3529 / 2440 | 169.40 | 155.07 → 168.95 | 3 | 3 |
| 2 | zero-c | continuation | 5 | 9864 | 95 | 865 / 2223 | 177.11 | 154.49 → 174.34 | 0 | 4 |
| 1 | fitted-c | profile | 5 | 13366 | 347 | 2995 / 851 | 154.94 | 156.38 → 152.09 | 4 | 3 |
| 1 | fitted-c | continuation | 5 | 11229 | 100 | 143 / 136 | 159.41 | 158.61 → 158.19 | 0 | 4 |
| 1 | zero-c | profile | 5 | 11697 | 304 | 3029 / 2554 | 169.92 | 155.49 → 167.91 | 3 | 4 |
| 1 | zero-c | continuation | 5 | 9831 | 113 | 1153 / 2544 | 176.19 | 153.99 → 174.43 | 0 | 2 |
| 0.5 | fitted-c | profile | 5 | 12302 | 339 | 2257 / 1177 | 159.70 | 157.33 → 156.10 | 5 | 3 |
| 0.5 | fitted-c | continuation | 5 | 10212 | 286 | 2014 / 3024 | 156.99 | 155.26 → 153.41 | 4 | 3 |
| 0.5 | zero-c | profile | 5 | 10298 | 299 | 2345 / 3269 | 173.56 | 155.51 → 172.92 | 3 | 5 |
| 0.5 | zero-c | continuation | 5 | 9617 | 142 | 1939 / 3544 | 174.39 | 154.22 → 174.13 | 1 | 4 |

For the fitted-c profile, the 2 / 1 / 0.5 s priors produce 13784 / 13366 / 12302 full-recording associations, 422 / 347 / 339 window associations, and 742 / 851 / 1177 losses of original assignments. These counts test whether tighter timing regularization reduces displaced support; lower relative timing RMS alone is not evidence of recovery.

The specifically requested region 003 has 0 / 0 / 0 associations out of its unchanged 27 observations at 2 / 1 / 0.5 s. Neither tighter prior recovers that window.

New/lost and intersection statistics use the unchanged original fitted-c assignments as the reference in every arm, including c=0. These are classification changes, not satellite identity accuracy. Major windows require at least 80% net restoration of originally missing assignments, subtracting losses. All 15 original window counts remain fixed.

Reused sigma=2 JSON retains its sealed original seed-comparison fields, which for c=0 may reference the c=0 seed. Use the consistently recomputed `summary.json` and `windows.csv` for cross-prior new/lost comparisons; their reference is always the original fitted-c inventory.

## All window counts: fitted-c profile

| Window | Source | All rows | Original | σ2 | σ1 | σ0.5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 001 | S01 | 86 | 13 | 79 | 47 | 80 |
| 002 | S01 | 35 | 1 | 11 | 13 | 1 |
| 003 | S01 | 27 | 0 | 0 | 0 | 0 |
| 004 | S02 | 44 | 6 | 10 | 9 | 8 |
| 005 | S02 | 33 | 1 | 31 | 6 | 4 |
| 006 | S02 | 72 | 12 | 33 | 14 | 12 |
| 007 | S03 | 54 | 16 | 54 | 54 | 54 |
| 008 | S03 | 50 | 8 | 48 | 48 | 48 |
| 009 | S03 | 34 | 4 | 34 | 34 | 34 |
| 010 | S04 | 46 | 2 | 25 | 28 | 5 |
| 011 | S04 | 43 | 9 | 15 | 7 | 10 |
| 012 | S04 | 66 | 14 | 16 | 18 | 17 |
| 013 | S05 | 28 | 1 | 22 | 22 | 22 |
| 014 | S05 | 39 | 3 | 11 | 15 | 11 |
| 015 | S05 | 36 | 6 | 33 | 32 | 33 |

`windows.csv` and `summary.json` retain counts, losses, intersection RMS and net restoration for every window, method and RF arm.

## Frequency score and timing, separated from position

**Penalized objectives differ across prior widths and must not be ranked across rows with different σ.** Frequency NLL excludes the timing penalty and is shown separately. A lower frequency NLL still does not establish better geographic accuracy.

| Relative σ s | Arm | Method | Frequency NLL sum | Penalized J within this prior only | Relative timing RMS s (215 candidates) | Full objective calls | Extra orbit projections |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2 | fitted-c | profile | 222582.03 | 225111.41 | 7.47 | 4022 | 1000 |
| 2 | fitted-c | continuation | 231431.85 | 234641.17 | 9.14 | 409 | 0 |
| 2 | zero-c | profile | 230955.51 | 233594.00 | 8.13 | 4322 | 1000 |
| 2 | zero-c | continuation | 239621.87 | 242658.21 | 8.85 | 2121 | 0 |
| 1 | fitted-c | profile | 223508.24 | 228197.18 | 5.83 | 4158 | 1000 |
| 1 | fitted-c | continuation | 231373.30 | 240948.92 | 8.93 | 1813 | 0 |
| 1 | zero-c | profile | 232804.19 | 237381.16 | 5.71 | 4177 | 1000 |
| 1 | zero-c | continuation | 239630.21 | 248181.77 | 8.48 | 2102 | 0 |
| 0.5 | fitted-c | profile | 227751.76 | 235452.27 | 3.94 | 3916 | 1000 |
| 0.5 | fitted-c | continuation | 236302.17 | 243959.62 | 4.02 | 2469 | 0 |
| 0.5 | zero-c | profile | 238052.22 | 243829.73 | 3.41 | 4129 | 1000 |
| 0.5 | zero-c | continuation | 240775.01 | 255375.18 | 5.66 | 2531 | 0 |

| Source | Relative σ s | Arm | Profile configured-reference distance km | Relative timing RMS s | Lost original assignments | Outside-window losses | Projected KKT | Strict pass |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| S01 | 2 | fitted-c | 132.47 | 10.26 | 305 | 304 | 0.004055 | False |
| S01 | 1 | fitted-c | 132.96 | 8.31 | 359 | 351 | 0.000169 | True |
| S01 | 0.5 | fitted-c | 128.03 | 5.33 | 457 | 456 | 0.000109 | True |
| S01 | 2 | zero-c | 133.32 | 10.69 | 360 | 358 | 0.040627 | False |
| S01 | 1 | zero-c | 133.19 | 8.34 | 354 | 351 | 0.000315 | True |
| S01 | 0.5 | zero-c | 122.97 | 4.76 | 613 | 610 | 0.000211 | True |
| S02 | 2 | fitted-c | 135.38 | 8.98 | 146 | 141 | 0.000154 | True |
| S02 | 1 | fitted-c | 133.48 | 5.73 | 177 | 169 | 0.003701 | False |
| S02 | 0.5 | fitted-c | 131.73 | 4.70 | 222 | 208 | 0.002466 | False |
| S02 | 2 | zero-c | 134.43 | 9.66 | 600 | 592 | 0.001214 | False |
| S02 | 1 | zero-c | 134.05 | 5.30 | 699 | 686 | 0.000987 | True |
| S02 | 0.5 | zero-c | 133.17 | 3.76 | 884 | 869 | 0.000495 | True |
| S03 | 2 | fitted-c | 3.28 | 3.42 | 47 | 47 | 0.000845 | True |
| S03 | 1 | fitted-c | 3.30 | 3.19 | 46 | 46 | 0.000498 | True |
| S03 | 0.5 | fitted-c | 3.28 | 1.71 | 45 | 45 | 0.000448 | True |
| S03 | 2 | zero-c | 3.75 | 5.14 | 918 | 904 | 0.000494 | True |
| S03 | 1 | zero-c | 2.85 | 4.15 | 956 | 944 | 0.001285 | False |
| S03 | 0.5 | zero-c | 3.79 | 2.13 | 996 | 980 | 0.000196 | True |
| S04 | 2 | fitted-c | 260.09 | 6.18 | 126 | 122 | 0.000635 | True |
| S04 | 1 | fitted-c | 260.80 | 5.42 | 119 | 111 | 0.001611 | False |
| S04 | 0.5 | fitted-c | 257.00 | 3.89 | 206 | 202 | 0.000646 | True |
| S04 | 2 | zero-c | 259.86 | 7.10 | 347 | 339 | 0.000164 | True |
| S04 | 1 | zero-c | 264.74 | 4.71 | 330 | 323 | 0.000094 | True |
| S04 | 0.5 | zero-c | 261.05 | 3.13 | 527 | 521 | 0.000253 | True |
| S05 | 2 | fitted-c | 4.71 | 5.02 | 118 | 117 | 0.000113 | True |
| S05 | 1 | fitted-c | 5.78 | 4.67 | 150 | 150 | 0.000268 | True |
| S05 | 0.5 | fitted-c | 5.03 | 1.66 | 247 | 246 | 0.001922 | False |
| S05 | 2 | zero-c | 9.68 | 5.07 | 215 | 215 | 0.000197 | True |
| S05 | 1 | zero-c | 10.08 | 4.60 | 215 | 215 | 0.000255 | True |
| S05 | 0.5 | zero-c | 5.46 | 1.86 | 249 | 248 | 0.000337 | True |

Position refers to the existing operator-configured station, not surveyed independent truth. Strict acceptance requires feasible bounds and projected KKT≤0.001. All nonstationary iterates and original support losses remain visible. Shared common/relative timing is a parameter decomposition, not a measurement of physical orbital-clock error.

![Coverage, frequency and configured-reference position](timing-comparison.png)

![Common and relative timing histograms](timing-histograms.png)

![Every original window](timing-windows.png)

Six component tests cover prior gradients/decomposition, independent model/seed copies, and consistent tightened scores in the full model, exact Profiles and shared refit. Report verification checks frozen observation ordering, original window denominators, saved association totals and RMS. The first two smoke endpoints used an unbatched launcher; `provenance/run_timing_smoke.py` preserves its exact recorded source hash. The later launcher only batches work by source to reuse read-only contexts; the scientific `run` function is identical. No production modules, RF corpus or sealed reports change.
