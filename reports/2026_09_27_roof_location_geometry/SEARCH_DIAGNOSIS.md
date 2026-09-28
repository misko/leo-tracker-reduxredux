# Search-policy confound and bounded follow-up

The original four-scan geographic comparison completed: geometry changes the selected location in **0/8** scan/prior cases. See `distance_results.json`. These are real outputs, but they do not establish that reception geometry lacks spatial information.

Trace inspection found that the installed generic search assigns priority zero to a boundary-intersecting cell with no measured center or measured parent. Its descendants can inherit the same zero priority. With positive likelihood losses, those chains precede measured interior cells. At the frozen 160-point budget and seven grid levels, this consumes refinement without adequate objective-responsive interior exploration. All eight scan/prior comparisons evaluated exactly the same 160 coordinates in both arms. Reno's evaluated depth counts are always 80,4,4,4,16,24,28 regardless of scan or objective. Gaussian residual-tail concentration is also real, but cannot be claimed as the sole cause of the bad distance errors.

Direct trace counts: Sacramento spends 136/160 evaluations before the first nonzero-priority pop; Reno spends 160/160 and never reaches one. These counts include initial coarse evaluations, not just added refinement points.

## Frozen repair-only experiment

Before changing the noise model, isolate search behavior. `run_measured_search.py` retains the original Gaussian model, all calibration coefficients, zero timing, training-only top3 selection, track weights, independent priors, 160-point budget, and grid levels. The only change is the research search implementation in `measured_search.py`.

Each boundary-intersecting cell is evaluated at a representative inside both its square and the prior disk. Interior cells use their centers. Every queued priority is an actual measured objective; there is no default zero score for an unevaluated boundary. All initial intersecting cells receive measured coverage, and subsequent best-first refinement uses measured scores. This remains a heuristic with finite budget, not a proof of global convergence.

Synthetic tests verify interior-bowl recovery below 2 km, objective-dependent refinement, valid negative objectives, boundary minimum recovery, radius/cell containment, and budget enforcement. Importantly, the installed search also recovers the simple test bowl to 0.494 km at 160 points; this test does **not** demonstrate that the installed search universally fails. Real traces do contain later nonzero-priority pops. The issue is boundary-first budget allocation, not an absence of all data-driven refinement, and only matched geographic runs can establish its impact here. No production component or original result is changed. Run the four development scans in chronological order, report both priors and both arms, and compare common-inventory winners separately. Ground-truth coordinates are not search inputs. A later disjoint cohort is still required for confirmation after these development iterations.

The Student-t prototype and calibration residual extraction are retained separately. Its search run is paused pending consistent treatment of seed-selected calibration CFOs versus fitted-parameter CFOs. Do not conflate a search-policy repair with an improvement caused by receiver geometry.
