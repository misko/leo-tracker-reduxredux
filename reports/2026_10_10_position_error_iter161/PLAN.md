# Fresh full-data and grouped-training comparison

Execution plan under the user's continuing research authorization. Recording
fits start only after the source/input/runtime protocol is frozen and published.
The standalone mean-position error goal remains 0.4 km; no improvement is promised.

## Fixed scope

Use all 12 consumed members from iteration 155, their original observations,
and the exact two folds sealed by iteration 160. Retain every member and row;
do not replace failures or choose a different split. The comparison comprises
72 fresh fits: 12 members × full data / training fold 0 / training fold 1 ×
fitted-c / c = 0. Acquisition grouping keeps paired receivers and overlapping
sample support together; it does not establish statistical independence.

For each member, all six fits start from independent copies of the same saved
iteration 155 **zero-c selected physical vector and clock coefficients**.
Both c = 0 locks—static RF stretch and the final two RF-time coefficients—must
remain exactly zero in the zero-c arm. The fitted-c arm starts at these same
zero values and may subsequently fit them. Do not substitute the historical
fitted-c endpoint as its start.

These are matched supplied starts. The unchanged fitter can move a timing
coordinate on an exact boundary inward by 1e-9 seconds during parameterization;
bitwise equality of its first evaluated state to the supplied seed is not claimed.

All six fits use the same bank, observations or prescribed row subset, clock
nodes, interpolation basis, time/RF centers, satellite slope centers, nuisance
precision, timing priors and bounds. Before proceeding, bind and verify that
the original selected model definitions match across the two historical arms;
otherwise preserve an explicit member failure rather than mixing models.

## Fitting and qualification

Use the unchanged
[joint fitter](../../src/leo/analysis/hard60_dynamic_rf.py)::`fit` with:

- `seed` and `clock_seed` copied from the common zero-c endpoint;
- `arm` set explicitly;
- `maximum_seconds=90`, a soft deadline between objective calls;
- `maximum_iterations=600`, not an objective-evaluation cap;
- `timing_half_width_s=20` and `fixed_position=False`.

The local disk is 25 km around the common starting position for every fit.
This is deliberately different from the original B7 stage's local center.
There is **no promise of historical optimizer or position parity**. Fresh
full-data fits provide the matched controls for the grouped-training fits.
The saved zero-c endpoint identifies the common start, not a success fallback.

Use the original full objective for full-data fits and iteration 159's row
objective for each training fold. Training includes only its selected
normalized mixture terms plus the unchanged priors once. Preserve whole-data
basis definitions; do not construct a subset model with different centering
or interpolation support.

Independently audit each returned state using the actual original constraints
with this common local center, arm locks and 25 km radius. Use the physical
`_Problem` projected stationarity together with the nuisance gradient scaled by
50 and projected against its original coefficient boxes and RF locks. Require
finite state, objective and gradients, physical feasibility and full-state
stationarity at most 0.001. Re-evaluate the returned state once on its own
fitting objective and require agreement with its reported objective within
absolute 1e-6. Never use iteration 155's `anchor_audit`: it intentionally forbids
position movement and is unsuitable for these fits.

Preserve solver output, independent audit, elapsed time, evaluation/iteration
counts where available, and every failure. No retries, repairs, alternative
starts, or fallback endpoints may be counted as successful fits. Qualification
checks and scoring add measured cost beyond the fitter's soft budget.

## Predictive reporting

For each qualified training fit, evaluate the opposite fold using the returned
physical and nuisance parameters without refitting or calibrating them. The
held score is `terms.nll` only. Report training likelihood, training priors and
held likelihood separately. A held observation's responsibilities may be
computed during fixed-parameter likelihood evaluation; they must not update
any parameters. Report counts and per-row scores alongside sums so differing
fold sizes remain visible. Preserve missing scores for failed fits rather than
zero-filling them.

The fresh full-data control is useful for measuring how much fitting all rows
changes the same scoring subsets. Its held-subset scores are descriptive
in-sample comparators, not held-out predictive performance. No per-member winner
selection between fits or c arms is part of this proposal.

## Conditioning and evaluation boundary

The bank, retained region, original start and responsibility-weighted satellite
centers originate from full-data inference. Keeping those structures fixed
makes this **consumed-data conditional predictive sensitivity**, not independent
validation or a wholly training-only localization pipeline. Whole visits also
share clock and orbital errors across folds. See
[iteration 159's rationale](../2026_10_10_position_error_iter159/PLAN.md).

This experiment tests calibration and fitting consistency around one ordinary
selected geometry. Without an independently specified inventory of competing
ordinary geometries it does not establish that held likelihood identifies the
correct region. Better predictive frequency fit must not be presented as better
position accuracy.

Seal all 72 attempted fit receipts and full 12-member coverage before any
position evaluation. Reference coordinates and errors must not enter grouping,
model construction, starts, fitting, qualification or operational selection.
A separately reviewed evaluation protocol is required before reading reference
positions or reporting position errors. That later report must retain both c
arms and distinguish fresh full controls from historical endpoints; it cannot
replace the standalone positioning goal with a predictive-score metric.
