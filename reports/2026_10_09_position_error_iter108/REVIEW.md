# Mathematical cross-check and next diagnostic

**Authorship disclosure:** this reviewer implemented `persistence.py`; this is a
separate derivation/enumeration cross-check, not an independent reviewer sign-off.
Only synthetic tests were run. Production Python 3.14 reports **six tests passed**;
Ruff passes. No recordings, reference coordinates, RF collection or fits were used.

## Findings

The [factorization](INDEPENDENT_LIMIT.md) matches the current hard60 score.
Writing `C = lambda + visible_count*q/(1-q)` and retaining
`D = p0*C/(1-p0)` recovers the original detection normalization; omitting `D`
would change the geometry preference. The identity mixture alone is insufficient.

The transition rows sum to one. A clutter predecessor resets; a predecessor
satellite invisible at the current row also resets. Forward updates require a
vector multiply and rank-one reset term, not a dense transition matrix. For the
backward update, define `u = emission_next * backward_next / normalizer_next`:
`backward_i = rho*active_i*u_i + (1-rho*active_i)*(pi_next·u)`.
This is precisely the transpose action of the same normalized transition.

Smoothed occupancy gives the correct prediction derivative
`-occupancy_satellite * circular_residual / sigma_hz²` when visibility is fixed.
The tests compare this both with exhaustive enumeration of 64 three-row paths
and with finite differences for every predicted frequency. They also cover
visibility/clutter resets, wrapped frequencies, arbitrary all-row reset boundaries,
and a 3,000-row scaled recursion.

At `rho=0`, production likelihood values and gradients are returned bit-for-bit.
That shortcut does not stand alone as evidence: a separate algebraic computation
of the factorized independent likelihood matches hard60 numerically. The kernel
is limited to the same narrow-width nearest-wrapped-Gaussian convention. It does
not claim differentiability across visibility or alias branch boundaries.

No blocking algebra defect was found. Important missing integration controls:

- The kernel accepts reset flags; it does **not** validate RF/channel/receiver/gap
  boundaries or overlapping track membership. Those belong to a separately tested
  reference-free adapter. A reset test is not an end-to-end RF-gap test.
- Multiple interleaved tracks must be packed as separate segments and mapped back
  to original observation order. Every observation must appear exactly once;
  uncovered and ambiguous-overlap rows remain independent.
- Physical/clock gradients follow by the chain rule, but there is no position
  wrapper and no corresponding integrated gradient test yet. Prediction-gradient
  tests must not be represented as complete position-model validation.
- This is a persistence assumption, not extra measurement information, verified
  satellite identity, or demonstrated localization improvement. A large `rho`
  could reinforce a wrong Hough path. No operational value of `rho` is selected.

## Smallest next recording diagnostic: opportunity and coverage only

Freeze a no-fit audit across the full 148 consumed DS16/17/18 members. Reuse the
immutable B7 reconstruction already validated in iteration87, verifying both
archived objectives before extracting responsibilities. Reuse frozen bootstrap
track memberships; do not select tracks, satellites or recordings by geographic
error. This requires objective evaluation, but no optimizer or new recording.

Apply the exact proposed conservative rule: unique track membership, same receiver,
channel and actual RF, positive adjacent gaps no greater than 2 seconds. Reset
every violation. Use the same fitted-derived membership for both c arms. Count
all rows, eligible rows/links, overlap exclusions, singleton segments and every
boundary reason. Report the full membership and any input failure explicitly.

Within those frozen segments, summarize satellite/clutter entropy, top-two
responsibility odds, and label switches at ordinary B7 endpoints. Separate
confident-to-confident switches from changes involving clutter or weak odds.
Compare these descriptive quantities with independent uncovered rows without
calling either population a validation set. There is no reference error input,
HMM fit, chosen persistence strength, or model selection in this audit.

The question is narrowly falsifiable: **does sufficient unambiguous track coverage
contain genuinely ambiguous window assignments for a persistence model to affect?**
Sparse coverage or almost deterministic assignments would argue against spending
position-fit budget on this extension. Frequent switches alone would not prove
errors; physical identity changes and blended/crossing tracks remain alternatives.

Only after that audit should a separately frozen protocol consider a global
persistence sensitivity with exact independent controls and matched c arms.
Do not claim held-out performance from tracks constructed using the same CFO
observations. The earlier negative inverse-count weighting and nuisance-flexibility
experiments remain reasons to require whole-corpus position and failure accounting.
