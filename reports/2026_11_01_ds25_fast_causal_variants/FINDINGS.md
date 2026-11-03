# Findings: DS25's 34 fast comparison scans

The broader causal TLE window recovers one additional source but does not improve position accuracy on this cohort. Keep the current production default. There is no evidence here to promote the ±30-second phase range or recency penalty for localization.

These are the 34 DS24 fast recordings paired with DS25's adaptive cohort, as confirmed by the user. There are 25 retained position outcomes: 24 completed recovery comparisons and one explicitly unchanged incumbent after a recovery audit failure. Nine acquisitions have no existing public GLRT input. The failed recovery is included in the statistics, not silently dropped. All observations are from the previously confirmed evaluation site; this is not a new-site generalization test.

## Position and association

The following table uses fitted c. All five methods use the same 25 scans and 113,227 native GLRT points.

| Method | Mean error, m | Median, m | P90, m | Associated GLRT | Added points |
|---|---:|---:|---:|---:|---:|
| Current ALGO05 | 1,175.17 | 1,016.75 | 2,013.27 | 72.727% | 0 |
| 48 h / ±15 s recovery | 1,175.17 | 1,016.75 | 2,013.27 | 72.727% | 0 |
| 72 h / ±15 s recovery | 1,175.46 | 1,016.75 | 2,013.27 | 72.782% | 62 |
| 72 h / ±30 s recovery | 1,175.46 | 1,016.75 | 2,013.27 | 72.782% | 62 |
| 72 h / ±30 s + recency | 1,175.46 | 1,016.75 | 2,013.27 | 72.782% | 62 |

The controlled c=0 comparison has the same accepted points. Its mean changes from 1,162.15 to 1,162.19 m; median 1,024.28 m and P90 2,000.40 m remain unchanged. Fitting c does not improve mean localization error on this cohort. Frequency objectives are recorded separately in `frequency-fit-ablation.json`; adding observations changes the objective's support, so the absolute before/after objective is not a localization metric.

![Both c arms: nearly coincident error distributions](position_error_distributions.png)

![Per-scan position error and association](per_scan_results.png)

## What the older TLE recovers

DS24-0079 RX2/CH3 contains a 62-point source spanning 13.92–56.45 seconds. NORAD **63045** passes the fixed catalogue screen, random whole-block validation and both physical-fit arms using a **50.24-hour-old causal TLE**. It was outside the 48-hour window. The fitted phase correction is approximately −12.6 seconds, and the physical residual RMS is 33.49 Hz with fitted c, 35.12 Hz with c=0. The residual plot retains an isolated roughly −200 Hz point; no points were manually removed.

The scan's association rises from **2,933/4,492 (65.29%)** to **2,995/4,492 (66.67%)**. Its fitted-c error changes from **877.94 to 885.06 m**; c=0 changes from **861.38 to 862.41 m**. The matched no-addition controls remain within 0.01 m of the saved baseline, so the small changes are not explained by merely continuing the optimizer. These are supported extra points, but they provide no measured accuracy gain here.

Widening phase to ±30 seconds produces essentially the same fit. The fixed recency penalty changes no accepted decision. Identity confidence remains conditional on the bounded search and physical model; this is not an exhaustive proof of satellite uniqueness.

![Recovered source, corrected orbit and residual](curves/DS24-0079.png)

## What limits further recovery

| Scan | Proposed satellite | Points | Blocking evidence |
|---|---:|---:|---|
| DS24-0019 | 69445 | 53 | Candidate fits pass, but the c=0 no-addition control does not declare optimizer convergence. |
| DS24-0077 | 100418 | 34 | Candidate fits pass, but the c=0 no-addition control does not declare optimizer convergence. |
| DS24-0083 | 67624 | 27 | Candidate c=0 optimizer fails. Controls additionally fail optimizer checks, and c=0 fails exact incumbent replay and owner preservation. |
| DS24-0091 | No adopted proposal | — | Bounded upstream recovery has 37/38 process receipts; its verified original incumbent is retained in every method. |

The final control audit for DS24-0083 is more restrictive than the candidate-only optimizer result discussed during execution. It must not be treated as a harmless optimizer-status failure. Full trial curves and gate details are in [the curve atlas](CURVES.md) and [the complete report](README.md).

Nine screened fragments across seven other scans nominate satellites already present in their baseline. This experiment leaves existing-family extension unchanged; these exclusions are not evidence that those curves lack a satellite match.

The next focused work should separate numerical control failures from genuine identity/ownership problems, and test the nine existing-family extensions under the same causal and matched-c rules. Do not bypass gates because an error measured against GPS looks better. The wider TLE window can remain a recovery experiment, but these results do not establish a localization improvement.

## Validation

All 250 scan × method × c-arm rows pass accounting, point-identity and incumbent-preservation checks. Baseline likelihood/ownership replay succeeds for all 25 retained position outcomes. The causal catalogue audit verifies the unchanged nominal TLE bytes and both epoch and collection cutoffs. The inference seal precedes geographic error reporting. Adapter, screening and physical-model tests total 31 passing tests. Production was not changed.
