# Published grid curvature did not identify which DS30 fixes degraded

Among 19 shared scored fixes, the candidate’s low-curvature rank had Kendall tau-b **−0.041** with the candidate-minus-installed horizontal error at fixed `c = 0` and **−0.088** at fitted `c`. It tracked the installed build’s low-curvature rank much more closely (**+0.719 / +0.696**). The frozen weakest-direction threshold flagged **every candidate fix**. These results do not support a selective 20 ms retry based on this diagnostic. [Frozen protocol](ds30-grid-triage-protocol.md) · [Sealed prediction](measurements/ds30-grid-triage-prediction.json.gz) · [Scored pairs](measurements/ds30-grid-triage-scored.json.gz)

The first 24 official pairs follow the recorded execution order through DS30-0147. DS30-0049 supplied the original weak-geometry example and was set aside before reading these grids. The remaining 23 inputs passed the original raw-authority, causal archive, inventory, chronological pair and common offer checks, including the independently verified DS30-0452 relocation. The candidate returned 20 paired fixes and withheld three. Installed returned 19 paired fixes, withheld three and recorded one solver failure on DS30-0397. All 20 returned candidate grids had finite complete 0.5 km stencils in both arms, and all 19 returned installed grids did too. The error ranks use the 19 shared fixes. No omitted or translated offers enter the field scores.

| Calibration | Tau-b with error excess | Tau-b with candidate absolute error | Tau-b with installed absolute error | Tau-b with installed low curvature | Median excess for weakest 7 | Median excess for other 12 | Candidate worse, weakest / other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed `c = 0` | −0.041 | −0.041 | −0.111 | +0.719 | +0.240 km | +0.362 km | 5/7 · 9/12 |
| Fitted `c` | −0.088 | −0.053 | −0.041 | +0.696 | +0.219 km | +0.352 km | 4/7 · 9/12 |

The weakest third’s median absolute installed/candidate errors were **0.466/0.775 km** at fixed zero and **0.410/0.718 km** fitted. The respective other 12 medians were **0.805/1.063 km** and **0.874/1.007 km**. Removing the previously audited DS30-0086 translation control and DS30-0220 initializer case leaves 17 shared fixes. The weakest-six split becomes sensitive to those omissions (median excess **0.361 vs 0.250 km** fixed and **0.267 vs 0.202 km** fitted), while the primary rank stays slightly negative (**−0.074 / −0.103**). The installed curvature rank link remains **+0.706 / +0.676**. The first 19 cases already contributed to earlier reports and these are development statistics from one site.

## Full retry cost at the one frozen threshold

The smallest candidate Hessian eigenvalue stayed below the **11.982 objective units/km²** threshold on both arms of every returned fix. The arm maxima were **11.318 / 11.302**. The screen therefore retries 20/23 captures, with the three original candidate withholds left in place. Returning the installed result after each replay restores baseline threshold counts, and removes the one fix that only the candidate produced. The cost adds each selected capture’s measured full installed run to the already paid candidate run. All successful or withheld runs include common publication verification. The recorded DS30-0397 installed failure cost **90.017 s wall / 77.353 s CPU** through exit. No data reuse or beneficial partial 20 ms acquisition is assumed. [Per-recording clocks and decisions](measurements/ds30-grid-triage-scored.json.gz)

| Strategy | Sum wall | Sum CPU | Fixes per arm | Within 1 km, fixed / fitted | Within 2 km, fixed / fitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Installed | 2,203.098 s | 1,935.468 s | 19/23 | 13 / 15 | 19 / 19 |
| Candidate | 1,337.838 s | 1,237.409 s | 20/23 | 10 / 11 | 18 / 18 |
| Candidate plus curvature-triggered installed retry | 3,533.696 s | 3,167.614 s | 19/23 | 13 / 15 | 19 / 19 |

The retry strategy’s wall/CPU sum ratios to installed are **1.604 / 1.637** and its median paired ratios are **1.574 / 1.606**. Keeping the same 20 selections would allow an average incremental **43.263 s wall / 34.903 s CPU** per retry simply to match installed, versus the measured full replay averages of **109.793 / 96.510 s**. At half installed time, the candidate already needs savings of **236.289 s wall / 269.676 s CPU** before paying for any retry. Partial acquisition after a weak result would have its own costs and might change owner support and location. This study observes neither an acquisition-stage signal nor the accuracy effect of targeted extra data. The archived curvature is conditional on a completed fit and its fixed published support.

## Prospective status and custody

The next three consecutive assigned cases **DS30-0010, DS30-0444 and DS30-0073** were frozen before scoring and all remain pending for the prospective aggregate. The combined export had DS30-0010 deferred for storage and the other two pending. No partial prospective score was computed. [Reserved predictions](measurements/ds30-grid-triage-pending.json.gz)

Protocol commit `91297a1b4`. The verified combined export SHA-256 is `db3e4869a95d2f8279873723158c4bd0e8ee93cbc228f5123ec58317712babc9`. It binds the plan, ordinary ledger generation and relocation proof via seal SHA-256 `9a39a071caa2469be3aadeea358f7dc51709be55e62b03ed299d1ace7ca01818`. Candidate-only predictions were sealed at `fdd2e02fde91f3c7f3a399b40ee8d142d9dc10ca1991c28bac370341c6396763` before the survey outcome join. That join output SHA-256 is `9d14cb672878b89d26746a79b32c3a50509166852ee70e277940a124e0dcf6c2` before compression. No coordinates are exported. Eight component and adjacent tests passed. The readout opened no waveforms or orbit bodies and launched no solver. [Prediction and score entry](ds30_grid_triage.py) · [Tests](../../../tests/pipeline_eval/test_ds30_grid_triage.py)
