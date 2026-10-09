# A bounded linear update of existing B7 clock coefficients

This is a pure synthetic-tested solver prototype, not a new position result or
production change. It adds no nuisance variables and reads no recordings. It is
separate from both a frozen receiver-contrast correction and ordinary clock-start
search. No claim of speed or position improvement follows from these tests.

## Existing model and exact surrogate

[DynamicRFObjective](../../src/leo/analysis/hard60_dynamic_rf.py) already represents
receiver smooth clocks and RF-time terms linearly through `clock_design`, with a
quadratic `precision` prior. Its current fitter optimizes these coefficients
alongside geometry/timing using SLSQP. Satellite slope terms in B7 have separate
candidate-dependent design and must not accidentally be treated as receiver-wide
clock columns.

At fixed geometry, timing, satellite slopes, candidate responsibilities and alias
windings, receiver-clock fitting is a bounded quadratic. Let r be the collapsed
measurement-minus-current-prediction residual, A the receiver clock design,
W its signal-responsibility precision, c the actual current coefficients, and
P the existing prior precision. Solve

`Q(delta)=0.5*(A*delta-r)'W*(A*delta-r) + 0.5*(c+delta-mu)'P*(c+delta-mu)`.

The prior is on the **actual updated coefficients**, not on delta alone. Omitting
the P(c−mu) gradient term would change the model and falsely favor an unchanged
nonzero clock. The usual B7 prior mean mu is zero. Cross-prior terms from locked
coefficients remain included.

`collapse_mixture` reduces candidate-specific Gaussian residuals to one weighted
target per observation for this receiver-common update. Its returned constant
preserves the full quadratic value, including within-window candidate spread.
Zero signal responsibility contributes no data weight. The collapse cannot be
used unchanged for satellite-specific updates, whose design differs by candidate.

`solve_nuisance_delta` factors positive-semidefinite P and solves the augmented
bounded least-squares problem using SciPy BVLS. Equal lower/upper bounds lock
coefficients exactly. It reports data and regularized rank separately, actual
objective change, active bounds, projected-gradient stationarity and solver status.
An independently checked feasible KKT point with no surrogate increase qualifies;
the library success flag alone is insufficient. Empty observations are explicitly
rejected; nonempty all-zero data weights allow a prior-only update.

Rank-deficient unconstrained least-squares uses a minimum-norm delta, preserving
unidentified current modes. For rank-deficient box-constrained cases, the solver
returns a qualified optimum but does not promise a uniquely defined minimum-change
point among all tied optima. Rank deficiency is not physical identification.

## Direct compatibility and limits

The prototype can consume an existing B7 `clock_design`, `precision`, coefficient
vector and frozen likelihood terms. `receiver_clock_bounds` changes only the first
`smooth_clock_count` coordinates and the final two RF-time coordinates. All
intervening satellite coefficients are locked at their current values, so their
zero columns in `clock_design` cannot silently cause prior-only shrinkage.

Physical bounds match the current fitter: smooth coefficients±2000Hz in its
coefficient convention; RF-time coefficients±1000 in their current units. For
c0 or RF-time-off, both final coordinates are locked exactly to zero. An
infeasible starting vector is rejected rather than silently repaired. Static c,
affine receiver slopes, position and timing are outside this block and unchanged.

The caller must then refresh the **actual wrapped mixture objective**, including
its clutter term, updated responsibilities, alias winding and every existing
prior. Accept only an independently qualified step that does not increase that
unchanged objective; otherwise retain the exact original state. A successful
quadratic solve is not full nonlinear stationarity. At changing geometry or
candidate visibility, repeat the model evaluation; do not reuse stale residuals
as though the entire position problem were quadratic.

This differs from earlier clock-start proposals: it solves one bounded,
regularized block of the existing coefficients, rather than enumerating affine
receiver anchors/slopes. Nonetheless, applying it at an already fully qualified
B7 optimum should not create a meaningful accuracy gain under the same model.
Its main potential is a cheaper inner nuisance update during future alternating
geometry fitting, or a controlled numerical diagnostic of whether a current
joint endpoint is truly stationary. That potential remains unmeasured.

The implementation factors a small coefficient-space prior and performs augmented
least-squares over observations; it does not allocate an observation-square
covariance. Repeated calls could reuse a prior factor, but optimization should
follow measured runtime evidence rather than adding caching infrastructure now.

## Synthetic qualification

Eleven tests pass under the production Python3.14.4 environment. They cover
agreement with an independent SLSQP quadratic reference, nonzero-current prior
centering, exact RF/satellite locks and cross-prior gradients, deficient rank,
active-bound KKT signs, mixture-collapse value/gradient equivalence, all-locked
states, invalid precision and explicit empty-input handling.

A synthetic fixed-geometry wrapped-Gaussian-plus-clutter example crosses the
observation alias boundary, solves the frozen surrogate, then explicitly refreshes
the production likelihood and accepts only after confirming its exact objective
decreases. Responsibilities change on refresh. This is a mathematical integration
check, not a recording fit, benchmark, or guarantee for every future numerical
step. Production adaptation would additionally require full model-state tests,
matched c arms, same-start controls, frozen whole-recording validation and measured
compute/accuracy tradeoffs. Existing production B7 remains unchanged.
