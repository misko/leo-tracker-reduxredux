# Known-site and known-emitter diagnostics

Use the corrected four development captures and their existing shuffled
control. Reconstruct native rate tracklets with the locked rate-triplet
seeding, extension and shape-screening logic. Retain the probe epochs
from the selected raw peaks. Use twelve evenly spaced raw points from
each qualifying segment. Fit on the first eight and score predictions
on the last four with candidate IDs and nuisance parameters fixed.

In the known-site diagnostic, search every causal catalogue object
visible throughout the sample times at elevation above five degrees.
Retain a common shortlist of sixteen by training-only centered Doppler
shape for all subsequent comparisons. Compare shape, shape plus shared
absolute CFO, shape plus frame drift and all three observables. Absolute
CFO profiles receiver intercepts and drifts, with or without an RF
coefficient. Frame drift profiles a per-track transmit phase and a common
sample-clock slope. Use the same four assignment updates, candidate roster
and sample budget for the two calibration arms. Score satellite identities
from the planted labels only after choosing candidates.

The known-emitter diagnostic assigns each qualifying segment its planted
NORAD from the sealed radio schedule. Search the global 1,536-point mesh
using centered Doppler and frame-delay shape before fitting position and
common nuisance parameters from the same four geographically separated
seeds in both calibration arms. Score positions and held frequency and
epoch residuals separately. The shuffled input has no emitter or site
label and is tested for qualifying raw tracklets. These are development
oracle measurements, with no truth passed into any deployable receiver.
