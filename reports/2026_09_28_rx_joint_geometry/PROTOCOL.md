# Joint presence and receiver-geometry refit

This experiment refits signal reception and presence parameters against the frozen empirical joint-count reference selected by calibration-only recording-held-out comparison. It evaluates whether geometry adds predictive information once both reference counts and target absence are represented. All evaluation panels are reused exploratory observations, not blind confirmation.

## Frozen evidence

Use the original pilot dataset/model and four-record disjoint confirmation dataset. Use `2026_09_28_rx_empirical_background/results.json:selected_model` (`joint`, 1,356 calibration reception windows). Freeze its full result digest. Retain original calibration feature center/scale, sigma=500 Hz, forecast/CFO/alias mappings and conditional retained nomination log priors. No new nomination, RF collection or raw-IQ analysis is permitted.

The empirical reference is unconditional mixed observational evidence, not physical absence truth. Frequencies remain uniform on each lane circle. Add signal candidates with the normalized joint count-ratio construction, integrating the original five-node shared normal RX latent state (SD=1). Invisible nominations have exactly the reference density. All raw candidates and qualified empty observations remain included.

## Joint calibration

Use only the six calibration recordings' reception windows. Fit D (first 3 saved features), E (first 4, adding elevation/up), S (first 6, adding horizontal line of sight), and T (all 8, adding differential tilt). Every arm also fits stationary presence occupancy and reset-process persistence time. Relative emissions are zero for absence and log(signal-plus-reference/reference) for each nominee. Use the exact continuous-time refresh process from the presence experiment, actual gaps and full log-domain finite nomination priors.

Maximize total calibration relative log evidence minus Gaussian penalties: beta SDs [2,1,1,0.5,0.5,0.5,0.35,0.35], logit occupancy SD=2 centered at zero, log persistence time SD=1.5 centered at zero. Bounds are beta [-12,12], logit occupancy [-7,7], persistence [0.1,10] seconds. These priors and bounds are fixed before execution.

Each arm has two deterministic starts: neutral beta [-2,0,...] with occupancy 0.5 and tau=1; and the previous nested arm's fitted parameters with added beta entries zero (D instead uses the old D beta with occupancy 0.5/tau=1). Use L-BFGS-B, maxiter=100, maxfun=2000, ftol=1e-9, gtol=1e-5. Save all optimizer outcomes. If neither start converges for an arm, stop without evaluating. An exact absent-only model has relative evidence and penalty zero. Select it if no converged nonnull fit has strictly positive penalized gain. Do not force nonzero presence. All four selections complete before scoring evaluation observations.

## Evaluation and controls

Keep the pilot four-record panel and disjoint four-record panel separate; additionally report the equal-eight-record mean. Carry reception posteriors into held windows and score each held window before updating. Export per-record full and relative log scores, denominators, posterior presence and conditional nomination. All arms and controls use identical paired windows.

For D/E/S/T shift forecasts by a fixed quarter alias period, without refitting. For T also swap receiver geometry and reverse geometric trajectory as previously defined, without refitting. Report each arm versus reference, E-D, S-D, S-E, T-S, T-swap, T-reverse and every arm versus its frequency-shift control. A general geometry benefit requires beating D and the reference; a horizontal LOS claim also requires beating E. Differential tilt requires beating S and both geometry controls. Reused outcomes, mixed signs, boundary fits or a deficient reference limit promotion even if means improve.

## Verification and execution

Verify normalized signal likelihood/Poisson equivalence, batched HMM agreement with the scalar filter for ragged lanes and tiny log priors, calibration isolation, reference identity under null and invisible nominees, and score denominators. Freeze source, test, protocol and input hashes before the run. One numerical thread, nice19, 4GiB, at most300seconds for fit and evaluation; preserve unsuccessful runs, with no retuning based on held results.
