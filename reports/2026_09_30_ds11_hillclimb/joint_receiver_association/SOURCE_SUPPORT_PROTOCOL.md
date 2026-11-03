# Whole-source assignment feasibility

The calibration and position grouping differ: calibration merges all nominated
tracks per physical NORAD/RF; bipartite position matching does not. Audit an
alternative assigning every track one retained physical candidate, grouping all
same-NORAD/RF tracks and scoring the union of receiver observations once.
Ownership alternatives still prevent duplicate raw observations. Start with the
frozen independent conditional receiver calibration, without changing parameters.
Use per-track catalogue priors, so removing receiver evidence reduces exactly
to independent Doppler mixtures (subject to explicit raw-observation ownership).
This is a different prior from the earlier matching model; preserve that model.

First measure tractability at original training-fitted endpoints on all six
compatible development inputs, every ownership branch. Do not fit positions or
inspect additional reference errors in this audit. Exact whole-source evaluation
must not silently discard candidate assignments.

For any assignment, the normalized receiver-state factor is <=1. Therefore
omitted joint evidence is bounded by omitted mass under the independent Doppler
mixture. Compute a finite lower bound L from the per-track MAP assignment after
whole-source receiver scoring; compute the independent Doppler log evidence D.
Remove only track candidates with conditional log probability below
L-D+log(1e-10)-log(total candidate slots). The union bound then guarantees omitted
evidence <=1e-10*exp(L), hence <=1e-10 of retained evidence. Report the bound
in log space, including candidates whose probabilities underflow in linear space.
This certificate covers the original exported candidate banks only, not omitted
catalogue objects. Recompute at every position if subsequently used in a solver.

Report connected component assignment counts after certified reduction. Limit
the audit child to 90 seconds. A solver still needs exact enumeration/parity,
gradient checks, and a separately frozen position experiment before any accuracy
claim. No unconditional absence/clutter or new orbit corrections are implied.
