# DS5 exact full42 summary

Both exact 42-session aggregates completed and passed their sealed-input checks.
The crossfit aggregate also passed direct replay from all 42 session receipts over
all 25 cells.

| Method | Signal-selected offset | Objective | Post-seal error | Boundary |
|---|---:|---:|---:|---|
| Cell-batched point-local reassociation | east +4 km, north 0 km | 32,658.36 weighted MSE Hz² | 4.910 km | yes |
| Exact crossfit | east -2 km, north +4 km | 101,678.63 equal-session held-out MSE Hz² | 4.104 km | yes |

The crossfit winner has 318.87 Hz equal-session held-out RMSE at the training-selected
shared tau of -1 second. The cell result has 180.72 Hz effective-time-weighted RMSE;
these losses are governed by different selection and weighting contracts and are not
directly comparable.

Both winners are on the edge of the 5 by 5 grid. These are therefore truncated 2 km
coarse-grid outcomes, not converged position estimates. Crossfit has the lower
post-seal error here, but DS5 is development data and the result is not independent
final validation. Reference coordinates were introduced only after the truth-blind
inference summary was sealed.

Machine-readable artifacts and the figure are in
`/srv/bulk/leo/experiments/ds5-exact-summary/`.
