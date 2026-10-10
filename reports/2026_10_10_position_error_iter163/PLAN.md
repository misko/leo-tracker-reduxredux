# Symmetric calibration starts at fixed ordinary geometries

Source preparation only. Freeze and publish the numerical protocol before
recording fits. Keep the 0.4 km standalone mean-error goal and the deployed
pipeline unchanged. No new RF collection or reserved-outcome access.

Iteration 162 found two independently stationary conditional fits with worse
training objective than an already available feasible state at exactly the
same position. This successor tests a general bounded remedy for every member,
not a DS16-024-only repair and not a claim that KKT certifies global optimality.

Use all twelve consumed members, their two ordinary full-data position
hypotheses, and the same grouped folds and model definitions from 161/162.
At each hypothesis, training fold and c arm, add two fits initialized from the
two ordinary 161 full solutions. Copy the complete physical/nuisance state and
replace only its position with the tested hypothesis; then apply the target
arm's required RF locks. Zero-c sets static c and both RF-time coefficients to
zero. Fitted-c retains the source's RF coefficients. All other starting
coordinates remain the same across arms. Both arms receive the same two source
states, candidate hypotheses, observations, priors and fit budgets; the RF
projection is an explicit part of the arm definition.

This comprises 12 × 2 hypotheses × 2 folds × 2 arms × 2 new starts = **192 new
fixed-position fits**. Use the unchanged production fitter with 90-second soft
budget, 600 maximum iterations, timing half-width 20 seconds and existing hard60
constraints. Independently check exact fixed position, original feasibility,
clock bounds, RF locks, objective parity within 1e-6 and projected stationarity
within 0.001. A successor audit must allow valid nonzero fitted-c starts;
iteration 161's zero-start-only admission cannot be silently bypassed.

Retain the corresponding sealed, qualified 162 result as an explicitly labelled
control candidate. Authenticate its exact model, fold, hypothesis and arm, and
freshly reproduce its training objective and independent qualification before
admitting it. These 96 control audits are measured separately from new fits.
Select the lowest qualified **training objective** among
that control and the two new fits, before reading any held score of the new
selected state. Use absolute 1e-6 objective tie tolerance, preferring control,
then the zero-source start, then the fitted-source start. Define the tolerance
relative to the global minimum among all qualified candidates before applying
priority; do not use sequential pairwise comparisons. Preserve every attempt
and failure. A retained control is reported as retained, never as successful
new optimization or an invisible fallback. Report attempted/qualified new fits,
selected-source counts and incremental cost separately from historical cost.

Score only the selected state on the opposite fold, without updating parameters.
Use the unchanged within-arm two-fold summed-NLL geometry preference from 162,
including its 1e-6 tie threshold and no unresolved-selection fallback. Retain
training likelihood, prior penalty and held likelihood separately. Never choose
calibration starts by held score or geographic error.

Seal all 192 new attempt receipts and all 96 selected-calibration receipts
before geometry preference publication and position evaluation. Compare against
the sealed 162 selectors and the ordinary same-arm 161 full positions, with
matched members, per-dataset mean/median/p95/worst errors, regressions, geographic
ties and all failures. The initial states and hypotheses use full-data inference,
so this remains consumed conditional development, not independent validation.
No result may replace the official 193-member mean by diagnostic splicing.
At most two single-thread numerical workers; keep scientific sources immutable
after freeze and do not restart an orphaned claim.
