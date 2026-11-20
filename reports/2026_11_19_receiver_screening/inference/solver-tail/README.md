# Position solver tail

The full roof panel isolated two recordings where the secant optimizer increased position error by more than 10% compared with the compact bounded solver. DS26-0152 incurred roughly 76 m and 96 m more error in the zero and fitted calibration arms. DS26-0283 incurred about 11 m more error on errors near 50 m. DS26-0092 moved the other way, improving by 1.80 km and 1.39 km. These are three deliberately selected diagnostic recordings. The confirmation cohort comes from the other DS26 corpus IDs and is reported separately.

The centered Armijo check runs when the projected step in the existing bounded Armijo solver is at most 20 m. It computes a fresh Jacobian of the original residual using 1 m differences along each feasible axis. At a tile edge it uses the available side of the derivative. It stops at a projected step of at most 1 m and allows at most two centered checks. Each proposed update must strictly decrease the original objective and pass the Armijo test. Rejected proposals contract by a factor of two, with at most six trials per check. The original five outer orbit-phase updates, factor and catalogue inputs, and all association and acceptance rules stay in force through the complete compact cavity pipeline.

The check adds at most 21 residual evaluations each time it triggers. On the winning zero-calibration branch of DS26-0152, the p95 conditional RF slope was 4.81 Hz/km, or about 0.096 Hz across 20 m and 0.0048 Hz across 1 m. Median nominal point noise was 63.3 Hz. The finer stop tests numerical decisions made from the aggregate objective.

The measured boundary starts at frozen native detector observations and ends at the v5 cavity prediction. The run includes track discovery and the 25 km tile search. Each fresh process uses one numerical thread and CPU 8 or 9. Archived stock, secant and original controls bind the same observation, causal catalogue and request digests and were timed in their own runs. Worker wall times therefore include those runs' host conditions. The plan records source digests, the fixed 480 s worker limit, and the salted ID selection fixed before scoring.

Trace comparisons use the curved track component IDs, candidate indexes, alias integers, exact support-mask digests and predictive linear entries. For each arm the stage snapshots retain local coordinates, the available objective and RF RMS. The cavity snapshot includes the offered predictive gains, adopted replacements and corrected decision gain when the stage runs. A small coordinate difference on matched support can track numerical convergence. A different assignment, observation mask or offered or adopted proposal changes the stage entering later fits. The final frequency RMS records measured fit quality. Position error is scored separately against the roof reference.

## Diagnostic cases

**DS26-0152.** Stock and secant selected the same first initial branch, about 49 objective units clear of the next branch, with the same track assignments, aliases and support. The initial endpoints diverged by 5.7 m after one orbit-phase pass and by 12.7 m after five. Conservative recovery reassigned the RX2 channel 8 track T004 from candidate index 486 to 927 and increased retained curved support from 3,145 to 3,170 observations. The history policy kept that changed assignment, used 3,033 curved observations versus 3,020, and used 630 predictive linear observations versus 652. Both runs rejected the signed refit and had zero positive cavity nominations. The final endpoints were 87.9 m and 98.8 m apart, and secant lowered RF RMS by 0.225 Hz and 0.300 Hz. The geographic loss follows changed conservative and predictive selections after a small initial convergence difference. The centered check reproduced the stock assignments, curved masks and linear entries. Its errors were 674.23 m and 842.85 m, compared with 674.22 m and 843.25 m for stock and 750.34 m and 939.53 m for secant.

**DS26-0283.** Track assignments, aliases, masks and gates matched throughout. The two runs both retained 2,327 curved and 547 predictive linear observations, rejected the signed refit and had no positive cavity nominations. The initial difference was 8.0 m and the final endpoints were 13.7 m and 14.2 m apart. Secant stopped at its 20 m projected threshold. It increased the matched final objective by about 0.002 in each arm and increased RF RMS by 0.00020 Hz and 0.00026 Hz. Geographic error rose from 45.85 m to 56.38 m and from 52.07 m to 63.40 m. On this case the loss is numerical convergence on the same selected evidence. The centered check gave 45.93 m and 52.20 m with the same assignments, masks and gates.

**DS26-0092.** The winning initial branch, conservative assignment and mask, history assignment and mask, and all predictive linear entries matched. The two runs rejected the signed refit. Their fitted endpoints entering the cavity stage differed by 8.3 m and 7.0 m. Both proposed and adopted the sole positive family replacement, candidate index 119 to 442, with roughly 265.22 units of nomination gain. The corrected selection gain after refitting was 121.83 for stock and 142.71 for secant. The cavity endpoints differed by 2.16 km and 2.01 km, and secant reduced the geographic errors from 2.778 to 0.977 km and from 2.500 to 1.108 km. RF RMS went from 79.859 to 79.754 Hz and from 79.815 to 79.828 Hz. The large divergence first appears during the cavity refit of the same replacement. Stock exhausted its iteration budget on 16 of 90 optimizer calls across the pipeline and secant exhausted none. The trace establishes the stage and the selected replacement. Resolving its internal basin or stopping mechanism would require the replacement aliases and cavity phase-pass trajectories. The centered check reproduced stock's cavity endpoint and corrected gain. It gave up the 1.80 km and 1.39 km secant improvements while using 1,706 residual evaluations against stock's 6,170.

| Diagnostic recording | Fresh stock wall (s) | Fresh secant wall (s) | Fresh centered Armijo wall (s) |
| --- | ---: | ---: | ---: |
| DS26-0152 | 196.82 | 121.81 | 115.45 |
| DS26-0283 | 94.86 | 71.61 | 78.93 |
| DS26-0092 | 431.26 | 121.29 | 154.83 |

The centered configuration restores the stock accuracy on both measured losses and forfeits secant's larger beneficial result. The intervention changes the numerical method as well as the stopping threshold relative to secant. A matched plain Armijo control would isolate the contribution of the centered check.

## Independent confirmation

All four sealed recordings returned both arms. The centered results stayed within 0.507 m of the compact stock coordinates and within 0.246 m of their position errors. Compact stock and original no-repair v5 had identical endpoints here. The greatest error difference between secant and stock was 13.08 m. Positive calibration deltas indicate higher error or RMS, respectively.

| Recording | Original and stock error, c=0 / fitted c (m) | Secant error (m) | Centered Armijo error (m) | Centered fitted-minus-zero error (m) | Centered fitted-minus-zero RF RMS (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0313 | 1299.71 / 1321.43 | 1307.88 / 1315.44 | 1299.71 / 1321.18 | +21.47 | +0.00094 |
| DS26-0080 | 1077.50 / 1131.11 | 1066.43 / 1118.02 | 1077.62 / 1131.18 | +53.56 | −0.00343 |
| DS26-0078 | 769.65 / 790.70 | 767.96 / 789.55 | 769.69 / 790.74 | +21.05 | −0.01408 |
| DS26-0231 | 781.69 / 751.55 | 782.07 / 752.14 | 781.57 / 751.47 | −30.10 | −0.06463 |

The fitted calibration reduced RF RMS in three of four recordings and reduced position error in one. Across all eight endpoints, centered and compact stock RF RMS differed by at most 0.000023 Hz. The original no-repair execution reports its own RF RMS under its aggregated observation support. Its fitted-minus-zero RF differences are in the score archive.

Median worker wall time was 111.75 s for centered Armijo, 127.16 s for archived compact stock, 79.06 s for archived secant and 313.04 s for archived original no-repair v5. These are separate replay timings. Centered Armijo used 4,177 residual evaluations across 280 calls compared with 1,937 evaluations for secant. The centered 1 m check passed on 245 calls and reached its two-check limit on 35.

All 13 fresh scheduled jobs completed within the worker limit. The published seal covers the full replays after correcting a preflight trace formatter that expected numeric component IDs. The solver arithmetic and confirmation selection were fixed before that formatter correction. The 15 focused Armijo and secant tests pass. The measured source files retain their byte hashes, including the import ordering and line lengths flagged by Ruff.
