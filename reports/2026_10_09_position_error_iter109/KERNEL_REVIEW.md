# Independent kernel review

No blocking mathematical issue was found for a future synthetic composed-gradient
prototype. The implementation matches the marginal transport derivation: retained
mass is rho times the minimum of adjacent prior masses, clutter retention is zero,
and redraw compensates exactly for that retained mass. The forward diagonal plus
rank-one multiplication and its backward transpose action are consistent. Resets
cut backward messages and initialize the current mixture directly. The derivative
uses smoothed occupancy and is correct conditional on unchanged visibility/priors.

Eight synthetic tests passed independently in 1.82 seconds. They verify dense
transition normalization and marginal transport under changing visibility and
all-clutter cases, brute-force sequence likelihood and occupancies, finite
differences for each synthetic prediction, reset independence, wrapping and exact
rho=0 production likelihood/gradient nesting. The zero-control also checks the
algebra before the exact-return override, avoiding a tautological equality test.

The API remains a research kernel. Before selecting broad numerical ranges, add
near-one rho, tiny positive prior, disjoint non-clutter support and long-segment
stress tests. Subtraction in Z and the normalized redraw check can lose relative
precision near rho=1; explicit rejection is preferable to silently modifying the
transition. Current tests do not establish robustness arbitrarily close to one.
Input shape/finiteness and probability/normalizer invariants should be checked at
the composed adapter boundary; this kernel largely inherits the narrower component
input assumptions. Existing assertions must not be interpreted as complete public
API validation or used with Python optimization disabling assertions.

Full arrays for forward, backward, retention and redraw increase the O(NK) memory
constant. A later embedded implementation should accumulate by bounded segment
and measure its memory/time. The current source does not implement that reduction.

Next work may construct a synthetic composed objective with all physical and
clock Jacobians and unchanged priors, c=0 RF locks, packing and reset tests.
Positive-rho recording work still requires a separate frozen protocol, matched
arms and independent position evaluation. Marginal preservation removes the
previous unconditional label-bias confound; it does not prove physical track
identity, a correlation time, or improved localization. No rho was selected and
no recording evaluation or freeze was performed during this review.
