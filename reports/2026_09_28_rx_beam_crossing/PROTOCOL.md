# Conditional temporal receiver-geometry pilot

Frozen before fitting on 2026-09-28. The adjacent `launch.json` binds executable and input hashes immediately before the single attempt.

## Question and scope

Does candidate-specific change in nominal receiver contrast add reception evidence beyond contrast at each timestamp, after accounting for correlated noise? This is a conditional paired log-margin-ratio experiment on ten reused roof recordings from the earlier DS6 work. It is not a full DS7 evaluation, position fit, calibrated beam measurement, or test of target first/last detection order.

The provisional software mapping is RX0 west and RX1 east, with nominal opposing 10-degree tilts. Candidate contrast is `(b1-b0) dot LOS`; its derivative uses actual observation intervals. A contrast-zero event is a predicted nominal equal-boresight event, not an observed beam crossing. Free gain offsets prevent equating it with equal measured margins.

## Inputs and partitions

Use only the audited compact inputs in `input-audit/CONDITIONAL-INPUT-CONTRACT.json`. No IQ, RF collection, regenerated positions, or QNAP writes. Deduplicate matched physical pairs by physical_pair_key, preferring RX0 then lexical anchor_key: 6,285 anchor rows become 6,043 distinct pairs. Retain tracks with at least three distinct epochs; disclose exclusions. All arms use identical support. Rank beyond intercept, time and static contrast is a diagnostic, not an outcome-selected subset.

Sort recording IDs by SHA256(`20260928:` + ID), first six coefficient-training and last four evaluation. Keep all rows, receivers, and tracks of each recording together. Evaluation recordings are `3ebf3526172258af`, `aa9770c66396e928`, `9d7b6a0db558703a`, `898b709fcf3dd978` (all prefixed `scan-fw-`). No outcome-dependent repartitioning.

Candidate identities and probabilities come from existing Doppler-training rows. Marginalize a single shared candidate over each whole track; never independently select a candidate per epoch. Scale geometry features using coefficient-training recordings only.

The original CFO pairing bias used two recordings now assigned to evaluation. Existing detection-gated tracks, source links, reference-conditioned candidate geometry, and previous research also predate this split. Therefore all results are **conditional reused-preprocessing feasibility**, not blind or untouched validation.

## Fixed comparison

Fit five arms: geometry-free IID, static rowwise geometry IID, geometry-free continuous-time OU, static rowwise geometry OU, and temporal geometry OU. OU models use actual time gaps and stationary sequence starts. The temporal arm adds only the contrast derivative to the static OU mean. This matched comparison separates directional motion from noise correlation. Candidate-specific static models are new comparators; the legacy posterior-mean rowwise model is not numerically reproduced here.

Before these fits, estimate one shared nuisance offset using only coefficient-training recordings: intercept, channel/edge/sample-rate categories and centered log anchor margin, with ridge 1 on non-intercept terms. Freeze these offsets for every arm. Audit evaluation category support. This is a residual comparison after a shared linear adjustment, not a joint nuisance/geometry optimum or exact reproduction of the old reception model. Unknown evaluation categories disqualify progression. Because rank-deficient tracks remain in the common descriptive cohort, no track-specific temporal-direction evidence or formal temporal promotion is authorized by this pilot.

Use normalized joint sequence likelihoods, not a product of level and difference densities. Sum track negative log marginal densities plus fixed ridge 1 on scaled geometry coefficients. The geometry level coefficient is nonnegative under the nominal mapping; a zero optimum is an absent geometry signal, not evidence of calibrated orientation. The derivative coefficient is signed. Parameter bounds, three deterministic starts, optimizer limits, and code are bound in launch.json. No tuning grid or refitting after observing evaluation results.

Score frozen fits on entire evaluation tracks. This is joint density evaluation, not future forecasting. Primary comparison: temporal OU minus static OU log predictive density, aggregated and per recording, with identical row counts. Report all five arms and convergence/boundary diagnostics. Do not treat epochs as independent replicates or manufacture confidence intervals from four recordings.

Negative controls use frozen coefficients on evaluation recordings only: swap geometry while holding measured ratios fixed; shuffle measured ratios within track; reverse candidate contrast trajectories and recompute derivatives on actual timestamps. Time shuffle also destroys noise correlation, so failure on that control alone does not demonstrate direction specificity.

## Decision and resource bounds

Exploratory reception progression requires temporal OU to improve aggregate density and at least three of four recordings relative to static OU, plus beat each of its frozen controls in aggregate. Require converged relevant fits and report active bounds, distinguishing a zero geometry coefficient from numerical scale/correlation boundaries. These conditions cannot authorize a satellite-confidence or localization claim: held-frequency evidence is absent from these compact inputs.

One attempt, one CPU/BLAS thread, nice 19, 4 GiB address-space ceiling, 300-second wall deadline. Preserve partial outputs and failures. No automatic retry, deadline extension, or expanded search following a weak result. Synthetic component checks and read-only input preflight precede fitting. Publish actual child resource usage and source hashes with results.
