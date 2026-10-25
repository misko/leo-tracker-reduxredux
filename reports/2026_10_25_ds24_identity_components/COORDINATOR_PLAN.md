# Fast-scan identity and generating-component tests

The preceding review is progress: it published new all-24 residual-gate evidence,
identified a weak 57743/66259 competition on 0012, and established conditional
cross-owner consistency for 189 RX1 points on 0013. It did not validate new
identities or improve operational outputs. The broad fast-scan improvement
goal remains active.

This wave follows the review at remote commit
`34acb8be6c93f7fff9fcf36b78e72d9721f59fea`. Three existing SOL xhigh agents own
identity implementation, synthetic implementation, and independent design/input
checks. The root integrates findings and publishes the iteration.

## Identity branch

Keep all four chronological nominees 0010/0011/0012/0013, including previously
worsening examples. Use the original causal catalogue to propose a bounded
common candidate pool, preserving the known 0012 alternative. Candidate and
alias treatment must be symmetric, including a symmetric calibration cavity
if a shortlisted satellite was already active. Compare fixed RF-derived parent
states, not GPS-selected positions. No new localization fits are planned.

Candidate and unresolved-curve densities must use the same observation measure.
In particular, do not compare an alias-averaged finite mixture against an
alias-image sum on a wrapped observation domain. Check image truncation,
alias/ordering invariance and numerical phase integration before scientific
comparison. A broad normalized unknown-curve model is not automatically an
empirically calibrated clutter distribution or an identity acceptance rule.

Whole-owner prediction on 0013 must exclude the held owner from candidate
nomination and parameter estimation. All four current owners are RX1, so
receiver-common discrepancy remains a competing explanation. Preserve native-ID
nonoverlap and shared covariance; overlapping folds are not independent votes.
The implementation design uses saved baseline states only, at most 112 exact
candidate contexts plus null checks, and a common finite translated-Gaussian
alias mixture on the real graph-vector domain for both physical and unresolved
models. This is not a claim of a complete wrapped-quotient density or calibrated
clutter law. Null and satellite scores should share the parent radio-conditioned
base mean/covariance, replacing only the target curve prior. The branch protocol
specifies the exact pool and alias convergence checks, with two one-BLAS-thread workers and a
600-second scientific cap. No thresholds are selected from output geography.

## Synthetic branch

Reuse the eight noisy fast-scan realizations: two original geometries, two
artificial sites, two existing seeds. First reproduce their saved observation
hashes. Change generating truth in exactly two ways: remove orbital timing/shape
deviations, or remove receiver hardware/smooth deviations. Keep all other latent
draws, Gaussian measurement noise, Gamma precision, source constants and input
ownership fixed. Re-evaluate geometry at the declared generating phase. Retain
the original inference priors, masks, powers, labels, regional start and budget.

This is 32 new fits including matched c=0/fitted-c controls, using two workers,
one BLAS thread each, 180 seconds per fit and a 600-second shared scientific cap.
No retries or additional seeds after observing failures. It is a conditional
generating-component intervention, not a true-nuisance inference oracle, a
selection benchmark or a calibrated precision floor. Preserve all gate failures
and frequency-score effects separately from artificial-position error.

## Independent review and validation availability

Protocols and construction checks are reviewed before scoring/fitting. The
independent agent also checks a bounded metadata exposure ledger, especially
the ten previously unavailable DS24 scans. Missing membership in the 24-case
cohort is insufficient evidence of untouched validation data. No new IQ
processing or RF collection belongs to this availability audit.

No production changes, post-scan TLE inference, real-GPS selection, assumed
stationary pooling, or new RF. Root tracked changes are preserved. Every outcome
is reported; an unqualified result does not replace a saved baseline. Publication
should contain new code, observations/results and figures with exact dependency
references, without duplicating large older input/runtime archives.
