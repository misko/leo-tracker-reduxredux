# Best-first fine-resolution comparison

This report compares the same truth-blind exact-center search at 12.5 km with a
400-point budget and at 6.25 km with 400- and 800-point budgets. Every run uses
the same 34 tracks, 750 disjoint observation IDs, fixed position-independent
evaluation masks, capped represented-time-weighted all-track RMS objective,
500 km radius, and 12 fork workers.

The 6.25 km lattice contains 20,108 in-circle centers. Evaluating 400 or 800
mixed-resolution centers is a bounded heuristic search, not an exhaustive or
globally certified substitute.

## Finding

Finer resolution without more budget regressed Sacramento badly: the 400-point
run exhausted its budget in the coarse-selected northwest basin and returned
205.52 Hz. At 800 points the search reached the main basin and improved to
183.09 Hz. Reno reached its 182.40 Hz fine cell with 400 points and did not
improve with 800.

The exact local checks certify only the 100 km parent selected by the coarse
objective (the best initial 100 km center). Sacramento's successful local check around the northwest parent did
not prevent a better basin elsewhere. Local validation is therefore necessary
but insufficient for a 500 km search guarantee.

| City | Resolution / budget | Search time | Finest centers | Capped RMSE | Coverage | Post-selection distance |
|---|---|---:|---:|---:|---:|---:|
| Sacramento | 12.5 km / 400 | 45.72 s | 219 | 185.01 Hz | 720 IDs / 32 tracks | 6.72 km |
| Sacramento | 6.25 km / 400 | 60.84 s | 214 | 205.52 Hz | 683 IDs / 29 tracks | 513.56 km |
| Sacramento | 6.25 km / 800 | 108.96 s | 506 | 183.09 Hz | 720 IDs / 32 tracks | 12.75 km |
| Reno | 12.5 km / 400 | 45.83 s | 203 | 184.51 Hz | 712 IDs / 31 tracks | 9.41 km |
| Reno | 6.25 km / 400 | 56.60 s | 216 | 182.40 Hz | 712 IDs / 31 tracks | 9.39 km |
| Reno | 6.25 km / 800 | 95.82 s | 492 | 182.40 Hz | 712 IDs / 31 tracks | 9.39 km |

The 400- and 800-point fine runs executed concurrently, so their wall times
include shared CPU and memory load and are not clean isolated timing estimates.
Sacramento's lower 800-point objective also increased post-selection reference
distance from 6.72 to 12.75 km; objective improvement is not calibrated position
accuracy.

The next algorithmic step should preserve the previous-resolution incumbent and
frontier when adding a finer level, then allocate an explicit exploration and
exploitation budget. These runs started independently; state was reused within
each run but not across the separate 12.5 and 6.25 executions.

The evaluation split participates in selection, so its RMS is not independent
final-test accuracy. Reference distance is calculated only after selection.
At the two 12.5 km finalists, one saturated track contributes about 62% of the
total squared loss and its capped term is equal at both cells. Six selected
tracks sit on a tau boundary. These diagnostics limit how much physical meaning
should be assigned to small objective changes.

Figures: [cost convergence](cost-vs-evaluations.png), [wide visited maps](visited-wide.png),
and [local zoom maps](visited-local-zoom.png).

## Reproduction

Run either fine-resolution budget from the public stored-track and causal TLE
ports by changing `BUDGET` to 400 or 800:

```bash
sudo -n env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/research/run_best_first_tle_search.py \
  --evidence /path/to/evidence --output /fresh/output \
  --cities sacramento reno --radius-km 500 --budget-points BUDGET \
  --workers 12 --priority-mode exact-centre --finest-spacing-km 6.25
```

Verify and render the copied artifacts without corpus access:

```bash
.venv/bin/python reports/2026_09_23_best_first_fine_resolution/qualify.py
.venv/bin/python reports/2026_09_23_best_first_fine_resolution/render.py
```
