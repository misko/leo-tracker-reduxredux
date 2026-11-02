# Native conditional predictive validation

DS26-0070 SD4 ranks first and SD2 second in each held subset and both c arms (c0: all gain 90.91, other-family gain 72.48, phase closed 2/3, optimizer success 3/3, boundary folds 1/3; fitted_c: all gain 92.30, other-family gain 73.99, phase closed 2/3, optimizer success 3/3, boundary folds 1/3). DS26-0309 SD4 ranks first and SD2 second in each held subset and both c arms (c0: all gain 74.66, other-family gain 38.82, phase closed 3/3, optimizer success 2/3, boundary folds 0/3; fitted_c: all gain 74.06, other-family gain 37.71, phase closed 3/3, optimizer success 2/3, boundary folds 0/3). Solver-only predictive differences are small. These comparisons support a family-influence sensitivity, with convergence and development-selection limits; they do not establish production acceptance.

These scores test the effect of the selected family on native held observations, including other satellite families. The native hardware, receiver, phase, orbit correction and position fits use only training IDs. They are conditional development evidence: full-data nominations, aliases, native masks, RF initialization, point-noise preprocessing and likelihood powers remain inherited. Ancillary linear/family likelihoods are omitted. No GPS was accessed by this runner.

Each scan has three random synchronized 5 s group folds (seed 2026110207), holding 20% of available groups and guarding an adjacent 5 s group on either side. Both c arms and all four model cells share native held IDs. Protocol JSON and SHA256 were written before outcome fits. Eight phase rounds, 25 position iterations and 100 function evaluations per round are the fixed fit budget.

The reported score is −2 times a normalized Gaussian log predictive density, integrating the fitted linear coefficient covariance and a local Laplace approximation for position uncertainty. The fitted Gamma precisions are conditioned upon; their uncertainty is not integrated. Training uses existing likelihood powers; held scores have no likelihood power. A wholly unseen fragment uses its Gamma(2,2) prior inverse-precision expectation. `all`, `target`, and `other` are separate marginal densities, so their scores do not add. Overlapping random folds are correlated: sums rank these declared fits and are not independent-sample evidence or identity probabilities.

| Scan | c arm | Held subset | Rank | Solver | Physical SD | −2 log density sum | Gain vs legacy | Phase closed |
|---|---|---|---:|---|---:|---:|---:|---:|
| DS26-0070 | c0 | all | 1 | damped_half | 4 | 13659.49 | 90.91 | 2/3 |
| DS26-0070 | c0 | all | 2 | damped_half | 2 | 13670.88 | 79.52 | 2/3 |
| DS26-0070 | c0 | all | 3 | legacy | 1 | 13750.40 | 0.00 | 1/3 |
| DS26-0070 | c0 | all | 4 | damped_half | 1 | 13751.44 | -1.05 | 3/3 |
| DS26-0070 | c0 | target | 1 | damped_half | 4 | 2718.82 | 28.80 | 2/3 |
| DS26-0070 | c0 | target | 2 | damped_half | 2 | 2722.43 | 25.19 | 2/3 |
| DS26-0070 | c0 | target | 3 | legacy | 1 | 2747.62 | 0.00 | 1/3 |
| DS26-0070 | c0 | target | 4 | damped_half | 1 | 2749.62 | -2.00 | 3/3 |
| DS26-0070 | c0 | other | 1 | damped_half | 4 | 10941.01 | 72.48 | 2/3 |
| DS26-0070 | c0 | other | 2 | damped_half | 2 | 10951.13 | 62.36 | 2/3 |
| DS26-0070 | c0 | other | 3 | legacy | 1 | 11013.49 | 0.00 | 1/3 |
| DS26-0070 | c0 | other | 4 | damped_half | 1 | 11013.97 | -0.48 | 3/3 |
| DS26-0070 | fitted_c | all | 1 | damped_half | 4 | 13667.64 | 92.30 | 2/3 |
| DS26-0070 | fitted_c | all | 2 | damped_half | 2 | 13679.30 | 80.64 | 2/3 |
| DS26-0070 | fitted_c | all | 3 | legacy | 1 | 13759.94 | 0.00 | 1/3 |
| DS26-0070 | fitted_c | all | 4 | damped_half | 1 | 13760.82 | -0.88 | 3/3 |
| DS26-0070 | fitted_c | target | 1 | damped_half | 4 | 2721.25 | 27.78 | 2/3 |
| DS26-0070 | fitted_c | target | 2 | damped_half | 2 | 2724.86 | 24.18 | 2/3 |
| DS26-0070 | fitted_c | target | 3 | legacy | 1 | 2749.03 | 0.00 | 1/3 |
| DS26-0070 | fitted_c | target | 4 | damped_half | 1 | 2751.61 | -2.57 | 3/3 |
| DS26-0070 | fitted_c | other | 1 | damped_half | 4 | 10948.54 | 73.99 | 2/3 |
| DS26-0070 | fitted_c | other | 2 | damped_half | 2 | 10958.83 | 63.69 | 2/3 |
| DS26-0070 | fitted_c | other | 3 | legacy | 1 | 11022.52 | 0.00 | 1/3 |
| DS26-0070 | fitted_c | other | 4 | damped_half | 1 | 11022.60 | -0.08 | 3/3 |
| DS26-0309 | c0 | all | 1 | damped_half | 4 | 17226.88 | 74.66 | 3/3 |
| DS26-0309 | c0 | all | 2 | damped_half | 2 | 17276.35 | 25.19 | 3/3 |
| DS26-0309 | c0 | all | 3 | damped_half | 1 | 17301.51 | 0.02 | 3/3 |
| DS26-0309 | c0 | all | 4 | legacy | 1 | 17301.54 | 0.00 | 3/3 |
| DS26-0309 | c0 | target | 1 | damped_half | 4 | 3394.09 | 21.32 | 3/3 |
| DS26-0309 | c0 | target | 2 | damped_half | 2 | 3408.49 | 6.92 | 3/3 |
| DS26-0309 | c0 | target | 3 | legacy | 1 | 3415.41 | 0.00 | 3/3 |
| DS26-0309 | c0 | target | 4 | damped_half | 1 | 3415.42 | -0.01 | 3/3 |
| DS26-0309 | c0 | other | 1 | damped_half | 4 | 13845.77 | 38.82 | 3/3 |
| DS26-0309 | c0 | other | 2 | damped_half | 2 | 13871.99 | 12.60 | 3/3 |
| DS26-0309 | c0 | other | 3 | damped_half | 1 | 13884.59 | 0.00 | 3/3 |
| DS26-0309 | c0 | other | 4 | legacy | 1 | 13884.59 | 0.00 | 3/3 |
| DS26-0309 | fitted_c | all | 1 | damped_half | 4 | 17233.67 | 74.06 | 3/3 |
| DS26-0309 | fitted_c | all | 2 | damped_half | 2 | 17282.91 | 24.82 | 3/3 |
| DS26-0309 | fitted_c | all | 3 | damped_half | 1 | 17307.72 | 0.01 | 3/3 |
| DS26-0309 | fitted_c | all | 4 | legacy | 1 | 17307.73 | 0.00 | 3/3 |
| DS26-0309 | fitted_c | target | 1 | damped_half | 4 | 3388.53 | 18.46 | 3/3 |
| DS26-0309 | fitted_c | target | 2 | damped_half | 2 | 3400.99 | 6.00 | 3/3 |
| DS26-0309 | fitted_c | target | 3 | legacy | 1 | 3406.99 | 0.00 | 3/3 |
| DS26-0309 | fitted_c | target | 4 | damped_half | 1 | 3407.00 | -0.01 | 3/3 |
| DS26-0309 | fitted_c | other | 1 | damped_half | 4 | 13854.48 | 37.71 | 3/3 |
| DS26-0309 | fitted_c | other | 2 | damped_half | 2 | 13879.88 | 12.32 | 3/3 |
| DS26-0309 | fitted_c | other | 3 | damped_half | 1 | 13892.19 | 0.00 | 3/3 |
| DS26-0309 | fitted_c | other | 4 | legacy | 1 | 13892.19 | 0.00 | 3/3 |

Positive gain means improved normalized predictive density. A nonclosed phase cell remains an unfinished approximation and cannot establish a preferred physical model. Position curvature clipping or a regional boundary further weakens the Laplace approximation. Held RMS is diagnostic only; it does not choose the model. Noise is diagonal conditional on the shared latent modes; group withholding does not itself calibrate residual correlations within each held group.

Files: `scores.csv` contains per-fold/per-family scores, `ranked_summary.csv` contains declared model ranks, each job JSON retains RF fit/convergence diagnostics and matched-ID hashes, and each scan protocol lists all native train/held IDs. `evaluate_context` in `predictive.py` accepts a remapped context and these same IDs for root-owned identity-mixture validation.

Validation: component tests compare normalized low-rank density against a dense covariance calculation and verify deterministic synchronized splits and exact group guards. No production files, published ownership or golden fixtures were changed.
