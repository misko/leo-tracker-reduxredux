# Geometry evidence relative to receiver-only source likelihood

The fixed-position ablation found the same ten high-confidence identity changes
with signed and receiver-only temporal emissions, and none with Doppler alone.
Test source factors equal to the signed temporal receiver likelihood divided by
the calibrated receiver/RF-only temporal likelihood, at the same source/window
assignment and common learned tau. Add log ratios to the original Doppler
factors. The denominator is independent of station position and timing; it uses
observed window times, fixed RF intercepts and the same ownership branch.
Do not renormalize individual states after subtraction: subtract complete source
sequence log likelihoods. Include all original candidates and exact assignments.

This is a conditional likelihood-ratio/composite experiment, not the completed
generative detection, source-count or clutter model. No arbitrary evidence
weight, new coefficient fitting, target-error tuning or stronger spatial prior.
Use the same eleven-record panel and calibration-selected Doppler fallback for
families3/5. Unsupported 2.5MS/s settings remain fallback in any full-corpus
continuation. Failed/fallback records are never dropped from accuracy scoring.

Verify that receiver-only numerator exactly cancels the denominator and recovers
Doppler-only score, gradient and source-count posterior, including ownership
alternatives and held scoring. Compare correlated multi-fragment assignments
against enumeration and audit real-scan derivatives before optimization.

Fit 22 cells (Doppler, candidate) from the original IID seeds, EN±12km/time±5s,
L-BFGS-B maxiter100, ftol1e-13, gtol0.001, maxls25. Qualification remains solver
success, bound margin≥0.001, raw gradient≤0.01 and derivative discrepancy≤0.02.
Each child≤90seconds, at most three single-thread workers. Preserve all failures.
Only read reference errors after every terminal receipt. Use the unchanged
cohort-separated gate: every fit qualifies, median improves≥5%, strict majority
wins and no P90 increase against both original IID and refitted Doppler. Passing
still requires further controls and wider confirmation. No selective retries.
