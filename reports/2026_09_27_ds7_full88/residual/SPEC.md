# Fixed-prediction audit after the full88 attempt

This specification is frozen while the full88 joint fit is running, before its
prediction or geographic score is available. It does not modify that fit.

If the attempt produces a sealed response with an estimate and timing vector,
evaluate its fixed training and held predictions against all 88 frozen
independent predictions using unchanged `tools/ds7_residual_audit.py`, SHA-256
`a560a1006a219a21ca7d3df1664d56cc2dfeb35c1e9b77330ee6f0bc5c677e2f`.
Use the exact full88 request/response and the plan-ordered paths in
`independent-response-index.json`. Verify every source request/response/seal
binding and identical per-recording input artifacts before evaluation.

Keep all 88 recordings, including boundary-unqualified single062. Report its
qualification explicitly; its diagnostic residuals do not turn it into a
qualified location estimate. Retain any further failures or missing outputs.
If no complete joint prediction exists, record the audit as unavailable;
do not fit a replacement or use a partial optimizer state.

The existing analyzer fixes candidate responsibilities and offsets from
training data before held prediction. Report training and held scores
separately, all recording comparisons, receiver/channel and RF strata,
candidate concentration, and exploratory partition-centered residual slopes.
Slopes are diagnostics, not calibrated drift states. Do not select captures,
weights, features, bounds or another model using geographic error or held fits.

Run only after the full88 fit terminates and is sealed, with no other DS7
preparation/fitting. Require at least 16 GiB available memory. One CPU/BLAS
thread, nice19, inherited 8 GiB address-space ceiling, 300-second whole wall
limit; retain a timeout/failure without extension or automatic retry. The
previous eight-recording audit completed in under 11 seconds. This is a new
bounded fixed-prediction evaluation, not additional optimization time.

No raw IQ, RF collection, dataset reference, pose or geographic score access
is permitted in this audit. Root scores locations separately. Residual or held
prediction improvement cannot substitute for the full88 sub-km goal.
