# H1–H7 causal frame-CFO holdout preregistration

This protocol was committed before any H1–H7 frame-CFO outcome was opened. The
metadata-only holdout has SHA-256
`547655cdf6a3bee84ae6877e2990083dad60d429b673b8d75e56b28d4e060dee`; the closed
replay protocol has SHA-256
`fafc327fb7670f30835b53dbb47f3d39541a1aa04fe1100f8cc7e15718d17345` at commit
`cd7868b7792f145ecc172f69ec4c58a0023f8064`.

## Frozen comparison

The sole decision comparison is `fixed_500ms` against `fixed_125ms`. The failed
adaptive selector and all other histories are diagnostics only. Horizons are 125,
500, and 1,000 ms. Only past even-Qin-qualified frame CFO updates a tracker; future
odd Qin supplies the response and cannot select a source, tile, target, support mask,
reset, retry, or method.

Every 11.875–19.5 s frozen interval is divided geometrically into equal-width,
half-open tiles no longer than 2 s. Each tile independently repeats exact
branch-bound 20 ms GLRT source/epoch selection within 75 ms of its midpoint. A tile
is a hard tracker segment: no history or forecast crosses its boundary. Tiles cannot
be moved, resized, dropped, retried, or substituted after response data are known.
Counter-verified application refills remain continuous; actual device gaps fail the
eligibility check.

For each capture, method, and horizon, squared odd-Qin forecast errors on the paired
mask are averaged within device-sample-anchored 1 s blocks, then blocks are weighted
equally. Capture MSEs are then weighted equally across H1–H7. Thus the replication
unit is the capture, not the frame.

## Decision rule

The fixed 500 ms challenger passes this seven-capture advancement gate only if every
condition holds at all three horizons:

- equal-capture RMS ratio to fixed 125 ms is at most 0.90;
- every individual-capture RMS ratio is at most 1.05;
- all H1–H7 are evaluable;
- every capture/horizon has at least 100 paired forecasts in at least five nonempty
  recording-anchored 1 s blocks; and
- paired coverage is at least 90% of the response-blind eligible targets.

A valid run that misses an effect condition is `scientific_fail`. A digest,
provenance, continuity, fresh-binding, or support failure is `inconclusive`. No
frame-level p-value or IID bootstrap is used: seven selected captures and correlated
rolling forecasts do not justify one.

## Interpretation boundary

A pass would establish conditional generalization of a 500 ms causal line for
receiver-relative apparent-CFO forecasting inside frozen GLRT source/epoch/alias
hypotheses. It would not authorize Standard promotion, identify a satellite, resolve
physical Doppler or range acceleration, calibrate uncertainty, or validate end-to-end
sensitivity. Upstream GLRT source selection used both Qin parities. Seven holdout
captures also remain below the ten-unseen-capture promotion floor.

The frozen cohort contains seven distinct sessions totaling 104.55 s. It covers both
radios, receivers, and spectral edges, but is imbalanced (radios 5/2, receivers 4/3,
upper/lower edges 5/2), so no subgroup claim is preregistered.
