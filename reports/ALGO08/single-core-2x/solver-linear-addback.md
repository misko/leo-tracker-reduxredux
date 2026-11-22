# Restore predictive linear evidence to the collapsed regional fit

The add-back recovered **380 of 411** omitted predictive rows on DS30-0374 while keeping a **12.43 CPU-second** solver saving. It recovered about two-thirds of the original geographic regression, leaving error increases of 150 m with `c = 0` and 164 m with fitted `c` relative to ALGO08v2. Both arms returned a fix and completed the full evidence path.

The full DS30-0374 control had 2,494 curved observations and 2,905 final owners. The collapsed fit removed the predictive-linear stage and published 2,379 owners. We chose one add-back before measuring its result. The normal predictive-linear selector nominates entries from the collapsed `c = 0` curved position and its physical posterior. One standard paired `event_position.refit` applies the same mask, powers and causal priors, with five stock phase refreshes per arm. The stock paired predictive gate decides whether to keep that refit. The linear evidence uses the covariance from the curved-only calibration. Conservative salvage, signed-prior retry and cavity continue outside this candidate. [Collapsed baseline](solver-collapsed.md) · [Add-back implementation](../../../tools/pipeline_eval/variants/algo08_collapsed_linear.py)

Both trials reuse the saved detections and original causal archive. The solver's region and screen are the published offer. It receives no scoring coordinate. The timed candidate publishes its exact selected marginal through the existing owner/objective replay and full grid. Position references are used in the subsequent scoring step. The audit extracts the curved and predictive point inventories independently from the final per-track reports and checks their satellite assignments against the rendered packet. It labels recovered curved fragments using the stock salvage selections recorded in the DS30 control. [Trial and owner audit](solver_linear_trial.py)

## North containing

The paired refit accepted both selected predictive tracks and recovered all 17 omitted points. The resulting 302 point owners matched both control hashes exactly, and the candidate built a complete 179-point grid and eight verified PNGs. The control, collapsed, and add-back used 7.248, 5.574, and 6.792 CPU seconds, respectively, from saved detections through the grid.

| Calibration arm | Add-back position | Control → add-back error (km) | Control → add-back solver RMS (Hz) |
|---|---|---:|---:|
| `c = 0` | 47.773194, 16.098705 | 0.745 → 0.176 | 5.380 → 5.386 |
| Fitted `c` | 47.771964, 16.099627 | 0.711 → 0.213 | 5.173 → 5.151 |

## Full DS30-0374 and identity audit

The original predictive gate admitted 24 tracks and 380 points with no failed tracks in either arm. Solver and grid CPU fell from 29.208 to 16.776 seconds relative to a fresh control. Every run completed its 179-point exact grid and produced eight verified PNGs. Figure construction took 5.242 and 4.878 CPU seconds. The add-back's evidence CPU includes the increased cost of evaluating its predictive model over the full grid.

| Calibration arm | Add-back position | Control → collapsed → add-back error (km) | Control → add-back solver RMS (Hz) |
|---|---|---:|---:|
| `c = 0` | 37.849078, −122.462910 | 1.855 → 2.287 → 2.005 | 101.536 → 101.370 |
| Fitted `c` | 37.849828, −122.461870 | 1.935 → 2.350 → 2.098 | 101.520 → 101.348 |

Both arms have the same ownership changes. The 2,379 collapsed owners form a strict subset of the control owners, with zero satellite-identity swaps, zero changes of role, and zero new points. All 115 lost curved points came from three stock salvage fragments. NORAD 62307 contributed 55, 66599 contributed 35 and 48464 contributed 25. Families 62307 and 48464 lost their entire representation. The predictive add-back recovered 380 points under their original owners. The remaining 31 omitted predictive points all came from two tracks for 62307, which lost its only curved support. The same catalogue remained available in discovery. These identities are diagnostic outcomes and do not enter the algorithm.

The owner audit initially stopped because legacy predictive gate rows omit NORAD. The corrected audit uses the selected entry that owns that gate's exact observation list and independently compares the resulting map with the normal evidence packet. The corrected DS30 control reproduced the known endpoints. Four component tests passed, including rejection when only one arm's predictive gates pass. [Component tests](../../../tests/pipeline_eval/test_algo08_collapsed_linear.py)
