# Frozen tenth-second shared-clock refinement

Fix geography to point `p0007` from the sealed shared-clock inference
`sha256:1b862b50620433c33d8481be5d2f9769960299311e4be00688a73eb73ac8ee27`.
Perform no geographic proposal, selection, or cone fit.

Evaluate one receive-time shift shared across all tracks, candidates, receivers,
and twelve TRAIN scans on the integer-derived grid `k/10` seconds for
`k=-15,-14,...,-5`. This is exactly -1.5 through -0.5 seconds inclusive and
contains the previous -1.0-second solution exactly. At every shift, query the
unchanged cached ECEF states at recorded receive time plus shift, fit one
per-track constant CFO on randomized TRAIN rows, and select the ordinary visible
candidate by TRAIN RMS. Select shift by all-track occupied-second weighted
capped TRAIN loss at 800 Hz, preferring smaller absolute shift and then smaller
signed shift on exact ties.

Require the -1.0-second TRAIN and held losses to reproduce the sealed prior run.
Evaluate held loss only after each shift's TRAIN CFO and candidate assignment
are frozen. Report the complete TRAIN and held profiles and selection.

The grid spacing is a numerical refinement, not a confidence interval or clock
uncertainty estimate. The ±5-second parent range remains an uncalibrated
sensitivity range. Reference error is unchanged by construction and may be
restated only as the prior post-seal 3.015 km evaluation. Use no truth for
selection, no VAL/TEST, no new RF, no QNAP write, and no deployment.
