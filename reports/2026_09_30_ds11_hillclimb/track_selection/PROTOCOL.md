# Detector-to-track selection transfer screen

Use DS10 family2 donors16 (training visits only) and17 (all visits, separate
recording). These are the already designated calibration/validation recordings.
Export existing public tracking inputs only. For every unique projected raw
candidate passing the fractional margin gate, label whether it belongs to any
track in the existing baseline observation export. Reconstruct membership using
the unchanged public persistent trajectory projection (3s minimum span, support6).
Verify every exported baseline track is found. No inferred satellite labels or
geographic reference is used. Rejected candidates are counted but excluded from
the conditional pass-to-track model. A retained label is not a physical detection
label, source activity, or proof that a candidate belongs to Starlink.

Compare ridge logistic models: receiver and RF versus receiver, RF, fractional
exact and control scores. Treat scores as detector statistics, never RF power.
Standardize non-intercept features using only training rows, weighted so each
receiver/window has total weight one. Same weights apply to likelihood fitting
and assessment; ridge coefficient1 on non-intercept standardized coefficients.
No strength-feature search, lambda search, per-record retuning, or DS11 fitting.
Use zero initial coefficients, analytic gradient, max200 iterations. Require
optimizer success, finite parameters, gradient max <=1e-5 and central gradient
audit <=1e-5. Score probabilities with stable log logistic formulas.

Gate before further integration: separate-donor weighted mean log probability
gain >0.01 nats and improvement in more than half of validation visits. Preserve
all qualifying projected candidates and all visits; no positive-only subset.
Failure ends this model unchanged. Passing licenses further selection-model
research only, not positioning promotion. Unseen physical sources, clutter,
undetected signals, and time dependence remain unmodeled.

Two metadata export children at most90s each, at most three single-thread workers;
numerical fit child at most90s. No new RF, QNAP writes, or production changes.
