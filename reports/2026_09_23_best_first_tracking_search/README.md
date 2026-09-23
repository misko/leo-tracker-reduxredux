# Best-first all-track TLE search

This report benchmarks a bounded best-first `100 → 50 → 25 → 12.5 km` search
for `scan-fw-cf510316ae7f05d5`. It uses every eligible reconstructed track with
at least 3 seconds of support and at least six observations, a frozen
position-independent split, and a maximum 500 km initialization radius.

The primary objective is the square root of the represented-time weighted mean
of per-track squared held-out RMS values, with each track loss capped at
800 Hz. Each track's weight is its number of distinct represented one-second
time bins. Uncapped per-track RMS and strict 200 Hz observation coverage are
diagnostics and do not change the search priority.

The frozen randomized evaluation split participates directly in candidate,
cell, and final-location selection. Its RMS is therefore a selection score, not
independent final-test accuracy.

The best-first queue and every pruning rule are heuristic unless an explicit
bound receipt proves otherwise. Publication requires a bounded exact 12.5 km
comparison region selected from the search inputs rather than the evaluation
reference. Position-reference distance is computed only after selection.

Only Sacramento and Reno are evaluated. Denver's earlier 2,500 km prior was a
stress test outside the current initialization assumption and is excluded.

## Measured result

Both searches used 34 eligible tracks containing 750 disjoint observation IDs,
a 400-point budget, and 12 fork workers. The exact-center priority is the
default because it reached the same final cells more quickly and evaluated more
12.5 km centers than the parent-linear experiment.

| City | Priority | Search time | Finest centers | Selected offset | Capped weighted RMSE | Coverage | Post-selection distance |
|---|---|---:|---:|---:|---:|---:|---:|
| Sacramento | exact center | 45.72 s | 219 | (-93.75, -81.25) km | 185.01 Hz | 720 IDs / 32 tracks | 6.72 km |
| Sacramento | parent linearization | 50.98 s | 199 | (-93.75, -81.25) km | 185.01 Hz | 720 IDs / 32 tracks | 6.72 km |
| Reno | exact center | 45.83 s | 203 | (-243.75, -181.25) km | 184.51 Hz | 712 IDs / 31 tracks | 9.41 km |
| Reno | parent linearization | 49.07 s | 161 | (-243.75, -181.25) km | 184.51 Hz | 712 IDs / 31 tracks | 9.41 km |

The table reports the best evaluated **final 12.5 km lattice** cell. Sacramento's
best incumbent across every evaluated resolution was the coarser `(-75, -75)`
km cell at 184.7835 Hz; its selected final-lattice cell was `(-93.75, -81.25)`
km at 185.0136 Hz. Reno's global and final-lattice incumbent was the same cell.

All four searches stopped at the point budget with a nonempty frontier. They
are incomplete heuristic searches, not global 12.5 km optima. Within the small
truth-free validation region chosen by the best 100 km objective cell, both
qualified searches found the exact local winner and visited all of that
region's exact top 15. This local result does not certify the rest of the
500 km circle.

No certified spatial pruning rule was supplied. The recorded certified-prune
count is zero; cells remained deferred only because the 400-point budget was
reached.

The parent-linear priority reuses each parent's selected satellite prediction,
fits finite-difference east/north derivatives, and refits the frozen
training-only nuisance terms at a nine-point child stencil. It is only a queue
ordering estimate and never supplies a pruning bound or final score. On these
runs it did not improve the result or runtime.

The one-second-bin weights are a fixed duration and evidence proxy, not a count
of calibrated independent samples. Tracks can remain correlated through shared
receiver or orbital effects even though their observation IDs are disjoint.
The primary value is the capped robust objective; uncapped matched-track RMS,
unmatched counts, and 200 Hz coverage remain separate diagnostics. The use of
34 three-second tracks changes the evidence set from the earlier ten-track
coverage report, so differences cannot be attributed to the search algorithm
alone.

## Reproduction

The live numerical run requires the public stored-track source and causal TLE
archive named by the receipts:

```bash
sudo -n env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/research/run_best_first_tle_search.py \
  --evidence /path/to/evidence --output /fresh/output \
  --cities sacramento reno --radius-km 500 --budget-points 400 \
  --workers 12 --priority-mode exact-centre --finest-spacing-km 12.5
```

Requalify and render the frozen report without corpus access:

```bash
.venv/bin/python reports/2026_09_23_best_first_tracking_search/qualify.py
.venv/bin/python reports/2026_09_23_best_first_tracking_search/render.py
```

Figures: [best cost versus evaluations](best-cost-vs-evaluations.png),
[visited points](visited-points.png), and [runtime comparison](runtime.png).

`baseline-retroactive-qualification.json` binds the completed exact-centre
400-point baseline to the current deterministic input protocol. Its 34-track
inventory, represented-second weights, and input provenance match exactly; the
engine, loader, frozen kernel, and parent-priority source digests also match.
The run-writer source changed only to add the frozen track-evidence receipt, so
`reconstructed-baseline-fixed-track-evidence.json` derives the same fixed
partition masks retrospectively and is labeled as such. It is not a claim that
the old baseline emitted those masks contemporaneously.

Both baseline searches stopped at the 400-point budget. Within the independently
rescored 12.5 km local reference under the selected 100 km parent, Sacramento
matched the 36-point winner and Reno matched the 64-point winner; each had
top-15 coordinate recall of 1.0 and zero objective gap. These are local
reference checks, not a global optimum guarantee.

`parent-linear-comparison-qualification.json` qualifies the parent-linear
priority run. Its copied source snapshot matches its manifest, its frozen
34-track fixed-mask receipt and represented-second weights recompute exactly,
and the capped all-track objective recomputes from every finalist. Sacramento
and Reno select the same final 12.5 km coordinate and objective as the
exact-centre 400-point baseline; both local exact references again have winner
match, top-15 recall 1.0, and zero objective gap. Parent-linear reaches the
Sacramento global incumbent `(-75, -75)` at evaluation 254 versus 195 for
exact-centre; the final-lattice point is reached at 263 versus 212. It provides
no measured Sacramento budget advantage and remains a heuristic priority with
no certified spatial-pruning claim.
