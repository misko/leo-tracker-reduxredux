# Covariance geographic refit

Follow the fixed-position covariance screen with two prespecified models per
dataset: multivariate Student-t4 at 100 Hz scale, 20% nugget, and decay 0 or
10 seconds. Use all eligible tracks in each published first-eight panel.
Refit one position, eight recording timings, and one stationary offset per
candidate/track using training only. Same bank, visibility, full-catalogue
normalization and weak offset penalty (variance 1e12). No new observations.

Profile offsets globally: the likelihood-plus-prior stationary equation is a
cubic. Certify its unique root where possible; otherwise evaluate every real
root between zero and the GLS center, selecting the global minimum. Polish
stationarity and require absolute derivative below 1e-8. Use envelope gradients
with central prediction differences 1e-4 km and 1e-5 seconds; visibility must
stay unchanged under perturbation.

Two starts per dataset/model: original polished iid panel point/timings and
inherited geographic origin with zero timings. Fit L-BFGS-B within +/-12 km
and +/-5 seconds, maxiter120, maxfun180, ftol1e-12, gtol1e-6, maxls30. Each
worker capped180 seconds/4 GiB, one BLAS thread; at most two concurrent workers.
Select successful interior fits by training likelihood, requiring gradient
infinity norm <=0.01. Preserve timeout/failure evidence; no automatic retries.

Before fits, check each model's gradient at the original point against full
objective central differences for east/north and first timing at steps
1e-3 km / 1e-4 seconds, tolerance0.002. Record initial scores after nuisance
refitting, separately from earlier frozen-offset shadow scores.

After selection, held scores use exact joint-minus-training mixture densities
with training-only profiled offsets. Compare geographic error against the
original iid baseline and zero-correlation control, reporting held changes
separately. Ground reference is the already exposed unsurveyed operator pose.
No reference enters fitting or start selection. Profile local positional
curvature using a finite-difference full Hessian and Schur elimination of
timing parameters; this is an identifiability diagnostic, not a calibrated CI.
Final selected-point gradient checks are required before geographic promotion.
