# Geometry and measurement-precision preparation

This iteration supplies tested mathematical diagnostics and an input audit, not
new positioning results. Production B7 is unchanged. No recording was fitted or
evaluated, and no new experiment protocol is frozen here. The full193 recovery
comparison still occupies both recording workers; the frozen iteration110
persistence pilot remains next in the queue.

The [remaining-model review](REMAINING_MODELS.md) explains why rescuing catastrophic
search failures alone cannot establish the 0.4 km mean target. It also records
negative evidence from prior changes and uniform frequency-width adjustments.

## What is implemented

The adapter builds the exact local frequency derivatives of ordinary B7 geometry,
timing, receiver clocks, RF stretch and satellite corrections. It keeps every soft
satellite responsibility and respects both c=0 and fixed RF-drift locks. The
observability helper projects position derivatives off the nuisance span using
thin SVD, with explicit scaling and rank tolerances. This measures conditional
data sensitivity, not calibrated position uncertainty. Actual priors and active
bounds are not silently counted as measurement information.

Freezing satellite labels is optimistic. A separate locally affine mixture
curvature helper subtracts the categorical score covariance, including the
zero-score clutter component. Ambiguity can make observed local curvature
negative even when the frozen-label information is positive. Negative eigenvalues
are not clipped into an apparent covariance. Orbit second derivatives, visibility
changes and wrap discontinuities remain outside this local approximation.

![Synthetic illustration of categorical ambiguity](synthetic-ambiguity.png)

This illustration uses two synthetic Gaussian hypotheses; its horizontal axis is
an arbitrary scalar parameter, not kilometres or a scan-derived position. It is
an explanation of the approximation, not evidence of an accuracy improvement.
The [mathematical review](ADAPTER_REVIEW.md) details the limits and permitted use.

## What the measurement inputs support

The [input audit](MEASUREMENT_INPUT_AUDIT.md) finds measured CFO, detector margins,
timing and reconstructible sample support, but no calibrated per-window CFO
variance or SNR. The projected uncertainty is a fixed frequency allowance plus
capture timing uncertainty. It must not be repurposed as measured precision.

An orbit-blind repeatability screen is feasible in principle, using nonoverlapping
same-lane observations and locally affine-path-cancelling differences. Curvature,
clock changes, spectral switching and selection effects remain confounders. A
predictive check on whole recording groups is needed before defining one global
weighting rule; no per-scan reference-error tuning or missing-member exclusion is
permitted. Existing datasets remain consumed development data.

The next step is to specify a bounded recording audit after reviewing these
diagnostics, not to deploy an uncalibrated weighting model. No accuracy benefit is
yet quantified and the 0.4 km objective remains unmet.

Validation: all24 synthetic tests pass under the production numerical interpreter.
They cover prediction derivatives, c=0/fixed-RF locks, exact confounding, nuisance
rescaling, affine-mixture Hessian finite differences, ambiguity, clutter and input
validation. Rendering the illustration exposed a probability-sum roundoff edge
case; the helper now accepts a documented1e-12 tolerance without renormalizing
values or clipping curvature. The regression test includes a normalized pair
whose floating-point sum exceeds one and rejects substantive excess. The PNG was
generated and visually inspected. These checks qualify the diagnostic code, not
its usefulness or accuracy on recordings.
