# Finite-window Doppler sensitivity

Two symmetric 20 ms averaging scenarios produce negligible local position changes across the 12 development scans. Uniform averaging gives shifts of 0.0010–0.0159 m; equal mass at the two endpoints gives 0.0030–0.0477 m. Maximum changes to retained frequency contrasts are respectively 0.001003 Hz and 0.003009 Hz. These scenarios do not support finite-window orbital curvature as a kilometer-error explanation.

The scenarios span the observed checking-candidate support durations, whose per-scan maxima are 18.9498–18.9544 ms. They are not reconstructions of the actual GLRT symbol weights or rigorous bounds over all possible support shapes. In particular, an asymmetric effective weighting that moves the mean time is not the same effect as symmetric averaging about the recorded mean.

At each sealed original fit, evaluate authoritative interpolated satellite position and velocity at the observation time and at offsets within ±10 ms. Project range rate onto the unchanged receiver line of sight. Compute uniform averages with 8- and 16-point Gauss-Legendre rules, and separately average the two endpoint predictions. Subtract the original instantaneous Doppler, apply the original per-track contrasts, and propagate the resulting mean perturbations through the fixed Student-IRLS position/nuisance information matrix with original Gaussian priors. Receiver drift is linear and therefore unchanged under symmetric averaging.

The maximum 8-versus-16 quadrature discrepancy is 3.50e-10 Hz. Reconstructed center predictions agree with the actual selected-track predictions within 9.10e-10 Hz after restoring receiver drift. All parent seals, source/input digests, height and observation bindings passed. Linear systems satisfy their normal equations. Runtime was 22.90 s total, with no nonlinear fits, reference-coordinate reads, or new RF collection. Source and results are `audit_window_average.py`, `window-average-v1.json`, and its SHA seal.

This is a fixed-state quadratic sensitivity calculation. It is not a geographic error, nonlinear refit, confidence interval, physical UTC calibration, or validation of the frequency estimator's effective symbol weighting. No production changes are warranted from this test.

## Return to statistical modeling

The recent audits found no exported timestamp error, at most 45 m of local sensitivity to nominal pilot/tuner frequency distinction, and less than 0.05 m to symmetric window averaging. Further small deterministic corrections are unlikely to close the accuracy gap represented by the current evidence. Group-level disagreement remains much larger.

A bounded next experiment should test a satellite-balanced composite score. Freeze original inferred identities, group the N signal tracks into G satellites with counts n_s, and assign each signal track weight N/(G n_s). This preserves total signal-track weight N while giving every satellite the same aggregate weight N/G. Keep clutter tracks and original nuisance priors unchanged, and use an otherwise identical all-weights-one control. No reference-based group exclusion or per-satellite tuning is allowed.

This is an explicit engineering composite objective, not a calibrated generative likelihood. It tests count-driven influence and may overweight weak singleton groups; a failure should stop expansion. It differs from the previously rejected shared latent residual-scale model, which preserves individual track marginals but couples their scale. Test exact gradients and the singleton/equal-group invariants before the three-scan warm pilot; require the full development panel, cold 64-scan benchmark and held-out validation before any promotion.

The full benchmark remains unchanged at 2,059.90 m median error, 5,850.75 m p90, and 64/64 acceptance. Accuracy and independent uncertainty-calibration targets remain unmet.
