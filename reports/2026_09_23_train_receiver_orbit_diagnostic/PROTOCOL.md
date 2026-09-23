# Frozen TRAIN receiver/orbit residual diagnostic

Use exactly the 151 session IDs in the sealed pooled TRAIN inference; reject any
VAL/TEST overlap. Recover receiver IDs only through `ScannerTrackingInputStore`
and the same public preparation path and sealed causal TLE archive used by the
cache exporter. Bind every capture/analysis/TLE input and require exact track,
candidate, observation, and session joins. First require a complete join on the
first TRAIN scan; use at most four read-only workers for the full inventory.

At the sealed pooled scale-5 s fixed-ID position and scan epochs, recompute
training-row residuals without geographic truth. Profile one constant offset
per track. A receiver pair requires the same provisional candidate ID, scan,
overlapping receive interval of at least 3 s, at least 8 matched time samples
within 80 ms, the same channel/sideband and sample rate, and median absolute
frequency disagreement below 2 kHz after separate constant centering. Retain
all passing pairs; report every rejection reason. Candidate equality is a
provisional association, not known identity, and pairing must independently
satisfy time/frequency consistency.

For each pair fit centered residual difference and common mean versus centered
time with linear and quadratic terms. Summarize differential receiver slope and
curvature across whole scan/satellite groups, and common terms by causal element
age quartile and look-direction quadrant. Bootstrap whole scan/satellite groups
with seed 20260923; never resample individual observations. Report support and
ambiguity before effect estimates. No threshold may change after outcomes.

Interpret stable RX0-RX1 structure across diverse satellites, times, and looks
as evidence for a differential receiver/channel model. Interpret common-mode
age/look structure reproduced in both receivers as evidence for an orbit or
propagation hypothesis. Marginal age correlation alone is not causal evidence.
Poor overlap or conflicting strata is an inconclusive result and does not
authorize free timing, drift, or receiver position terms. No position refit,
held-frequency scoring, reference coordinate, VAL/TEST data, RF collection, or
deployment is permitted.
