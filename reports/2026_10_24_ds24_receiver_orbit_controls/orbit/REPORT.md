# DS24 causal phase/orbit prior control: not qualified

The one predeclared correlation candidate failed the grouped forecast qualification. No position adapter was produced, no geographic fit or RF observation was used to select a prior, and the current prior is retained. This negative result concerns historical TLE forecasting; it says nothing about whether an alternative would improve GPS error.

The attainable phase constraint is also tiny: learned correlations imply only 0.16% median phase-SD reduction even if all three shape coordinates were known, under a nominal unit-Gamma Gaussian-curvature calculation. Meanwhile the training-only baseline’s phase-proxy central-95% coverage is 88.59% under satellite holdout and 87.37% under time-block holdout. Shape-proxy Gaussian central-95% coverage is only about 70–74%. These historical-TLE proxies are not true-orbit error samples, and the results do not justify tightening a phase/orbit prior. The mixed Student/Gaussian marginal-law limitation is stated below.

## Inputs and coordinate check

The 24 frozen DS24 causal-history files contain 68,686 unique TLE-byte triples across 10,764 satellites. Seed 2026102501 selected 1,024 whole satellites before projection; these yielded 6,476 valid triples and no rejections. Identical triples shared across scans were counted once, not as independent evidence. All version epoch and collected timestamps were checked against their source scan cutoff, and each proxy window ends before that cutoff. No post-scan TLE, IQ, RF assignment, or geographic truth was used.

The older DS23 joint-prior helper uses a single-time TEME/element approximation. This control instead reconstructs the current engine’s phase coordinate with Earth rotation and its reference-aligned mean-motion, inclination and RAAN directions over 0/150/300 seconds. It projects newer historical TLE state differences into those physical coordinates, with the existing causal previous-TLE disagreement scales and the fixed 150 s velocity weighting. This is an adapter for the forecast diagnostic, not a new orbit engine.

Every projection has rank four. Median unexplained state-energy fraction is 9.87714e-05; p90 is 0.00331052. The absolute difference from the legacy scalar phase proxy is median 0.0115 s, p90 0.0532 s. A separate 12-satellite check against the existing engine’s causal TLE bank gives maximum relative column discrepancy 0.0063872; the diagnostic uses direct SGP4 while the engine interpolates one-second state samples. The low projection remainder supports a representation check, not proof that the four-dimensional prior describes true orbit error.

## Predeclared candidate and honest validation

The single candidate is R = 0.5 I + 0.5 R̂, where R̂ is robust training-only four-coordinate phase/shape scatter normalized to unit diagonal. There is no GPS-driven scale tightening, alternative shrinkage grid, or choice among outcomes. The current scalar phase distribution and signed location-form selection are refitted from training records only, then reused unchanged in the baseline and candidate. Historical newer TLEs are correlated prediction proxies, not authenticated orbit truth.

The random-group seed is 2026102502: four whole-satellite folds and four randomly assigned contiguous six-hour publication-block folds. Inside either randomized partition, every forecast trains only on earlier publication blocks. All training triples sharing any satellite/TLE endpoint with heldout triples are purged. Satellite folds also exclude every record of the heldout satellites. This is randomized grouped prequential validation; the legacy chronological prefix split is not the new primary validation. Minimum evidence is 300 training rows, 60 training satellites and ten heldout rows. Every active fit passed the independent timestamp, endpoint-disjointness and satellite-disjointness audit.

| Randomized holdout | Heldout rows | Pooled −2 log-density gain | Satellite-cluster 95% interval | Time-block 95% interval |
|---|---:|---:|---:|---:|
| Whole satellite | 5,908 | 10790.6 | [-12.10, 6.84] | [-2.60, 8.56] |
| Publication time block | 5,139 | 4859.3 | [-44.25, 6.99] | [-5.81, 9.92] |

Positive gain favors the candidate. The bootstrap intervals concern the mean group gain, not the pooled sum; groups receive equal weight. The predeclared gate required gain > 6 log N and positive lower bounds under both satellite and publication-block resampling in both holdout schemes. Both schemes fail: pooled improvement is not stable across satellites and publication blocks. No second candidate was introduced after seeing this result.

## Mixed-prior limitation

The existing model uses independent unit-variance Student phase and Gaussian shape priors. A Cholesky correlation transform preserves the nominal unconditional covariance diagonal, but it does not preserve the physical marginal distributions: transformed shape coordinates inherit a Student component. At fixed phase Gamma precision even the conditional shape variances change. Thus the tested likelihood gain combines dependence and tail-law effects; it cannot be advertised as a covariance-only correction with unchanged Gaussian orbit marginals. No automatic prior or adapter promotion is justified. This limitation independently prevents treating the candidate as a drop-in calibration fix.

## Calibration and bounded outcome

- satellite: baseline phase proxy central-95% coverage is 88.59%; median absolute standardized phase error is 0.443. The candidate leaves the scalar phase marginal forecast exactly unchanged. These are historical-TLE proxy diagnostics, not true-orbit coverage.
- time_block: baseline phase proxy central-95% coverage is 87.37%; median absolute standardized phase error is 0.451. The candidate leaves the scalar phase marginal forecast exactly unchanged. These are historical-TLE proxy diagnostics, not true-orbit coverage.

The learned phase/shape dependence is also too weak to approximate the phase-known position-information oracle. Across whole-satellite training folds, median phase correlations with mean motion, inclination and RAAN are 0.0538, 0.0039, and -0.0050. A nominal unit-Gamma Gaussian-curvature calculation gives phase-SD factor 0.99840 if all three shape coordinates were known, only 0.16% median reduction. This is a Gaussian curvature analogy, not the exact Student conditional distribution or a position-accuracy forecast.

Projection took 2.55 s and grouped validation took 3.74 s with BLAS limited to one thread. Three component-owned tests pass. No RF collection, IQ processing, position fit, satellite reassignment, point deletion, or golden-fixture change occurred.

A feasible future change would need independent evidence that distinguishes physical dependence from shape-tail misspecification, then randomized grouped causal validation. The present results do not justify a narrower phase prior or a better-localization claim. The earlier phase-known information oracle remains an unavailable-information sensitivity, not a usable method.

Artifacts: protocol.json and groups.json preserve the predeclared design; inventory.json records input hashes and sampled satellites; projected_rows.json and validation.json retain every diagnostic row/fold; basis_audit.json and audit.json record numerical and leakage checks; model_law_clarification.json states the prior-law limitation; eligibility.json explicitly rejects position fitting. orbit_forecast_validation.png is the scientific summary figure.
