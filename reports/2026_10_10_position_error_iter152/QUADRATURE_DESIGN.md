# Bounded conditional-integration diagnostic: draft only

No freeze, recording evaluation, quadrature, test or position fit is authorized
by this design. Start with the original saved endpoints of the existing consumed
twelve-member panel, both final c arms, original measurements and fixed banks.
Do not add a position stencil until the endpoint integral itself is shown to be
tractable. No references, position errors, parameter tuning or mode selection
enter this diagnostic. Missing, unsupported and budget-exhausted endpoints stay
in the 24-endpoint inventory.

The scope is the two receiver-specific modes in [PLAN.md](PLAN.md), with
[ADAPTER_REVIEW.md](ADAPTER_REVIEW.md)'s feasibility and actual-callback parity
preconditions. The finite coefficient intervals and normalized prior are fixed
by the existing model. Neither a neighborhood of the fitted mode nor a
prior-standard-deviation truncation replaces those intervals.

## Coverage and a conservative certificate

For one receiver, write the amplitude log integrand as
`L(a) = -D_r(a)`. At fixed geometry, every satellite prediction in observation i
has the same amplitude derivative `d_i = clock_design[i, receiver_slice] @ q`.
For the ordinary nearest-image wrapped Gaussian likelihood, residual magnitude
is at most `P/2`, with alias period P. Responsibilities sum to at most one.
Consequently an amplitude-interval derivative bound is

`|L'(a)| <= lambda*max(|lower|,|upper|) + sum_i |d_i|*P/(2*sigma^2) = G`.

This holds almost everywhere across wrap seams; the likelihood value is
continuous there, so it still gives a Lipschitz bound. It assumes the inspected
125 Hz production branch, positive clutter, fixed visibility and the verified
prior separation. It is not asserted for a different likelihood implementation.
Other fixed penalties have zero derivative. In particular, it does not rely on
the current responsibilities remaining valid away from the anchor.

For any cell of width w, center c and half-width h, the whole cell integral lies
between `w*exp(L(c)-G*h)` and `w*exp(L(c)+G*h)`. Add cell bounds in log space.
The resulting lower and upper sums cover **the complete finite interval**;
an unvisited remote narrow mode cannot silently escape this certificate.
With two receivers, add the two log-bound widths: that bounds uncertainty in the
normalized conditional negative log score. Require a combined width at most
`1e-4 NLL`, matching the existing numerical target.

This certificate is deliberately conservative. Large alias period, many rows
and a broad coefficient box can make it prohibitively loose. That is an explicit
failure of this lean diagnostic, not permission to silently drop the certificate
or reinterpret an adaptive integrator's error estimate as global coverage.

## Proposed fixed resource policy

Before execution, freeze a maximum of **512 scalar value evaluations per receiver
per endpoint**, plus at most four full-objective calls per endpoint for the anchor
and fixed callback/cache parity checks. Use a 30-second soft per-endpoint limit,
checked before calls; an in-flight call can overrun. Across 24 endpoints this is
at most 24,672 value calls, not a claim that the budget will be used or affordable.
Report all calls and elapsed times, including failed parity and coverage attempts.
Never expand these limits after inspecting an endpoint.

Partition each complete interval initially into 16 equal cells and evaluate their
centers. Repeatedly bisect the cell with the largest absolute integral-bound gap,
comparing gaps stably in log space. Ties use lower interval coordinate. Both child
centers require new evaluations; parent values remain in the receipt. Stop on the
global certificate or declared budget. This is a deterministic coverage rule,
not a search seeded from a fitted optimum or a reference position.

For descriptive resolution diagnostics, also record
`H_upper = lambda + sum_i d_i^2/sigma^2` and the scale `1/sqrt(H_upper)`.
The observed mixture curvature cannot exceed H_upper within a smooth winding
cell, because responsibility covariance subtracts curvature. This suggests how
fine local features might be, but **is not a universal sampling guarantee**:
boundary modes, nonstationary tails and winding changes need the global bound.
Neither a handful of adaptive nodes nor agreement between two coarse grids proves
that remote modes were covered.

An optional midpoint integral estimate lies inside the certified envelope. Its
successive-refinement difference may be reported as an empirical stability check,
never the acceptance criterion. No conditional profile or Laplace comparison is
claimed without separately bounded mode-search coverage; this draft certifies
integration only. Existing requirements on integration-minus-profile relevance
and Laplace accuracy are unchanged and remain a later stage.

## Stable arithmetic and conservative error handling

Store log weights, log lower bounds and log upper bounds; use log-sum-exp across
cells. Global shifts of L are algebraic and must be restored. Do not clip a small
probability, delete a cell, or replace a nonfinite objective with a finite sentinel.
Use outward numerical slack when converting floating-point values into interval
bounds, and explicitly document that ordinary floating-point evaluation is not
formal interval arithmetic. The analytic Lipschitz envelope is rigorous for the
specified mathematical likelihood; the implementation certificate is conditional
on correctly bounded floating-point error. Without that accounting, label it a
conservative numerical check, not a formally rigorous certificate.

Reject invalid support/boxes, improper or ambiguous modes, failed physical audit,
failed actual-callback factorization/parity, nonfinite values and inconsistent
bounds. Preserve the diagnostic reason. If this uniformly declared coverage
cannot resolve the endpoints within budget, stop the proposed lean integration
route. Do not use an uncertified subset to infer accuracy or choose a nuisance
mode. Failure can motivate a separately reviewed stronger analytic bound, not
an automatic second run.

## Avoid repeated orbit propagation without changing the likelihood

Full `evaluate_joint` calls repeat orbit prediction and spatial derivatives even
though geometry is fixed. This likely dominates a fine scalar scan; cost has not
been measured. The minimal eventual cache can preserve exact formulas:

1. Evaluate fixed orbital prediction/visibility and construct the original full
   prediction matrix, including receiver baseline, affine/RF terms and satellite
   corrections, using the actual final-model conventions.
2. For a receiver amplitude change, add `d_i*(a-a_anchor)` to every satellite
   component in its observation row. Call the existing `hard60_score.likelihood`
   with the original measured array, visibility and score. Recompute circular
   residuals and responsibilities; do not freeze labels or winding indices.
3. Add the original timing penalty and `0.5*clock.T@precision@clock` once, using
   the modified clock. Differentiate with the existing prediction gradient plus
   the prior. Keep other receiver likelihood and all fixed penalties unchanged.

This cache uses O(NK) existing prediction storage and O(NK) likelihood work per
scalar call, with no new orbital calls after setup. Receiver-only subsetting can
reduce work further, but is unnecessary for first parity. Bind the exact model,
arrays, bank, source and alias conventions. Compare cached values and scalar
gradients at the anchor and fixed interior test amplitudes against the full
objective before admitting a recording integral. Construction and those checks
must count against the frozen budget. No cache has been implemented or tested.

Source evidence: [dynamic clock model](../../src/leo/analysis/hard60_dynamic_rf.py),
[final satellite correction](../../src/leo/analysis/hard60_satellite_correction.py),
and [production wrapped likelihood](../../src/leo/analysis/hard60_score.py).
The likely bottleneck is certifiable coverage, not dimensionality: the conditional
integral already factors into two one-dimensional problems. This proposal cannot
establish positioning improvement and does not change the standalone goal metric.
