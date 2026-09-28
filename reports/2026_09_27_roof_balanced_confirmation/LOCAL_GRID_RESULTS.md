# Equal-coordinate local-ranking diagnostic: primary and sensitivity complete

All four primary grid runs completed (806–851seconds each). Both priors evaluated289 coordinates per recording on the fixed0.5km grid around their own original D estimates. Frozen provenance, exact inventories, and selected-score minima passed the separate reporter. No selected point lies on a grid edge or prior boundary.

| Scan | Prior | Original D km | Local D km | Local joint km |
|---|---|---:|---:|---:|
| 339af | Sacramento | 1.9585 | 2.4237 | 1.9585 |
| 339af | Reno | 2.5797 | 2.4662 | 1.6095 |
| 53ce | Sacramento | 5.0401 | 5.5377 | 5.5132 |
| 53ce | Reno | 5.7013 | 5.7088 | 5.7013 |
| e76c | Sacramento | 3.6049 | 3.0003 | 3.0003 |
| e76c | Reno | 6.5487 | 3.0138 | 3.0138 |
| c9db | Sacramento | 6.1235 | 5.4166 | 5.4166 |
| c9db | Reno | 6.1281 | 5.4218 | 5.4218 |

On identical coordinates, geometry improves4 cases, worsens0, and leaves4 unchanged. Mean error decreases4.123608→3.954377km (about4.1%). Sacramento mean decreases4.094565→3.972148km; Reno4.152652→3.936606km. Unlike the earlier broad-search comparison, these differences are local ranking differences, not different coordinate coverage.

The gains are concentrated in339af (approximately0.465km Sacramento and0.857km Reno). Both53ce gains are tiny (about24m and7m of radial error), despite half-kilometre grid spacing; this reflects different selected directions, not demonstrated metre-level resolution. The paired priors are not independent observations. Four recordings with shared calibration do not establish a population-wide benefit.

Refinement alone also changes errors, sometimes adversely: the original D mean4.710588km becomes local D4.123608km, but339af and53ce Sacramento worsen. Do not attribute all refinement gains to geometry or assume a smaller grid eliminates model bias.

This cohort was already unblinded when the local diagnostic was designed. Therefore this is development evidence only, not an additional untouched confirmation. Distances remain relative to operator-supplied roof coordinates, not surveyed GPS. Grid spacing and interior winners do not establish confidence-interval coverage, global convergence, physical resolution, or production superiority.

The predeclared same-grid reciprocal-pair sensitivity completed for all four recordings (581–598seconds each). The whole-cohort reporter verified the same fixed grids and bindings. Every D and joint selected coordinate is exactly unchanged in all8 cases; no selected point is on a grid edge. Mean errors remain4.123608 versus3.954377km. Thus the measured local-ranking gain survives this particular duplicate-pair sensitivity. This does not establish independence of temporal observations, eliminate calibration mismatch, or provide prospective validation. Any final estimator using this refinement still requires prospective validation under a frozen policy.

Artifacts: `local-grid-distances.json`, `local-grid-dedup-distances.json`, bound `local-grid[-dedup]-scan-fw-*.json`, and `LOCAL_GRID_PROTOCOL.md`.

## Posthoc orientation-reversal control

The already-saved frozen scorer also evaluated reversed directional terms at every grid point. Ranking these scores on exactly the same inventory requires no new evaluations. Relative to the normal directional score, reversal worsens3 cases, improves3 and leaves2 unchanged. It substantially worsens53ce in both priors, but improves e76c in both and339af Sacramento;339af Reno favors the normal direction. This is mixed evidence for directional specificity, not a clean physical-orientation validation.

The control deliberately reverses directional terms inside the frozen model; it is not independently refitted to a reversed physical receiver arrangement. It does not negate the measured local D-versus-joint improvement, but it limits a causal claim that accurate antenna geometry alone explains that improvement. Association selection, residual-model bias and imperfect reception calibration may interact with local ranking. These are hypotheses, not established causes.

All eight cases and the detection-only local control are retained in `local-grid-direction-control.json`; the control implementation has two passing focused tests. Do not select a reversed orientation by observing reference errors or deploy an outcome-tuned mixture from this result.
