# Conditional persistence integration review

This is source-only preparation, independent of the partial iteration108 census.
No recording was evaluated, no rho was chosen and no model was implemented.

A minimal research wrapper can reuse the complete production
`SatelliteCorrection.evaluate_joint` prediction and Jacobian algebra, replacing
only `likelihood` with the sequence kernel. Its smoothed occupancy supplies the
prediction derivative; the existing spatial/timing, physical design, smooth/RF
clock, satellite offset and slope chains then contract exactly as before. Common
and relative timing priors and the entire clock precision remain unchanged.
Packing/unpacking must preserve original row order, with shared inference-only
segments and resets. Candidate banks, search starts, priors, c-arm locks and
budgets must remain matched. No additional receiver clock dimensions are needed.

The adapter must export the existing narrow likelihood-term contract (`nll`,
`prediction_gradient`, satellite responsibilities, clutter probability and
wrapped residuals). For positive rho, responsibilities are smoothed sequence
occupancies: signal mass and weighted RMS therefore change meaning. Label them
explicitly; they are not independent row posterior probabilities or evidence of
better position. Preserve independent-frequency diagnostics separately, without
using them to choose among models. Existing fit/export consumers can otherwise
retain their interface; no published persisted contract should be redefined.

The kernel preserves the independent detection normalization for every row and
normalizes redraw probabilities over currently visible satellites plus clutter.
Do not replace this with an unnormalized track score. Visibility is recomputed
at every hypothesis but treated as fixed in frequency derivatives, as in B7.
Finite differences must avoid visibility/wrap boundaries; separate tests should
document their discontinuities rather than claim a globally smooth objective.

At rho=0, require bitwise kernel nesting and full composed score, physical
gradient and clock gradient parity at synthetic nonzero-prior states. Require
the same fixed-position/active-bound independent KKT and c=0 static/RF locks.
Positive-rho composed finite differences should cover all parameter blocks,
receiver exchange, resets, permutations and satellite relabeling before any
recording optimizer runs. Archived endpoints remain a separate baseline;
cross-rho scores must never be an operational winner rule.

## Scientific issue to resolve first

The current transition is `T = diag(s) + (1-s) piᵀ`, where `s=rho*active`
and clutter has s=0. Even with unchanged visibility, pi generally is not its
stationary distribution: `(pi T)_j = pi_j (s_j + 1 - sum_i pi_i s_i)`.
Satellite and clutter stay probabilities differ, so positive rho changes the
categorical marginal preference as well as temporal dependence. This is a model
confound, not an implementation error. Decide before freezing a positive-rho
study whether that asymmetric physical assumption is intentional. If retained,
disclose it and include a separately frozen stationary-marginal control; do not
interpret all benefit as persistence. A stationary control is a distinct model,
especially when visibility changes, and requires its own normalized derivation.

Rho is also per adjacent observation, not a physical decorrelation time. Unequal
gaps and sampling rates imply different persistence per second. Either explicitly
study that discrete assumption or derive a globally fixed elapsed-time policy
before validation. No per-scan tuning from entropy, position error or partial
census outcomes is justified. Bootstrap track membership itself is a conditioned
inference grouping, not independent proof that consecutive labels should agree.

## Embedded cost and next gate

The transition permits O(NK) time without dense K×K matrices. Current full
forward/backward arrays require O(NK) memory and also compute the independent
likelihood at every call. A lean implementation should process disjoint segments
sequentially, accumulate objective/Jacobian contractions and release each
segment, yielding O(max_segment_length*K) working storage. Exact smoothing still
needs forward information or recomputation within each segment; do not claim
constant memory without measuring that tradeoff. Long segments need a fixed
memory policy, not data-dependent truncation selected for position accuracy.

After full census completion, decide whether ambiguity and valid links justify
the additional mechanism. Then freeze one small model comparison with matched
c arms, starts and budgets, held-out-block predictive evidence where available,
position accuracy evaluation only, complete failures and measured runtime/memory.
The census alone cannot establish that positive rho improves localization.
