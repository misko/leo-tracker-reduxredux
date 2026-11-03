# Original full-endpoint identifiability audit

Calibration plus satellite timing can locally imitate99.48–99.78% of the positive spatial-frequency information trace at all five original fitted-c endpoints. This generalizes the local confounding observation beyond one recording. It does not show that their locations are correct, explain global mode ranking or provide a position covariance. No station/reference coordinates or requested-window labels were read in this audit.

The one-worker run completed in89.333s under the180s whole preparation/analysis cap (TERM180/KILL185). It made10 explicit objective evaluations and10 explicit derivative-predictor calls, plus public original-source preparation/audits, with zero fits. All20084 original full rows and the original ordered candidate banks are retained. Original endpoints came from public production replay, not later profile winners or position-selected states.

## Fitted-c retained information

| Source | N / candidates | Signal responsibility mass | After cal+clock % | After cal+clock+timing % | With actual clock/timing priors % | Nuisance rank |
|---|---:|---:|---:|---:|---:|---:|
| S01 | 4797 / 46 | 1586.299 | 43.2907 | 0.5198 | 0.5398 | 69/69 |
| S02 | 3524 / 51 | 1607.873 | 29.2179 | 0.4739 | 0.5068 | 74/74 |
| S03 | 3988 / 40 | 3019.822 | 25.8882 | 0.3338 | 0.3446 | 63/63 |
| S04 | 3719 / 46 | 2318.929 | 27.0110 | 0.3709 | 0.4100 | 69/69 |
| S05 | 4056 / 32 | 2382.305 | 38.3091 | 0.2212 | 0.2468 | 55/55 |

Calibration5 plus the18 clock coordinates alone leaves25.89–43.29% of the raw trace. Most further loss occurs when the independent total-satellite timing columns are added. Exact existing priors restore only a small fraction of that loss. This is unconstrained local linear projection, not a demonstrated feasible finite movement through bounds, assignment changes or global orbital modes.

## Deterministic c0 sensitivity, no refit

The c0 arm changes only c to zero at exactly the same original geography and complete nuisance/timing state. Its current posterior weights change, so this is not a matched-weight information comparison or an optimized c0 ablation. Both primary projections use the same five-calibration-column span. The additional four-coefficient result removes the c direction explicitly.

| Source | Signal mass | cal+timing retained % (5coef) | With priors % | cal+timing retained % (c fixed, 4coef) |
|---|---:|---:|---:|---:|
| S01 | 1484.080 | 0.5045 | 0.5267 | 0.5046 |
| S02 | 899.128 | 0.8451 | 0.8912 | 0.8470 |
| S03 | 1483.108 | 0.5355 | 0.5640 | 0.5363 |
| S04 | 1883.267 | 0.4750 | 0.5220 | 0.4813 |
| S05 | 2301.228 | 0.2293 | 0.2553 | 0.2300 |

## Eigenvalues, axes and units

| Source / arm | Raw weak / strong eigenvalues | After cal+timing weak / strong | Projected weak axis degrees from east (mod180) |
|---|---:|---:|---:|
| S01 / fitted-c | 8510.500 / 12971.504 | 47.943 / 63.717 | 109.575 |
| S01 / deterministic-c0-zero-only | 7752.650 / 11958.879 | 40.620 / 58.834 | 117.920 |
| S02 / fitted-c | 7160.777 / 12615.534 | 37.837 / 55.879 | 15.434 |
| S02 / deterministic-c0-zero-only | 3147.244 / 6137.362 | 31.867 / 46.600 | 46.346 |
| S03 / fitted-c | 13650.955 / 30294.833 | 46.360 / 100.330 | 171.462 |
| S03 / deterministic-c0-zero-only | 5406.259 / 13145.872 | 33.956 / 65.387 | 168.425 |
| S04 / fitted-c | 9469.739 / 22768.615 | 33.121 / 86.464 | 159.351 |
| S04 / deterministic-c0-zero-only | 7608.735 / 17148.631 | 33.734 / 83.866 | 160.671 |
| S05 / fitted-c | 13667.412 / 20699.855 | 20.513 / 55.516 | 20.702 |
| S05 / deterministic-c0-zero-only | 13008.777 / 19966.785 | 20.492 / 55.124 | 21.901 |

All matrices have units NLL-equivalent/km². The saved field name `information_hz_gaussian_per_km2` denotes its frequency-Gaussian origin; it does not add an extra Hz factor. Eigenvectors are regional east/north unit axes with arbitrary sign. Full matrices, generalized raw-relative eigenfractions, raw signed eigenvalues, nuisance spectra, column norms and cutoff sensitivity are retained in summary.json. No inverse-information distance, error ellipse or standard error is claimed.

Nuisance columns have different physical units and are first normalized to unit data or data+prior norm. The column span is preserved; eigenspace rank uses1e-12 of the normalized Gram maximum (with a unit floor), with predeclared1e-10/1e-14 sensitivity. All primary fitted projected nuisance blocks are full rank, and their reported trace fractions are unchanged at those two sensitivity cutoffs. This is not a rank threshold fitted to obtain a desired answer.

## Exact existing priors and clock scale

Actual archived clock precision is verified against the entire node/null-basis matrix for every source and arm. It implies prior_scale4:200Hz amplitude and100Hz node-second-difference penalty widths, not the class defaults50/25. These are penalty widths in that clock basis, not pointwise marginal oscillator uncertainty. Each RX has its own clock common across bands; node constant/linear modes are removed by its null basis. The3s recording-time prior is separate from these Hz-valued receiver-frequency clocks.

The five affine/RF coefficients have no Gaussian prior. The ridge adds exactly the existing clock precision and total-time precision `(I−11ᵀ/K)/4 + 11ᵀ/(9K²)`. This preserves the3s common mean and2s relative priors once. Each actual endpoint prior ledger closes after adding unchanged q and fixed-band penalties. There is no added geography ridge, q curvature in the frequency-mean projection or invented timing-age uncertainty.

## Interpretation and qualification

Weights are each arm’s current satellite responsibilities divided by actual per-row sigma². q, candidate signal masses, signal/clutter totals and support counts are saved. In this sample, signal responsibility on hard-invisible or below1% soft-visibility alternatives is zero. This does not remove visibility’s normalizer derivatives from the actual objective; those effects are deliberately absent from the positive frequency-only surrogate.

The actual observed mixture Hessian also includes changing assignments/q/visibility, residual curvature, interpolation structure and bounds. The positive surrogate does not measure those terms or global ambiguity. Large local confounding is therefore not an accuracy ranking, proof of wrong timestamps, or justification for arbitrary prior tightening or more geographic starts.

Five component tests pass: explicit small-design versus block projection, span invariance under unit changes/redundant gauges, ridge PSD and common-time prior, zero-support/dimension guards, and actual4x clock-scale reconciliation. No giant n*k*parameter tensor is allocated. Each actual source checks original fitted classification, all-row dimensions, posterior mass closure, exact prior ledger and immutable source bindings. One cosmetic102-character metadata string in the frozen runner triggers Ruff E501; it has no numerical effect and is left unchanged to preserve the run’s source authority. All numerical failures would have remained durable; this run completed without one.

Artifacts: summary.json plus ten source/arm JSONs contain the complete matrices and support/prior metadata. information_fractions.png/.pdf, spatial_eigenvalues.png/.pdf and weak_axes.png/.pdf are presentation only. No fits, RF, provider changes, production changes or prior/threshold tuning followed these results.
