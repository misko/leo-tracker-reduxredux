# Experiment protocol

## Inputs, time, geometry, and TLE provenance

Use native GLRT observations with their actual integration support, UTC times, CFO units/sign, RF carrier, receiver, band/channel, scores, uncertainty, and observation identity. Keep alternative peaks tied to the same acquisition opportunity; they are competing measurements, not additional independent evidence. Verify downconversion sideband, wavelength scaling, frequency reference, alias period, time origin, and orbit coordinate frames before adding nuisance freedom.

Record the scan-start causal cutoff unless the deployed algorithm explicitly uses a different as-of policy. For each satellite, select the latest eligible element set actually available by that cutoff. Record element epoch **and** archive collection/availability time. An epoch before the scan does not by itself prove causal availability. Label unverifiable provenance `causality-unverified`.

For the retrospective bank, default to the first valid archived element set with epoch after scan end; record when it was collected, its distance from observation, and any propagation validity limitations. Fix the allowed look-ahead horizon before seeing fit scores. If only later-collected, pre-scan-epoch elements exist, label them separately. A later snapshot containing unchanged causal elements is not new orbit evidence. Never select the TLE epoch that minimizes this track's residual without explicitly accounting for that additional search.

Perform both comparisons when possible:

- **Paired TLE comparison:** same satellite IDs and observations with both banks available, same position, radio model, priors, starts, and budgets; first freeze nuisance parameters, then refit them under the same policy. Report both effects.
- **Catalogue discovery:** search each bank's complete eligible universe, including newly present IDs. Report catalogue additions/missing IDs separately from improvement in the orbit of an existing candidate.

Eligibility may use instrument band and physical visibility. Model uncertain receiver pointing/beam width as uncertainty; do not reject candidates using an invented hard field of view. Record horizon, sky angle, and known antenna geometry. Never restrict the search to the desired identity, a known-site answer, or just the current assigned families.

## Polynomial and track-construction audit

Center and scale time; compare degree 0 (constant control), 1, 2, 3, and 4 where sample count and conditioning permit. The existing robust-order helper supports degrees 1–4 only: identify that limitation rather than claiming it fits the constant control. Use a declared noise/clutter model and complexity penalty. Include join/change-point and alias-search complexity when comparing piecewise models.

Fit native points, not densely sampled polynomial predictions. Start on the saved alias branch; examine physically permitted alternative integer branches consistently across contiguous pieces. No independent alias integer per point merely to reduce residuals. Retain branch decisions and their uncertainty.

For every polynomial and orbit model, report full-point and retained-point RMS, robust scale, residual mean, slope, remaining curvature, change-point statistic, lag/time-lag correlation, block means, sample count, time span, and exclusions. Preserve the deployed gate definitions and units for exact replay. Report their numerical margins as well as pass/fail. Account for irregular cadence and measurement correlation in any new statistical interpretation; legacy gate z-scores are not automatically calibrated significance levels.

Check endpoint leave-one-out sensitivity, leverage, effective degrees of freedom, and uncertainty in derivatives. Active curvature means the data support departure from an affine curve; polynomial order alone is insufficient. A near-zero in-sample mean or slope after explicitly fitting those terms is automatic and does not validate identity. Test remaining structure and predictions on independent evidence.

Inspect every original graph piece and join. For long sources, render consecutive 20-second windows with common frequency conventions and boundary context. Compare individual pieces and the joined model with appropriate complexity accounting. Record all native points, including rejected endpoints; do not tune truncation to satisfy a satellite gate.

## Shared nuisance ladder

Use an observation model of the form

`observed_CFO + integer_alias * alias_period = orbit_CFO(satellite, RF, time, position, orbital_correction) + receiver_band_offset + receiver_band_drift * (time - t0) + satellite_frequency_term + residual`.

This is a scope diagram, not an instruction to fit every term simultaneously. Reproduce the pipeline's physical carrier/downconversion model and signs. Center time at a recorded reference. Pin a reference offset or impose an explicit gauge; do not jointly fit redundant receiver and satellite constants without an identifiability constraint. Model multiple carrier hypotheses explicitly if needed.

| Level | Newly available freedom | Scope and evidence requirement |
| --- | --- | --- |
| L0: replay | None beyond saved baseline settings | Frozen position, existing radio calibration, saved phase, and explicit alias hypotheses. For previously unseen satellites use the declared baseline phase prior/search, not an invented saved phase. |
| L1: constants | Receiver/band constant corrections | Shared across relevant tracks with physical priors and a pinned gauge. A free per-track intercept is only a diagnostic lower bound. |
| L2: small drift | Linear frequency drift | Shared per receiver; compare justified band-specific deviations with shrinkage. Use cross-family support. Do not let every track acquire its own slope. |
| L3: satellite phase | One timing/phase correction per satellite | Shared across its receivers/channels/tracks, bounded by the declared prior. Distinguish satellite phase from global timestamp error. |
| L4: additional satellite correction | A small identifiable orbital perturbation **or** a shared satellite frequency-rate term | Separate alternatives, with physical priors and independent family support where possible. Report degeneracy with position, receiver drift, and phase. A free frequency rate is a discrepancy model, not proof of TLE error. |

Retain all baseline freedoms at every level. If the pipeline already fits phase, keep it enabled in L0–L2 and describe L3 as a prior-sensitivity experiment, not a nested extra parameter. Save an exact parameter inventory for every cell: fixed/free, scope, units, prior, bound, fitted value, uncertainty, and effective dimension. Compare candidates within identical model cells; penalize new freedom when choosing between cells.

For L4, inspect physical orbit sensitivities before choosing parameters. Candidate possibilities include an along-track/time correction or a small mean-motion correction. Avoid fitting phase and a duplicate along-track parameter simultaneously. Use Jacobian singular values, posterior correlations, and bound/prior pulls to identify unsupported parameters. Over a short scan, several orbital elements may be indistinguishable; do not fit all six and claim an orbit solution.

Keep two additional diagnostic controls outside the acceptance ladder:

- Unpenalized per-track offset/affine residual minima: how much mismatch could arbitrary calibration absorb?
- The selected polynomial/clutter model: the achievable empirical curve fit without a satellite identity.

If a satellite wins only with these controls, retain ambiguity. A receiver frequency step is a separate hypothesis requiring contemporaneous evidence from independent satellite families on that receiver/band. Its time and amplitude are shared; count the change-point search and test the rest of the scan.

Use curved evidence and overdetermined, independently linked families to calibrate offsets and drifts. Linear tracks can be associated after calibration, but freely aligning two lines cannot establish that calibration or identity. Multiple linear fragments help only when common hardware parameters and independent timing/family constraints make the system identifiable; show rank and predictive stability.

## Fair ranking, search, and confidence

Keep all candidate comparisons on the same original observations, noise/covariance model, opportunity inventory, and fitting budget. Use likelihood normalization and a declared complexity treatment (proper marginal likelihood, predictive score, or an appropriate information criterion). Account for correlated observations and searched discrete hypotheses; do not apply a raw-point BIC as if all points were independent. Do not compare arbitrary scores from different normalizations or call lower RMS better evidence.

Search feasible alias/phase basins and position starts under a recorded bound. Retain search failures and candidates rejected at each stage. A coarse screen may prune only with a justified criterion; report whether all eligible candidates received exact fitting or only a shortlist. Include the best rejected candidate and at least the best runner-up; render up to five competitive finalists when available. Keep clutter/no-match and a radio-curve alternative in view. Near-identical catalogue entries may support an orbit family without resolving a NORAD identity.

Use the saved inferred position first, then test stability within the declared regional prior (normally the configured 25 × 25 km box). Never center that prior on evaluation truth. If requested, a fixed known-site fit can diagnose orbit/radio mismatch, but label it `oracle-position diagnostic`; its ranking is not blind localization evidence. Separate fixed-association position profiling from full reassociation at each start.

Prefer independent receiver/channel/family fragments to test the correction. Where predictive splits are needed, randomize **whole time groups**, not individual adjacent samples; keep synchronized observations and competing peaks together, with a declared guard against correlation leakage. Freeze partitions and seeds for every candidate/model and both c arms. Do not silently replace this with a first-half/second-half test. Chronological extrapolation can be an additional labeled test. Report when a short track cannot support meaningful held-group validation. Fit the final diagnostic on all points after model selection, preserving validation results and any reuse of data for selection.

For any RF-dependent coefficient `c`, run controlled `c = 0` and fitted-`c` comparisons with matched observations, candidate sets, other priors, starts, and budgets. Record fit-score gains separately from position accuracy. Do not choose between arms using evaluation-site error.

Base confidence on all of: candidate coverage, competitor margin under matched models, residual adequacy, independent prediction, stability across starts/aliases/priors, identifiable nuisance corrections, and plausible geometry. Report each dimension rather than hiding them in an arbitrary percentage. A later-TLE rescue suggests orbit-model discrepancy but cannot alone distinguish propagation error, a maneuver, timing error, or calibration absorption.

When testing a recovery against the full scan, replay the exact ownership/gate checks for both the target and incumbents. Report lost/reassigned/added native points and per-family changes. A target-only fit must not quietly damage existing associations.
