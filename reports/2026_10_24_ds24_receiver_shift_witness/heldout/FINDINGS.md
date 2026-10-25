# Whole-family position-sensitive holdout

Under this conditional score, held-family CFO prediction supports the RF50 movement in 0017 in aggregate and favors the baseline position in 0095. Within the RF50 predictor, the fitted-c movement gains are **+16.724** and **−5.807** respectively; the baseline predictor gives **+5.636** and **−11.031**. The aggregate signs persist in c=0 and at both predeclared noise sensitivities. Individual folds disagree, and these two previously selected cases cannot establish a transferable selection rule.

The headline is held CFO support for moving from the baseline train-only endpoint to the RF-scaled shared-RX1 train-only endpoint, under the same predictor. Positive values favor the movement. These are conditional Gaussian **moment** predictive scores using native per-ID sigma ×√2, not exact original Student/Gamma densities or geographic accuracy.

| Scan | c arm | Predictor | Fold1 | Fold2 | Fold3 | Sum | Positive folds |
|---|---|---|---:|---:|---:|---:|---:|
| DS24-0017 | c0 | baseline | 5.406 | -11.834 | 11.462 | 5.035 | 2/3 |
| DS24-0017 | c0 | sharedRF50 | 10.163 | -7.664 | 13.130 | 15.629 | 2/3 |
| DS24-0017 | fitted_c | baseline | 6.084 | -10.640 | 10.191 | 5.636 | 2/3 |
| DS24-0017 | fitted_c | sharedRF50 | 11.103 | -6.142 | 11.763 | 16.724 | 2/3 |
| DS24-0095 | c0 | baseline | 1.911 | -9.900 | -4.552 | -12.541 | 1/3 |
| DS24-0095 | c0 | sharedRF50 | 1.944 | -8.518 | -0.052 | -6.625 | 1/3 |
| DS24-0095 | fitted_c | baseline | 1.609 | -10.205 | -2.435 | -11.031 | 1/3 |
| DS24-0095 | fitted_c | sharedRF50 | 1.576 | -8.716 | 1.333 | -5.807 | 2/3 |

![Movement support](movement_support.png)

The three folds are one seeded random disjoint whole-family partition, not three independent experiments. Each held vector jointly includes all its original active curved and predictive factors across both receivers and all channels. The sums combine fold-wise conditional validation scores; training sets overlap. Nonadditive family marginal diagnostics are saved separately inside each result and never substituted for the joint score.

| Scan | c arm | Predictor | Native sigma ×1 | Native sigma ×√2 | Native sigma ×2 |
|---|---|---|---:|---:|---:|
| DS24-0017 | c0 | baseline | 5.051 | 5.035 | 5.113 |
| DS24-0017 | c0 | sharedRF50 | 20.792 | 15.629 | 11.567 |
| DS24-0017 | fitted_c | baseline | 5.394 | 5.636 | 5.829 |
| DS24-0017 | fitted_c | sharedRF50 | 21.882 | 16.724 | 12.572 |
| DS24-0095 | c0 | baseline | -15.099 | -12.541 | -10.613 |
| DS24-0095 | c0 | sharedRF50 | -7.222 | -6.625 | -6.200 |
| DS24-0095 | fitted_c | baseline | -14.014 | -11.031 | -8.871 |
| DS24-0095 | fitted_c | sharedRF50 | -6.932 | -5.807 | -5.098 |

The complete [movement table](movement_support.csv) separates quadratic from log-determinant gains. Both terms are retained. The [train endpoints](train_endpoints.csv) contain only fitted regional east/north coordinates; this report has no geographic reference.

![Own-model prediction](own_model_prediction.png)

The separate [own-model table](own_model_prediction.csv) compares baseline prediction at its baseline endpoint with RF50 prediction at its RF50 endpoint. This combines added covariance, changed receiver mean and changed location; it cannot by itself establish support for the movement.

Own-model fitted-c gains are much larger: +267.279 for 0017 and +135.298 for 0095. Thus both scans benefit from the receiver model in this conditional predictive metric, while the same-predictor crossover distinguishes their location movement. Raw held prior-mean RMS values retain the unknown target phase and fragment offsets and are not estimates of measurement noise. The score integrates their covariance rather than fitting target nuisance values.

## Construction and leakage controls

Frozen cases are DS24-0017 and DS24-0095, selected previously for opposing geographic effects. No geographic reference enters these new fits, scores, fold assignments, model choices or thresholds. Seed 2026102503 plus numeric case suffix defines three reproducible whole-family folds. Original observations, IDs, satellite labels, aliases, powers, causal prior means/scales and 25×25 km bounds are retained. Each fold removes every held curved factor through the point mask and every held predictive entry from the training problem. All frozen graph rows and physical-mode support stay present for stable coordinate support, an explicit inherited-graph condition.

Both models and both c arms start at the regional center and use five phase-refresh rounds with at most 48 position steps per round. Held phases remain at their causal prior means in every training and scoring round. The crossover recalculates training-only nuisance posteriors with five fixed-position phase refreshes at both endpoints; it adds no position optimization. Predictive training factors influence position, while their values never update curved calibration, phase coefficients or Gamma precision.

At each held endpoint, the mean uses the curved-training nuisance posterior. The covariance carries its full joint coefficient covariance, conditional on training variational Gamma precisions and original generalized-likelihood powers. All held-local training feature columns must be exactly zero. Held phase mean stays causal and its standardized variance is explicitly reset to 1, rather than the unused mean-field Student precision. Held orbit coefficients retain Gaussian prior variance 1. Each original held curved fragment retains a 300 Hz Gaussian constant, and every held predictive fragment gets its own 300 Hz Gaussian constant. Full shared covariance couples all target points and families.

Native frozen per-ID sigmas are used unchanged, multiplied by√2 to match E[1/tau]=2 for an unseen Gamma(2,2) noise precision. Sensitivities ×1 and ×2 were frozen before fitting. No target nuisance or Gamma precision is estimated from target CFO. However, native sigmas, graph membership, labels, aliases, masks, powers and mode support were previously selected or estimated with full RF data. The evaluation is conditional on these inherited inputs and is not a fully external holdout.

The held Student phase and Gamma noise tails are approximated by Gaussian covariance moments; the training nuisance covariance is conditional on variational precisions. Linear orbital/phase geometry uses the causal held phase mean and does not integrate nonlinear phase curvature. Fitted train-only position is a plug-in point: its uncertainty and search selection are not integrated. These limitations preclude interpreting the score as exact model evidence, an identity proof, a geographic accuracy estimate or a promotion rule.

## Verification and reproducibility

Completed 24/24 position fits and 48/48 joint crossover vectors; longest case/fold 28.79 s under the 240 s cap. Maximum training final log-precision change 1e-05; maximum final fixed-position phase-reference change 0.0003959 s. Work used at most two processes with one BLAS/OMP/MKL thread each.

**One original phase convergence criterion fails and is retained:** DS24-0095, fold 3 (zero-based fold 2), fitted-c baseline has final train-fit phase-reference change 0.0150179 s, above the original 0.01 s limit. All fixed-position crossover phase refreshes finish below 0.01 s. No extra fitting rounds or tuned rescue were added. These are raw diagnostic fits; original residual adoption gates were not used to select folds or emit an accepted policy.

A labeled [convergence sensitivity](convergence_sensitivity.csv) excludes that entire 0095 fold consistently for both predictors, both c arms and all three noise scales. At the primary scale, the remaining c=0 gains are −7.989 (baseline predictor) and −6.573 (RF50 predictor); fitted-c gains are −8.596 and −7.140. All sensitivity aggregate signs remain negative. This exclusion is not the primary result and supplies no replacement fit.

Five focused component tests check dense joint Gaussian agreement, the effect of shared covariance, retention of position-sensitive shapes, fold factor removal, and held-CFO redaction. The redaction test perturbs all held curved/predictive values by 12,345 Hz with frozen graph/noise, verifies identical training objective/coefficients/precisions/residuals at a point, and verifies one identical 8-step bounded optimization trajectory for DS24-0017/fold 0/sharedRF50/fitted-c. This test is not claimed to replay all 24 fits.

The [protocol](protocol.json), [input manifest](input_manifest.json), raw results and NPZ arrays bind exact IDs, immutable scales and source dependencies. Run freeze.py only before a new explicitly versioned batch; the production runner refuses to overwrite existing evidence and verifies input, protocol and source seals at start/end. No RF collection, QNAP write, golden fixture update or runtime production change was made.

Reproduction: use .venv/bin/python -B; PYTHONPATH=/tmp/algo03-feasible-deps:src:tools:/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/evaluation:/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/receiver; set OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1. Run heldout.py --case CASE --fold 0 (or 1/2) with at most two simultaneous processes, then report.py. Results are a bounded conditional diagnostic. No threshold was tuned and neither case selects a policy.
