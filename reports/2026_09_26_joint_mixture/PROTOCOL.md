# Joint location/association/timing model: bounded feasibility prototype

This experiment conditions on three existing fixed locations in each of three scans: 08:10 and 10:30 large Reno failures, plus the first DS5 scan (07:00) as a clean control. The control's existing Sacramento/Reno errors are 5.8/4.0 km. No geographic search or production mutation occurs.

## Implemented model

- Satellite identity is latent per track, including an explicit unexplained-track state. All tracks remain in the likelihood.
- One orbit-time correction is shared by tracks assigned to the same satellite within a scan/location. It is integrated over a 0.1-second grid against the frozen signed historical age-conditioned prior.
- One scan-clock correction is shared across all satellite groups. Its diagnostic prior is N(0,1 second), discretized every 0.5 second over ±3 seconds. This prior has not been calibrated from absolute receiver timing metadata.
- Each track's constant frequency offset is analytically integrated under N(0,1 MHz). This is a proper broad prior, not an optimized offset without a complexity term. No polynomial drift is allowed.
- Observations and predictions are averaged within each occupied one-second bin, separately within the original training/evaluation masks. Gaussian block-noise scales 100/200 Hz are prespecified sensitivity settings, not estimated measurement uncertainty.
- The unexplained state has prior probability 0.1 and a normalized constant-only Gaussian frequency model with 3,000 Hz block noise, with the same broad offset prior. Remaining identity prior probability is uniform across the site's retained candidates. Neither the unexplained rate nor its scale is calibrated.
- Collapsed Gibbs sampling jointly updates identities and scan clock; satellite timings are summed out at every identity update. Two chains start from original IDs and all-unexplained, each with 80 burn-in sweeps and 160 retained sweeps. The no-clock sensitivity uses one chain. Agreement is a diagnostic, not proof of convergence.
- Reported score sums per-track joint predictive log densities and divides by total evaluation blocks. Shared training information enters those predictions, but summing their marginal scores is a **composite** score, not the full joint evaluation evidence or a location posterior probability.

## Controls

1. Frozen original IDs, no scan clock, historical satellite timing marginalized, identical block likelihood and integrated offsets.
2. Joint assignment/unexplained mixture, no scan clock.
3. Joint assignment/unexplained mixture plus shared scan clock.

Both 100 and 200 Hz block-noise settings are run for each control/site/scan. Timing and assignment inference never access evaluation likelihood arrays; evaluation values are used only after posterior draws have been produced.

## Preserved independence and provenance

Each location uses only its own earlier training-selected coarse top-three satellite candidates plus its own original ID. No site's candidate list, fitted correction, or geographic proposal is supplied to another location. A universal propagation bank may reuse calculations. Evidence and snapshot digests are checked against the original DS5 and shortlist artifacts. The historical calibration predates DS5.

## Limitations that prevent production claims

- Historical timing priors are **conditioned on ±120 seconds**; omitted continuous mass is reported. This finite-window approximation is not full unbounded marginalization, and expanding/renormalizing that support changes the approximation. Support-convergence and finer scan-clock-grid experiments remain necessary.
- Candidates were screened on earlier training data using a different objective and a coarse timing grid. Inference is conditional on this limited, data-selected list, not a full-catalogue identity posterior. Candidate inventory size affects the uniform identity prior.
- One-second aggregation reduces repeated-frame counting but is not a fitted covariance model. Same-bin train/evaluation overlap and dependence across receivers/tracks remain; their count is reported. Do not claim independent block likelihoods are calibrated.
- GLRT-quality information has not been calibrated to frequency uncertainty; seconds/frames are not given extra superlinear weights. Longer tracks contribute additional blocks through the likelihood, avoiding a second multiplication by their frame count.
- Orbit-space historical equivalent timing is still an approximation to Doppler-time uncertainty. Scan-clock and orbit-time corrections may be confounded.
- Unexplained-track assumptions and broad CFO prior need sensitivity/calibration. Strong likelihoods can still dominate historical timing priors. Posterior null probability is a model diagnostic, not a verified bad-association probability.
- Original geographic winners and masks have been reused and these cases were selected retrospectively. No fresh independent validation or localization-error improvement can be inferred.

Four component tests cover integrated-offset normalization against a multivariate Gaussian, partition isolation in block averaging, sampler agreement with an exactly soluble toy posterior, evaluation-value isolation, and shared-timing behavior.
