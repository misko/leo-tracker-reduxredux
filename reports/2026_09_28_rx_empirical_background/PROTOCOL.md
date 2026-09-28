# Calibration-only empirical observational reference

This prerequisite addresses observed excess zeros, count dispersion and paired-receiver dependence before another receiver-geometry fit. It does not label mixed observations as clutter or target absence. It uses only the original pilot's six calibration recordings and their reception windows. Confirmation, evaluation, and calibration-held observations cannot enter fitting, model selection or diagnostics.

## Frozen candidate models

All modes operate on paired candidate sets, retaining empty observations. Convert each canonical RX0-coordinate frequency to phase modulo the lane alias period. Candidate marks remain ancillary. Let n0,n1 denote receiver candidate counts. A normalized phase-space set density is P(n0,n1) n0! n1! times the product of individual phase densities. Include the common Hz Jacobian, -(n0+n1) log(period), when comparing full scores. This equals the prior Poisson set-density convention for independent Poisson counts and uniform phases.

Compare these five fixed modes, in order of tie preference:

1. `poisson`: independent RX Poisson counts with means (sum counts + 1)/(number windows + 1); uniform phase densities.
2. `joint`: empirical joint RX count distribution, smoothed by 32 pseudowindows from independent geometric counts with the same fitted means. This gives strictly positive support to all nonnegative integer counts.
3. `joint_frequency`: joint counts plus separately fitted RX phase histograms with 16 equal bins and one pseudocandidate per bin.
4. `rate_joint`: per-sample-rate joint counts, shrunk with 128 pseudowindows to the pooled joint model. Unseen rates use the pooled model; uniform phases.
5. `rate_joint_frequency`: per-rate joint counts and per-rate RX frequency histograms, the latter shrunk with 128 pseudocandidates to the pooled frequency model. Unseen rates use the pooled distributions.

Constants and bins are fixed before execution. There is no parameter/grid expansion after results. Frequency densities are independent draws conditional on RX and optional rate; candidates within a window may violate that model. Joint counts allow cross-RX dependence without claiming emitter pairing. Rate stratification is a limited observed-covariate treatment, not a fitted recording identity or future-lane parameter.

## Selection and diagnostics

Leave one entire calibration recording out in each of six folds. Fit each candidate mode on the other five recordings' reception windows. Score every reception window of the omitted recording once. Aggregate by equal-record mean nats/window. Select the highest mean, with exact ties preferring the earlier mode; persist all fold scores and count/frequency decomposition. Refit the selected mode on all six calibration reception recordings only and save its complete JSON parameters for subsequent experiments.

This selection score is development evidence, not independent final validation. Report per-record signs versus the recalibrated Poisson reference; gains confined to particular recordings or frequency terms must be visible. No significance claim based on independent windows is permitted. A selected empirical reference can contain real signals and absorb useful candidate structure. It is an unconditional observational comparator, not a learned physical target-free process. Its use in a signal-plus-background model requires a normalized generative construction and separate calibration, not replacing one term in the old Poisson likelihood.

## Execution and verification

Before the real run, test normalization including the infinite count tail, exact Poisson set-density identity, finite empty/large-count scores, phase periodicity, rate fallback, input extraction isolation and count/frequency additivity. Freeze sources, tests, protocol and pilot dataset hashes. Use one thread, nice19, maximum 120 seconds and 4 GiB. No RF, raw IQ or QNAP writes. Preserve results and failed attempts; do not inspect evaluation outcomes to choose this model.
