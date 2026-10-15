# A059/A105: inherited geography versus fusion displacement

The completed A059 covered search selects the same path that minimizes its CH1–4 stage objective. The combined final fit moves only 0.73–1.14 km from that path's low-stage position. Its roughly 275 km configured distance therefore cannot be explained by a large within-path displacement introduced during fusion. This identifies an upstream likelihood/search problem as well as any possible fusion problem; it does not prove exhaustive search or verified satellite assignments.

This is a zero-fit, zero-objective metadata audit of the sealed [budget completion](DS22_A_BUDGET_COMPLETION_RESULTS.md). No observations, predictions, reference coordinates, held data or new seeds were accessed. All distances below are Euclidean separations in the saved local XY chart, not receiver-reference errors. The low stages share the union bank and upstream full-derived preparation, so they are conditional CH1–4 views, not an independent adaptive or half-only pipeline.

| Case / final method / scope | Selected path | Low-stage to final displacement km | Exact omitted shift prior |
|---|---|---:|---:|
| 059 / high timing / original six | original-0 | 19.157874 | 0.350643 |
| 059 / high timing / covered 22 | coarse-11 | 1.136458 | 0.482467 |
| 059 / low timing / original six | original-0 | 0.924131 | 0.350643 |
| 059 / low timing / covered 22 | coarse-11 | 0.728482 | 0.482467 |
| 105 / high timing / original six | original-0 | 2.189285 | 0.336727 |
| 105 / high timing / covered 22 | original-0 | 2.189285 | 0.336727 |
| 105 / low timing / original six | original-5 | 1.606492 | 0.272675 |
| 105 / low timing / covered 22 | coarse-03 | 2.919546 | 0.444045 |

For each strict eligible final candidate in each method/scope, adding the original high-stage offset prior `sum(offset_hz**2)/(2*50000**2)` leaves all eight winners unchanged. This directly tests the omitted constant on the existing candidate inventory; it does not propagate offset uncertainty or make the fixed-shift model jointly stationary in those offsets.

Among all strict low-stage candidates, A059's minimum is coarse-11, J=26292.326580. Both covered combined selectors retain this path. Its learned high-minus-low offsets are −18645.415 and +45438.788 Hz for the two receivers. The large receiver-dependent values warrant physical calibration/association diagnosis, but their size alone is not evidence of a bug.

A105's low-stage minimum is coarse-03, J=25953.347237. The low-timing final selector retains this path and moves 2.919546 km. The high-timing selector instead chooses original-0, whose low-stage J is worse by 286.251781, and moves 2.189285 km within that path. Its final position is 303.068163 km from the low-stage winner. Thus a large difference between selected estimates can arise from switching paths rather than a large geographic movement during an individual final fit. Final selection still uses each declared final objective, never this separation or reference distance.

The next diagnosis must distinguish three effects: low-stage basin discovery/ranking, cross-path final ranking, and within-path movement after learning shifts. Adding more final-stage starts or the small missing prior cannot by itself explain or repair the observed A059 result. A separate uncertainty-aware offset model would require a common joint likelihood with the original data and priors counted once; reusing a high-data posterior as a prior while scoring the same high data would double count evidence.

Reproduction uses `terminal.json` under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-ds22-budget-completion-v1/{DS22-059,DS22-105}`. For each selection, join its `unit` to `rows[unit].calls.low.row.fit` and `.high.row.fit`; compute XY displacement and the two-offset penalty. Independently rank accepted low rows by their own objective, and accepted final rows by final J plus the penalty, restricting original-six rows by their `original-` unit prefix. No missing/rejected row is eligible.

Source SHA-256: A059 `5e70c260c40cc740a4655e11d5913ead7535321234510772594f9586c15248ed`; A105 `c7a670a4909c8945e213cc991055366aca7e351a78bb10c3975bc9d9d1bef1ca`. Both match the previously sealed completion report. No cohort curves or performance claims change.
