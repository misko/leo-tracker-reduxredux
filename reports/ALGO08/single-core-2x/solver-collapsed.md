# One paired regional fit after broad discovery

The collapsed solver reduced full DS30-0374 solve and grid CPU from **28.69 to 13.46 seconds (2.13×)** and returned both fixes through the normal publication evidence path. Relative to the matched control, geographic error rose by **432 m** with `c = 0` and **416 m** with fitted `c`. This is the first tested solver change in this series with a 15-second saving on that recording. The location regression and reduction in published observation ownership rule out an accuracy-equivalent substitution.

This experiment shortens the complete ALGO08v2 solver schedule. It uses the stock all-catalogue center and corner discovery, applies the two-round `c = 0` screen to each of the up to three ranked assignments, and warm-starts both calibration arms from that selected position and orbit phase. One robust curved-data likelihood then uses genuine-previous orbit support, the causal history prior, and the matched observation mask. Both arms share the same catalogue, support powers, masks and search budget. [Candidate](../../../tools/pipeline_eval/variants/algo08_collapsed.py)

The fit profiles the shared receiver calibration, satellite phases and physical orbit modes at each bounded trial position and refreshes the physical linearization from the fitted phase. The candidate can stop when the largest clipped phase update is at most 0.01 seconds and the regional movement is at most the existing optimizer's 20 m step tolerance. It uses at most five phase rounds on each of up to four common track masks. If either arm rejects a track, the next paired fit drops it in both arms and resumes from the previous fit. The candidate omits the additional conservative/salvage pass, predictive-linear admission, signed-prior retry and cavity nomination. Those cuts can affect associations, frequency fit, availability and position accuracy.

The earlier fixed two-refresh rule worsened geographic accuracy on the 21-recording confirmation. The stricter stability rule removed under 1% of position objective evaluations. A one-center discovery path had a nearly 1.4 km regression on one older recording. This experiment retains the broad original proposals and uses two rounds for branch choice. It moves the budget reduction to the later fit sequence and keeps its measurement and publication checks explicit. [Prior solver comparisons](solver-statistics.md)

The standard evidence path rebuilds the chosen arm, checks its objective and owners, samples the full native variational grid and records the real optimizer path. The comparison loads the same saved detections, causal TLE archive, regional offer and pinned runtime. It times both methods from saved input through the standard grid, using the earlier exact preparation and salvage optimizations in the control. Rendering is measured independently. The published reference coordinates enter the postfit scorer only. [Trial runner](solver_collapsed_trial.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_collapsed.py)

## Small matched checks

The short real case and north-containing simulation each returned both calibration fixes in both methods. Every run computed 179 exact variational grid points and rendered eight verified PNGs. Both candidate fits used two phase refreshes under one shared mask. Associated-observation counts fell from 109 to 90 on the real case and from 302 to 285 on the simulation. Owner hashes differed. Geographic error decreased in all four comparisons. [Real scoring reference](../location-audit/README.md) · [Published simulation scores](../regional-release/blind-scores.csv)

| Saved input | Solve and grid CPU s | Figure CPU s | `c = 0` error, km | Fitted `c` error, km | Solver RMS `c = 0` / fitted, Hz |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 4.697 → 3.636 | 3.354 → 3.303 | 1.644 → 1.314 | 1.662 → 1.581 | 109.375 / 109.479 → 109.545 / 109.505 |
| North containing | 7.248 → 5.574 | 3.904 → 3.811 | 0.745 → 0.187 | 0.711 → 0.223 | 5.380 / 5.173 → 5.388 / 5.151 |

At the short real site, `c = 0` moved from (37.834938, −122.491301) to (37.839223, −122.477462), and fitted `c` moved from (37.835682, −122.494190) to (37.838146, −122.474209). In the containing simulation, zero calibration moved from (47.771519, 16.086911) to (47.773306, 16.098762), and fitted calibration moved from (47.770427, 16.087693) to (47.771907, 16.099762). In the short real case fitted `c` reduced conditional RMS in the candidate while increasing its position error relative to `c = 0`. The resulting fit-quality and geography comparisons use different measured outcomes.

## Full DS30-0374 comparison

DS30-0374 started with 4,157 detections in 125 prepared tracks and 1,407 eligible catalogue entries. The candidate deduplicated seven discovered assignments and ran the two-round screen for the three ranked proposals. It dropped 11 tracks after the initial gate, then three more after the first paired fit. The two paired mask rounds took three and two physical phase refreshes per calibration arm. The candidate published 2,379 associated observations in each arm. The control published 2,905. Neither control case in the initial check, nor this full control, offered a cavity replacement.

| Calibration arm | Control position | Collapsed position | Control → collapsed error (km) | Control → collapsed solver RMS (Hz) |
|---|---|---|---:|---:|
| `c = 0` | 37.849625, −122.464635 | 37.851146, −122.459837 | 1.855 → 2.287 | 101.536 → 101.415 |
| Fitted `c` | 37.850682, −122.463809 | 37.851086, −122.459103 | 1.935 → 2.350 | 101.520 → 101.378 |

The lower solver RMS accompanied fewer observations and worse geographic error in both arms. The 15.22 CPU seconds saved include the reduction in selected evidence work. Both full grids contained 179 exact objective evaluations and completed in 4.33 and 2.32 wall seconds, respectively. The full solve plus grid took 28.94 and 13.62 wall seconds. The eight figure encodes took 5.08 and 4.76 CPU seconds. Taken together, solve, grid and figures took 33.76 and 18.23 CPU seconds. Verification decoded all 16 output PNGs. Timings exclude raw I/Q acquisition and publication I/O.

The earlier exact solver-block extraction had 2,494 curved observations on the full case. The control also published 411 predictive observations. The collapsed estimator publishes curved observations only, with 115 fewer curved points by count. This locates the two most direct omissions to test separately. The numerical comparison did not hold associations or signed priors fixed, so the respective contributions to the position shift remain unresolved. [Earlier curved-block extraction](solver-schur.md)

Both methods returned six of six calibration-arm fixes over the three experimental inputs. The tested offers all contained the reference. Coverage against unsolved inputs, wrong offers and alternative physical stations remains unqualified. Applying the measured 15.22-second reduction to the earlier 93.40-second exact raw-to-grid result would give about 78.18 seconds under additive timing assumptions. That remains above the 64.71-second half-time for the 129.42-second reference. This is a calculation across separate measurements, with full raw trial performance for the collapsed solver still unmeasured.
