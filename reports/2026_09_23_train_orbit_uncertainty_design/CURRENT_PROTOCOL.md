# Executed TRAIN orbit-transfer pilot

The causal historical prior and four-arm positioning pilot are complete;
see `FINDINGS.md` for the sealed geographic evaluation. The earlier design
is retained in `DESIGN_SUPERSEDED.md`; its pooled initialization and fixed fitted
scan epochs were replaced by the design below.

Use the first six scans of each frozen TRAIN group, separately for the
Sacramento 250 km and Reno 500 km prior disks. Each arm starts from its own
sealed tau-zero blind baseline and its own training-only satellite assignments.
There are 476 tracks per prior in the first group and 298 per prior in the
second. These are fixed-assignment positioning experiments, not new joint
satellite-association searches.

The three stages use identical observations and randomized masks:

1. Uncorrected causal elements, recorded receiver UTC, and a constant frequency
   offset per track profiled from training rows only.
2. A causal point prediction of orbital phase error with the same clock and
   per-track offsets.
3. One correction rate per NORAD, shared across its assigned tracks and scans,
   multiplied by element age around that point prediction. The bound is
   ±0.25 s/hour, regularized using the historical prior width.

An orbital correction advances inertial satellite motion, not Earth's rotation
time. Frequency normalization remains the baseline's 11.2 GHz convention. The
inherited robust RF scale is 250 Hz and prior-residual conversion is 100 Hz.
Each selected candidate's epoch is parsed from its exact session snapshot.

SGP4 supplies nominal and point-mean ±1-second states. Fitting uses quadratic
phase-state interpolation; final rates are checked against direct SGP4.
Held-out measurements are perturbed by 1 MHz and refitted from identical
initialization to check parameter isolation. Reference-position error is not
used by the fitter or prior learner.

The historical prior population contains 2,689 blind fixed TRAIN NORAD IDs.
Both archive collection and element epoch precede the earliest TRAIN cutoff.
The unchanged model-selection rule chooses median absolute final-transition
rate error, then uses that winner's validation RMS as the width. Ridge alpha
0.1 wins, with median absolute error 0.03209 s/hour and RMS 0.16029 s/hour.
These are catalogue-update residuals, not calibrated errors against orbital
truth. The unchanged fit bound is about 1.56 times this width; bound saturation
must be reported. The amended replay's frozen model equals the original exactly.

`cutoff_receipts.json` independently verifies all 12 sessions and 774 distinct
tracks through the public store. Reconstructed anchors match original
first-sample estimates at zero-nanosecond difference; observation-ID order and
support times match. All snapshots precede first-sample-minus-505-second cutoff.
This is a transparent post-execution verification, not a pre-execution assertion.

`EXECUTION_ATTEMPTS.md` records the first process ending without a recoverable
result and the logged second attempt. Partial checkpoints are not completed
four-arm results. Lower RF residuals on these exposed TRAIN data cannot alone
establish sub-300 m generalization.
