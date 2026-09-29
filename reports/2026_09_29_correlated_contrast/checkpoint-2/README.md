# Correlated contrast localization

Completed 12/36 planned units; selected numerical audits pass for 12/12 completed units. Pending and failed units remain explicit. No blanket sub-km claim follows.

Errors are horizontal metres to the exposed unsurveyed reference. The comparison changes correlation in both satellite and background contrast densities. corr10 compares with published q020; corr10_c40 compares with published soft40. Position and one timing per scan are fitted using training data only.

| Arm | Dataset | Scans | Passed blocks | Median error (m) |
|---|---|---:|---:|---:|
| corr10 | DS7 | 4 | 3/3 | 2487.6 |
| corr10 | DS7 | 8 | 3/3 | 1971.8 |
| corr10 | DS8 | 4 | 3/3 | 1626.0 |
| corr10 | DS8 | 8 | 3/3 | 1936.5 |
| corr10 | DS9 | 4 | 0/3 | Incomplete |
| corr10 | DS9 | 8 | 0/3 | Incomplete |
| corr10_c40 | DS7 | 4 | 0/3 | Incomplete |
| corr10_c40 | DS7 | 8 | 0/3 | Incomplete |
| corr10_c40 | DS8 | 4 | 0/3 | Incomplete |
| corr10_c40 | DS8 | 8 | 0/3 | Incomplete |
| corr10_c40 | DS9 | 4 | 0/3 | Incomplete |
| corr10_c40 | DS9 | 8 | 0/3 | Incomplete |

| Panel / arm | Status | Qualified starts | Error (m) | Matched baseline (m) | Held change (nats) |
|---|---|---:|---:|---:|---:|
| DS7_early_4_corr10 | Pass | 4/4 | 2487.6 | 2855.8 | +2578.412 |
| DS7_early_8_corr10 | Pass | 4/4 | 2872.5 | 2286.0 | +4842.432 |
| DS7_middle_4_corr10 | Pass | 3/4 | 3218.6 | 2196.1 | +3366.332 |
| DS7_middle_8_corr10 | Pass | 4/4 | 1971.8 | 1603.6 | +7034.100 |
| DS7_late_4_corr10 | Pass | 4/4 | 739.6 | 1391.6 | +2543.979 |
| DS7_late_8_corr10 | Pass | 4/4 | 1945.2 | 2023.6 | +5361.910 |
| DS8_early_4_corr10 | Pass | 4/4 | 1626.0 | 1069.5 | +3199.525 |
| DS8_early_8_corr10 | Pass | 4/4 | 801.7 | 1435.7 | +6029.179 |
| DS8_middle_4_corr10 | Pass | 4/4 | 661.9 | 2473.8 | +3166.890 |
| DS8_middle_8_corr10 | Pass | 4/4 | 2234.7 | 2130.8 | +6013.363 |
| DS8_late_4_corr10 | Pass | 4/4 | 2733.6 | 3504.7 | +3880.195 |
| DS8_late_8_corr10 | Pass | 4/4 | 1936.5 | 1721.1 | +6975.561 |
| DS9_early_4_corr10 | Pending | — | — | — | — |
| DS9_early_8_corr10 | Pending | — | — | — | — |
| DS9_middle_4_corr10 | Pending | — | — | — | — |
| DS9_middle_8_corr10 | Pending | — | — | — | — |
| DS9_late_4_corr10 | Pending | — | — | — | — |
| DS9_late_8_corr10 | Pending | — | — | — | — |
| DS7_early_4_corr10_c40 | Pending | — | — | — | — |
| DS7_early_8_corr10_c40 | Pending | — | — | — | — |
| DS7_middle_4_corr10_c40 | Pending | — | — | — | — |
| DS7_middle_8_corr10_c40 | Pending | — | — | — | — |
| DS7_late_4_corr10_c40 | Pending | — | — | — | — |
| DS7_late_8_corr10_c40 | Pending | — | — | — | — |
| DS8_early_4_corr10_c40 | Pending | — | — | — | — |
| DS8_early_8_corr10_c40 | Pending | — | — | — | — |
| DS8_middle_4_corr10_c40 | Pending | — | — | — | — |
| DS8_middle_8_corr10_c40 | Pending | — | — | — | — |
| DS8_late_4_corr10_c40 | Pending | — | — | — | — |
| DS8_late_8_corr10_c40 | Pending | — | — | — | — |
| DS9_early_4_corr10_c40 | Pending | — | — | — | — |
| DS9_early_8_corr10_c40 | Pending | — | — | — | — |
| DS9_middle_4_corr10_c40 | Pending | — | — | — | — |
| DS9_middle_8_corr10_c40 | Pending | — | — | — | — |
| DS9_late_4_corr10_c40 | Pending | — | — | — | — |
| DS9_late_8_corr10_c40 | Pending | — | — | — | — |

Among audited comparisons, 6/12 have lower nominal geographic error; 12/12 improve held prediction. These are dependent explored panels, not independent trials.

60 child receipts: 375.79 seconds summed wall time; peak RSS 702,284 KiB. Nonzero child exits: 0. No completed fits were retried.

Ten prelaunch tests pass. The summarizer reconstructs qualification, training selection and all derivative gates; zero-decay replays and matching observation identities are checked. Generic-only selections and every selected audit remain in summary.json. Local convergence does not prove a global optimum or correct satellite identity.

The inherited origin is already 809 m from the reference. Neither nominal sub-km errors nor higher held frequency density establish surveyed accuracy, calibrated uncertainty or unseen-site transfer. No new RF, IQ processing, propagation or production changes.

![Audited matched errors](comparison.png)

[Protocol](../PROTOCOL.md), [tests](../tests.log), [full results](summary.json).
