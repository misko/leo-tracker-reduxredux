# Shorter coherent segments: bounded follow-up

Design recorded October 7, 2026 before final evaluation. This extends the earlier
GLRT comparison without changing its files, production algorithms, or fixtures.
Use existing saved IQ and seeded simulation only; no RF collection.

## Question

Can shorter coherent segments increase detection while preserving useful CFO
accuracy and avoiding a material loss on coherent signals? Treat a higher score,
a larger candidate count, and better frequency recovery as distinct outcomes.

The primary comparison holds the total aperture at 64 pilot symbols and sums
power across 14 frames. Segment length changes the assumed phase coherence,
not the amount of data. All searched methods share the 512-point CFO grid.

## Prespecified methods

- Existing 64-symbol coherent-ceiling exact-minus-control margin.
- Full-aperture Gaussian matched-subspace score with template-energy handling.
- Nonoverlapping coherent segments of 8, 16, 32, or 64 symbols, with segment
  powers summed at one common CFO. Each segment has a free complex amplitude.
- Smooth phase-kernel quadratic scores with correlation weights
  `exp(-abs(i-j)/L)` for L = 8, 16, 32. These retain nearby-symbol products across
  arbitrary block boundaries and are not claimed to be exact deterministic GLRTs.
- Exact-minus-control versions as explicit specificity diagnostics.
- A multiscale union over 16/32/64-symbol scores. Estimate each member's null
  location/scale from separate training nulls, maximize the standardized scores,
  then calibrate the union's own threshold on another null sample. Selecting
  among lengths incurs a search penalty; do not reuse individual thresholds.

Potential hybrid CFO estimation (short-segment detection with coherent CFO) is
reported separately if evaluated. An oracle choosing the best segment after
observing evaluation truth is an upper bound, never an implementable detector.

## Simulated development and evaluation

Use fresh seeds and shared exact/control projections from the actual sampled
pilot-template Gram matrix. Within each trial, frames share a true CFO but have
independent unknown phases. Test coherent signals, phase-increment standard
deviations 0.15/0.35/0.6 radians, and an abrupt pi phase jump at a random symbol
within each frame. SNRs are -18, -15, -12, -9 dB per symbol correlation. Colored
noise and a coherent tone are separate specificity/mismatch stress tests if the
bounded runtime preflight supports them.

Before inspecting development outcomes, freeze this primary selection rule:
choose at most one natural short-segment, phase-kernel, or calibrated-union
candidate maximizing average joint detection and CFO error at most 1 kHz over
the prespecified noncoherent development scenarios/SNRs. Require no more than
five percentage points of coherent-signal detection loss at -15 dB relative to
Gaussian64; record performance relative to current margin as well. If no
candidate qualifies, report that result rather than relaxing the constraint.

Normalization training, development, threshold calibration, and final evaluation
use separate seeds. Expected counts are 2,000 normalization nulls, 400 development
signals per condition, 3,000 calibration nulls, 5,000 evaluation nulls, and 600
evaluation signals per condition. Runtime preflight may reduce these counts
before outcomes and final configuration are frozen. No tuning on final results.

Primary decisions use frozen thresholds at nominal 1% conditional false alarms.
Report achieved false alarms and uncertainty; threshold exceedance and joint
detection/CFO success separately. A descriptive evaluation-set ROC at common
observed false alarms is additional evidence, not a retuned operating threshold.
Use paired decision differences for uncertainty on method comparisons, with
explicit conditioning on the realized training/calibration.

## Saved-IQ evaluation

Select fifth/sixth visits in every DS5 sample-rate/split block independently of
outcomes. These differ from the previous comparison's scored first/second and
covariance-training third/fourth visits. They are not a new external dataset:
other historical DS5 experiments may already have used them.

On the first 20 ms of each visit/receiver, run the existing full acquisition
once with eight candidates. All scorers share this inventory. For each
method, choose the candidate using the first window, then evaluate later
40--60 ms IQ at that candidate's frozen timing and total CFO. Primary later
confirmation does not re-search timing or frequency. Exact and control evidence
use the same fixed hypothesis. Any searched-later diagnostic is labeled separately.
Later confirmation is descriptive; intermittent signals may disappear.

Extract 64, 128, and 256 symbols where complete frame support is available.
Within each aperture compare coherent and segmented methods on identical
observations. Across apertures, additional data and different supported frame
counts are an explicit second factor; do not attribute all gain to segmentation.

Add bounded raw-IQ injection controls on development and separate holdout
backgrounds, balancing rates/edges where the source permits. Freeze pilot power,
timing/CFO, and phase settings before holdout. Include both exact and wrong-pattern
injections. Re-run one common full acquisition per injected case, so tests measure
recovery of a planted hypothesis instead of assuming it survived acquisition.
Unmodified backgrounds can contain real signals: score or hypothesis recovery
changes do not supply a calibrated real-RF false-alarm denominator.

## Review and constraints

Workers own separate method, simulated, and recorded experiment files. Each
component includes tests. Freeze code/configuration before final runs and check
source/input hashes again afterward; preserve failed or preliminary receipts.
Use single BLAS threads and bounded minute-scale jobs. No hardware or services
are opened or changed. No localization weighting or position claim is made;
any subsequent localization experiment requires matched fitted-c versus c=0.

The root reviewer checks numerical equivalence, direct likelihood/quadratic
oracles, splits, search penalties, shared candidate geometry, source provenance,
and saved decision counts before deciding whether better detection is supported.
