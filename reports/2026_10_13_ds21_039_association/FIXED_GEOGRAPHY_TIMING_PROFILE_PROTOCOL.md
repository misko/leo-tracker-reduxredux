# DS21-039 finite displacement nuisance-profile control

This development diagnostic follows the completed eight-point timing displacement
check. It tests whether refitting nuisance parameters removes the asymmetry of
the saved linear compensation rays. It is not a new position estimator and does
not select geography against the reference. All new fitting uses fitted c only.

## Prespecified four calls

Use the first saved curvature step (`1e-4`) at each of the original all-band and
refined free-position endpoints. The four fixed geographical positions are their
already evaluated minus and plus 1 km displacements. Use the corresponding saved
compensated physical vectors and nuisance vectors without new seeds or candidate
discovery. The second curvature step is a numerical sensitivity check, not four
additional starts to choose after seeing outcomes.

Bind the successful displacement freeze, terminal, endpoint receipts and final
seal, along with their successful curvature and original-model ancestors. Before
any optimizer call, verify unchanged input/source authority, physical layouts,
candidate bank, original bounds and exact starting-objective/prior replay within
the declared numerical closure tolerance. Freeze the new runner's source bytes
separately; do not edit any successfully frozen scientific source.

For each call, fix east and north to that displacement and optimize the original
receiver calibration, fitted c, common and relative satellite timing, and existing
group nuisance coefficients. Retain the original per-observation RF/time model,
likelihood, priors, native alternatives, seed-5 geographic disk and physical
bounds. Do not add weighting, temporal edges, tighter priors or new coefficients.

Each fit has at most **20 seconds and 600 iterations**. Run one process with
one BLAS thread, at most 150 seconds internally including preparation, external
TERM at 165 seconds and KILL at 170 seconds. There are exactly four proposed fit
calls, no automatic retries and no alternative-direction search. Failed,
interrupted and nonstationary outcomes remain visible. A process timeout does
not authorize replaying a call whose completion is unknown.

## Analysis and decision rules

Report the original endpoint objective, exact saved displacement objective,
local Taylor prediction, and fitted fixed-position objective separately. Split
each change into likelihood and common-timing, relative-timing and group-prior
costs. Verify that fitted geography remains fixed and report stationarity and
active bounds. Keep the saved ray state as a feasible incumbent if the optimizer
does not produce a better valid stationary result; label its origin explicitly.

A material reduction from the ray objective demonstrates additional feasible
nuisance relaxation. It does not prove the global nuisance-profile minimum.
If the negative-direction excess largely disappears, linear compensation was
an important source of the observed asymmetry. If the excess remains after
stationary fitting, finite nonlinear behavior remains under this initialization;
that still does not identify a timestamp bug or prove satellite identity.
Neither outcome justifies choosing a tighter prior using known position errors.

No reference coordinates, held observations, new RF collection or QNAP mutation
are used. The existing endpoint position errors remain historical evaluation
results; the four displaced positions are not scored or ranked by geographical
accuracy. Full DS21 and the three-model 0.5 km acceptance target remain separate,
unfinished requirements.
