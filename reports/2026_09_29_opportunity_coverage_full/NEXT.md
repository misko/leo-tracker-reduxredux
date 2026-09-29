# Next bounded model comparison

Do not repeat a nominal-cone sweep merely because the opportunity inventory is now
larger. Earlier paired-state, presence, causal-reference and DS8-confirmation models
already retained empty windows and failed predictive promotion gates.

One distinct use of these observations is to test whether extraction context predicts
when a frequency track needs the unassociated-trend branch. The current geographic
baseline assigns every track the same 20% prior background probability. A receiver/RF
lane with mostly empty analyzed windows may have a different association reliability
from a consistently detected lane. That relationship is a hypothesis, not an observed
result or a verified satellite-presence probability.

Before any fit, join each track to the exact receiver/RF lane and compute opportunity
features using **training visits only**, following the existing deterministic visit
partition. Include empty training probes. Never use held detections, residuals,
location error or candidate identities to construct the features. Keep missing
features explicit. First establish complete and unambiguous joins for all tracks.

Then freeze a small comparison: existing q=0.20; a donor-fitted constant q; and a
donor-fitted logistic q using one smoothed training empty-window fraction. The latter
must beat the fitted-constant comparator, not just a fixed arbitrary prior. Use
whole donor groups for calibration validation, preserve all target tracks and
evaluate the normalized joint-minus-training frequency likelihood at unchanged
positions before any geographic refit. Re-export branch joint densities if needed;
do not reconstruct nearly canceled mixture components by unstable subtraction.

This would be an offline calibration experiment on disjoint donor and target scans,
not a strictly causal forecast unless chronological availability is additionally
enforced. No coefficient, smoothing choice, gate or subset is selected here; those
must be declared and tested before execution. Only a transferable predictive benefit
would justify a separately frozen geographic test. The existing sub-km objective
remains open regardless of a conditional frequency-score improvement.
