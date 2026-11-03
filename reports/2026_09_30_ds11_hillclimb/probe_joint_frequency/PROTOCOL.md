# Joint versus separate pilot frequency refinement on common samples

Retain all six frozen probe-coexistence pairs, including its two negative
cases. Reuse saved IQ and identical per-probe training/held masks; no new reads,
source selection, orbit data, localization-held IQ or geographic scoring.
The three prior real controls validate the waveform convention but do not
enter this two-candidate frequency comparison.

Three arms use the same joint16-column gain model on the same samples:
cached acquisition frequencies; frequencies separately optimized for each
candidate; and frequencies jointly optimized while profiling both gains.
Thus the joint-versus-separate comparison isolates frequency selection rather
than changing which signals are reconstructed in the final predictor.

For separate fits, scan native residual frequencies from-1500 to+1500Hz in
25Hz increments and refine the best interior interval. For joint fits use two
starts: zero residual and the separate estimates. Use analytic variable-
projection derivatives, L-BFGS-B,80iterations/120function calls per start,
and the same frequency bounds. Keep both starts. Qualification requires solver
success, interior estimates, gradient maximum below1e-5 per kHz and central
finite-difference discrepancy below1e-6. Highest training likelihood selects
among qualified starts. Store that selection before held scoring.

Report all six cases and failures. No retries, changing bounds, replacing
cases, or choosing frequencies from held scores. Separate-boundary estimates
remain explicitly flagged and cannot support a qualified joint-versus-separate
comparison. A joint failure yields unavailable held comparison, not a new seed.
No position propagation is authorized by this pilot alone. Advancement to
a larger measurement test requires joint held NMSE below separate on at least
five of six cases, positive median paired gain, and all six comparisons usable.
This is an engineering gate, not a calibrated statistical significance test.

One worker capped at120seconds, one BLAS thread, nice19. Mark rows active before
numerical work and preserve interrupted/failed/unattempted records. Bind all
prior sources, excerpts, code and tests before execution. Verify analytic
derivatives and synthetic two-frequency recovery before opening real excerpts.
