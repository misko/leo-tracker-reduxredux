# Robust joint likelihood follow-up

Status: design frozen before fitting robust calibration parameters or running robust geographic searches. The original Gaussian experiment remains unchanged and must be reported in full. Its first two geographic results have already been inspected; all four original holdouts are now development data for this follow-up, not fresh confirmatory holdouts.

## Question and success criterion

Does adding measured receiver reception evidence reduce distance error against the same robust Doppler-only baseline, independently from Sacramento and Reno? A lower likelihood loss, smaller nominal grid spacing, or improvement over the failed Gaussian prototype is not sufficient. Report deployed estimates separately, since their association, timing, and search settings differ.

Actual generalization requires a later, disjoint set of existing roof recordings selected by metadata and analysis readiness before looking at their geographic results. No new RF collection. Operator-supplied roof coordinates and provisional orientation support a diagnostic distance comparison, not a claim of surveyed positioning precision.

## Frequency model

Use a fully normalized Student-t frequency density, with scale in Hz and degrees of freedom fixed from the original six calibration scans only. No RMS cap, test-location tuning, or artificial geometry multiplier. Fit constant CFO and rank satellite identities exclusively from Doppler-training observations. Use the full causal eligible catalogue at each searched point independently within each geographic prior. Initial calibration association parameters are scale 100 Hz and df 4; these are an initialization, not a measured uncertainty.

Fit scale/df on reserved calibration residuals with scan-level validation; retain normalized density constants. Report sensitivity to candidate selection and boundary solutions instead of presenting the scale as a calibrated orbit uncertainty. This is a frequency-residual likelihood; it does not yet implement historical-TLE timing priors. Keep timing at zero for this isolated receiver-geometry experiment.

## Shared identity and joint reception evidence

For candidate k with Doppler-training probability w_k, and a track with N reserved observations:

    D = -logsumexp_k(log(w_k) + sum_i log p(f_i | k, location)) / N
    J = -logsumexp_k(log(w_k) + sum_i [log p(f_i | k, location)
            + log p(counterpart_i | k, location)
            + matched_i * log p(log_margin_ratio_i | k, location)]) / N

Satellite identity is shared across a track; it is not redrawn per observation. Evaluate reception predictions at each candidate's direction, not the nonlinear model at an averaged direction. Keep detection and conditional-ratio model coefficients frozen from the six calibration scans. Counterpart and ratio evidence must not select the Doppler-training shortlist. Marginalizing identities with reserved joint evidence is part of evaluating a location, not a new training fit.

Use the same occupied-second track weights for D and J. Nondetections contribute zero ratio loss. The original endpoint set contains reciprocal pair duplicates; the initial comparison is explicitly a composite likelihood. Report this dependence and add a deduplicated-pair sensitivity before any general claim. The frequency observations are not thereby independent either.

## Search and controls

Keep independent Sacramento/Reno priors and identical per-arm settings. Never seed from reference coordinates, production estimates, another prior's fitted candidates, or previous test winners. Full-catalogue orbital propagation reuse is allowed; fitted candidates are not shared. Preserve search traces and stop status. Compare D, D+detection, J, and reversed-direction controls on the same-prior common coordinate inventory. Insufficient search coverage remains a limitation even when a winner improves.

## Required tests and provenance

- Student-t logdensity agrees with a standard implementation and approaches the Gaussian density for large df.
- Training-only CFO and shortlist are invariant to changes in reserved measurements.
- Shared-identity evidence agrees with explicit enumeration and differs from pointwise mixtures in a switching-candidate fixture.
- Geometry is candidate-specific and zero geometry terms recover D exactly.
- Calibration refuses holdout sessions; source cache digests and calibration membership are recorded.
- No running Gaussian source files are modified; robust artifacts have separate names and code hashes.

Geographic outcomes can falsify an improvement hypothesis. Do not increase reception weights or choose recordings using their distance errors to manufacture a successful result.
