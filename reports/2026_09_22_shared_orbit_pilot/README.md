# Full-catalogue shared-orbit pilot: predictive improvement, still kilometre error

On the 19-track scan `scan-fw-3bee6be6e987a34f`, fitting one orbital-rate
correction per NORAD improved held-out prediction. Allowing receiver position
to move improved it further. Exact SGP4 replay confirmed the computed scores,
but the resulting receiver position remains **5.89 km** from the evaluation
reference. This does not demonstrate blind sub-kilometre positioning.

This pilot uses a subset of the five-scan cohort and starts from that cohort's
previously sealed Sacramento solution. It is **not** an independently acquired
single-scan position result, nor the completed three-region comparison. The
primary 39-track single scan and complete 165-track set are separate experiments.

| Model on the same 19 tracks | Negative log posterior ↓ | Held-out log predictive ↑ |
|---|---:|---:|
| Original orbit, fixed blind position | 884.6642 | −679.0284 |
| Causal nominal orbital phase, fixed position, zero fitted rate | 883.2245 | −681.7351 |
| Causal phase + shared fitted rates, fixed position | 845.1565 | −645.0383 |
| Causal phase + shared rates + local position | 833.9567 | −640.2757 |

The causal mean alone worsens held-out prediction by 2.71 log-score units. Rate
fitting improves it by 33.99 relative to the original orbit; moving position
adds 4.76. Scores are Gaussian composite likelihoods with effective count six
per track, not calibrated probabilities. They are not comparable to raw-count
scores from earlier reports.

## Model and safeguards

All 11,109 causal catalogue objects retain their prior denominator. Each track
sums over candidate identity and an explicit broad unassigned component.
Training-only constant frequency offsets are profiled per candidate/track.
A NORAD has one shared Gaussian-prior rate variable across its occurrences;
rates are MAP estimates, not marginalized orbital uncertainty. The frozen rate
prior sigma is 0.09176615913014215 seconds/hour and bounds are ±0.25 seconds/hour.
Causal nominal phase plus rate times capture-start element age shifts orbital
propagation; Earth rotation remains at receive time. Identities and nuisance
parameters are fitted jointly without receiver truth.

Training uses chronological blocks 0/2/4; held-out blocks 1/3 are within-span
interpolation checks, not future prediction. Position, rates, offsets, and
identity weights are frozen for prediction. The saved Sausalito reference was
read only after the joint fit and exact replay finished.

One fixed-position fitted rate (NORAD 59572) reaches +0.25 s/hour. This is a
model/identifiability warning, not evidence of a uniquely measured orbital
error. The joint solver reports convergence by relative objective reduction;
its projected gradient maximum is 0.000193, so this is a numerical local
solution rather than a proof of global optimality.

LNB geometry is not a new positional constraint in this experiment. Earlier
paired-receiver tests did not establish added predictive benefit. Nominal
80 mm geometry is too weak to explain hundreds of hertz of residual Doppler,
and RF phase-centre/pose calibration remains absent. We do not attribute this
fit to geometric phase or count the two receivers as independent geometry
measurements merely because they observed the same signal.

## Numerical qualification

Small ±1-second quadratic state support failed at 6.7084 Hz maximum error over
sampled rate bounds. The replacement uses five rate nodes spanning the actual
±0.25 s/hour domain, with candidate-specific phase shifts and fourth-order state
interpolation. No extrapolation is permitted.

At four off-node rates, 844,056 candidate/track comparisons had maximum error
0.00012873 Hz and no training-visibility differences at the fixed blind
position. This is sampled validation, not a continuous interval proof.

Exact replay at the fitted rates and positions then checked all 211,014 valid
candidate/track occurrences. Maximum errors were 0.00000317 Hz for fixed
position and 0.00000327 Hz for joint position, with no visibility changes and
essentially identical predictive scores.

Three catalogue objects are explicitly zero-likelihood under the propagation
policy: 46375 and 54015 fall below the existing 6478.137 km radial support floor;
59322 fails propagation. They account for 57 exclusions across 19 tracks and
remain in the full prior denominator. Their rejection was checked at sampled
rates and final fitted support; no continuous-support theorem is asserted.

## Artifacts and scope

- `artifacts/` contains sealed controls, fitted rates, exact replays, off-node
  qualification, and evaluator-only position error.
- `comparison.png` plots held-out score changes and exact-replay errors.
- `render.py` regenerates the figure from the saved artifacts.
- `manifest.json` binds every published artifact by SHA-256.

The runtime implementation and broader fits are still being qualified and are
not promoted to the automatic analysis pipeline by this report. No production
deployment or new RF collection was performed. The next experiment must compare
the primary single scan and complete five-scan set from all three independently
acquired blind basins, with matched controls and exact finalist replay.
