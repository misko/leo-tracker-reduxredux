# Interleaved trajectory mixture: withheld radio prediction

Process all 142 independent full tracks from the three first scans, not only the selected DS10 pair. For each track train on even-indexed observations and score odd-indexed observations, then reverse. This is correlated within-track prediction, not unseen-scan or geographic validation. Keep the original radio-only frequencies and times; no localization labels, state or GPS.

Compare one quadratic Gaussian trajectory against a two-quadratic Gaussian mixture with fixed noise sigma=100 Hz (primary) and 300 Hz (scale control). Fit by EM with six deterministic starts, at most 100 updates each. Require convergence, at least six hard-assigned training points and three seconds of training span per component. Unsupported or unconverged mixtures fall back to the single curve with the reason recorded. Components may have non-contiguous memberships. Score held observations with the normalized weighted sum of component densities, never the best branch.

Use the best supported converged training likelihood. Admit the mixture only when 2*(LLmix−LLsingle)>4 log(ntrain); double that complexity penalty as an ablation. This is a heuristic model-selection penalty, not calibrated BIC for correlated or singular mixture models. Do not use held observations to select starts, scales, components or penalties. Report raw-mixture and training-selected prediction separately.

Directional gate for integration: positive pooled held gain per observation and positive median paired per-track gain in each dataset under the primary selection rule. Report zero-gain fallbacks, full denominators and convergence failures. For the DS10 pair report both fold results rather than choosing a favorable fold. A pass justifies a separately bounded localization pilot, not accuracy or generalization claims.

Gaussian prediction is a diagnostic surrogate and is not the current Student-t localization likelihood. No assertion that this mixture beats the robust localization baseline follows from Gaussian predictive gains. Freeze source, partitions and policies; preserve every original observation and original benchmark arm.
