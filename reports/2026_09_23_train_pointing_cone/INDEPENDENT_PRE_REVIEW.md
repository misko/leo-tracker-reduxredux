# Independent pre-execution review

Reviewed the frozen protocol (SHA-256
`25f6cbdd26f4496c6ad62d08e8a4e38ac3e3c6bfcca042ff21a00c3df0681a98`) and
locations freeze (SHA-256
`7af93dce9cf7e16ea0d4281fff71321b077f58c99895c01ccf84da79f6da9a33`). No
geometry evaluation, position fit, held-row score, reference coordinate, or
TEST input was accessed.

All six frozen locations exactly reproduce the cited saved ambiguity result:
the two 50-km Reno beam survivors and final selected point for each first- and
second-TRAIN six-scan view. The source result is bound by digest and the
freeze records `truth_used: false`.

The protocol appropriately fixes locations before geometry outcomes, preserves
both provisional RX-to-slot mappings and all tilt scenarios, requires
duration-weighted midpoint quantiles plus endpoint sensitivity, and describes
cone widths as support requirements rather than RF likelihoods. It correctly
forbids per-track/per-scan orientation fitting and use of the unmeasured
boresight as calibration.

Implementation review remains required before execution. The source must state
one ENU/body-frame convention for vertical, yaw, and arbitrary tilt azimuth;
construct two unit body axes exactly 20 degrees apart before applying each
receiver mapping; use fixed location-specific candidate identities and the
same candidates at endpoints; and bind training masks, duration weights,
prepared cache/metadata/TLE inputs, and a deterministic weighted-quantile
definition. No source, metadata checkpoints, or outcomes existed at review
time, so this is not execution approval.

## Source follow-up

The first `run.py` source review found two blockers before execution. It passes
absolute `support_*_utc_ns / 1e9` values to the compact causal cache
interpolator, whose grid is relative to the capture (for example, -3 to 305
seconds). That would reject the endpoint queries and mixes time frames. Strict
metadata must bind a sample-time anchor and the geometry source must convert
UTC support times to the cache-relative time frame, with a check against the
sealed track-time coordinates.

The literal yaw × tilt-azimuth × tilt nested loops also repeat work across the
0/15/30-degree scenarios and imply tens of millions of orientations and tens
of billions of track-angle products. Preserve the declared one-degree grid,
but evaluate each tilt only once per location/mapping, derive the three maximum
tilt scenarios from that output, and batch/vectorize the calculation under a
fixed memory bound. The reviewed source also fails Ruff. These are execution
blockers, not findings about pointing or localization.

The replacement source fixes the UTC/cache mismatch with a per-track median
anchor from the exact metadata center timestamps and sealed receipt times; its
reported alignment check is the right fail-closed invariant. The local ENU/body
axis construction preserves the required 20-degree separation and applies a
tilt followed by yaw about the tilted body-up axis. It still requires a
pre-execution amendment because the original frozen protocol specified
one-degree yaw/azimuth while the revised protocol specifies five-degree
yaw/azimuth. It also needs a bounded-runtime preflight or reuse of the single
0--30-degree orientation sweep for the nested 0/15/30 scenarios before the
full geometry run. Candidate existence/non-nullness and RX IDs in `{0,1}`
should be asserted with retained failure accounting.

## First vectorized output audit

The first vectorized result is sealed and binds the vectorized source, frozen
locations, caches, metadata checkpoints, and published scorer. The 155,592-row
shared orientation grid, 1,024-row batching, one-sort weighted midpoint
quantiles, fixed candidate/location support, ENU axes, and cache-relative time
anchor checks are sound. The batched/scalar tests pass.

It is nevertheless superseded for the endpoint sensitivity: the source flattens
the two endpoint angles and repeats each track weight. The intended quantity is
the maximum of the two endpoints *per track*, followed by one
duration-weighted quantile. Flattening can understate a required endpoint cone
and changes the stated interpretation. Correct the endpoint reduction and its
brute-force test, preserve this output as superseded, and rerun before using
any cone comparison.

## Final corrected output review

The corrected result is approved. It binds executed source
`95a1824b075dbe58241ff88804365edf3b432f0093a003fe5bc81bcee2bf3dd1`,
the pre-execution amendment
`d7fa190313626d8423ac64dd8afb2424a73d223a3a4687c72dc9a825366c21d9`, and
result `228cab1f0f50430f2ce7156f515d1d66ca22252ccd6ee28d41c3f9d59d59bc88`.
The sidecar matches. The corrected source takes the worst endpoint per track
before applying the duration-weighted quantile; its brute-force comparison and
specific endpoint regression now pass alongside the other three tests and
Ruff.

The report keeps the valid scope: final locations have smaller conditional cone
requirements than the frozen coarse cells, but the first near-tied coarse pair
has 80-percent midpoint cones 21.779 and 21.650 degrees. This cannot resolve
that association tie, identify the physical receiver mapping, or establish a
position-accuracy improvement.
