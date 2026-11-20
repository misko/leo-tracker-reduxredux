# Prospective rule for the frozen four-region transfer panel

The 900 s StarLoc captures contain short Doppler arcs which need not be evenly
distributed across the scan. Take a contiguous endpoint block within each arc
as a prediction target. Compare the same original four offers, causal TLEs,
anonymous frequencies, orbit model and spatial grid as the frozen receiver.
Do not use capture coordinates, catalogue matches from the source release,
array phases, signal-specific tuning or reference scores in inference.

Use the same maximum of 64 tracks and 12 points per track as the frozen
receiver. Require at least six distinct samples per track, subject to the
original duration and finite-value checks. Use the first two thirds of the
sampled times for fitting, with at least four training points and two held-out
points. Select the top 12 satellite hypotheses at sentinel positions using
training samples only. Reuse the frozen 180 Hz shape scale, 2 s phase prior
and 8 s phase bound. In each 25 km square, minimize training-only Doppler
shape loss using the original 7 by 7 grid and two refinements, with support
from at least three distinct catalogue objects. Estimate a constant additive
frequency bias and linearized time shift per training arc from its training
samples only.

Evaluate each region's training position on the held-out samples with its
training orbit choices, biases and phase shifts fixed. Held-out residuals
use the original robust score, with unsupported or invisible orbits
contributing zero and no use of held-out frequencies in candidate selection.
Rank regions by held-out score. At least three distinct catalogue objects
must satisfy both the training and held-out support threshold of three
times the 180 Hz scale. Require training and held-out scores at least 0.25,
a held-out lead greater than 0.025 over the best other offer, and a
training position more than 1 km inside the square. If any condition
fails, withhold the position and retain the selected region and training
point as diagnostics. Keep the training point on publication, without a
pooled refit to the held-out data. Missing trainable alternatives count as
zero. Exact regional ties withhold.

A constant additive RF offset is absorbed in each arc's training bias at its
fixed RF, so the procedure is algebraically invariant to replacing fitted
calibration by zero. Report both arms. Use the complete transfer panel with
separate groups for the 11 measured StarLoc and eight roof acquisitions,
the 40 simulated acquisitions, and the three empty recordings. Report
published coordinates, forced nominations, region-level correctness on
present offers and false region/position acceptance on missing offers.

The within-arc split validates a time extrapolation of the Doppler model.
Its observations share source extraction and can share systematic or
orbit errors. It does not supply independent site or satellite identity
labels. The three-object threshold and spatial boundary are heuristic
publication checks. Performance numbers for the new rule were not read
when specifying them.
