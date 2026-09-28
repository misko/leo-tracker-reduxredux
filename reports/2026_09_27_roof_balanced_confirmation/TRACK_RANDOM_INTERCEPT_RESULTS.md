# Shared detection effect passes conditional reception validation

The numerically refined detection random-intercept experiment passed its predeclared advancement gate. It has not yet been evaluated for geographic error and does not establish improved tracking resolution.

## Model and scope

One zero-mean Gaussian detection-logit offset is shared by all rows of each track and integrated out, not freely optimized per track. Its population standard deviation is learned using calibration data only. Existing reception coefficients, candidate priors, feature schemas, frequency model, ratio likelihood, and row/track normalization remain fixed. Each held session uses a scale learned from the other five sessions. The frozen frequency priors still use all six sessions: these are conditional reception holdouts, not fully nested location validation.

## Held-out results

Lower joint reception NLL per track is better. This is not distance error or a percentage of correct satellite associations.

| Arm | Original independent detection | Shared detection effect |
|---|---:|---:|
| Directionless M0 | 1.074718 | 0.773205 |
| Mean direction | 0.876168 | 0.652007 |
| Candidate mixture | 0.658506 | 0.542909 |

All 344 held-out tracks are included exactly once. The candidate-mixture arm improves in all six sessions:

| Held session suffix | Tracks | Fitted sigma, logit units | Original NLL/track | Shared-effect NLL/track |
|---|---:|---:|---:|---:|
| 39ac2b14d1bb5f0f | 62 | 2.753528 | 0.444380 | 0.386102 |
| 4c56320fb5ca6994 | 60 | 2.740625 | 0.643844 | 0.585757 |
| 9d7b6a0db558703a | 57 | 2.462766 | 0.747918 | 0.638644 |
| aa9770c66396e928 | 55 | 2.349171 | 0.796944 | 0.632985 |
| c559f436d578c9bd | 52 | 2.595500 | 0.551970 | 0.482336 |
| da2858f6cd2521b7 | 58 | 2.350423 | 0.778932 | 0.541012 |

Pooled mixture gain is 0.115596 NLL/track; excluding the largest-gain session leaves a positive gain of 0.090789. The full-calibration mixture sigma is 2.561860. No fitted scale reaches the bound of eight.

The directionless arm also improves substantially, showing that this is not solely a geometry gain. The mixture still has lower held joint NLL than either directionless or mean-direction models under the new effect. This remains prediction at known calibration positions, not proof of discrimination between nearby receiver positions.

## Important ratio caveat

Mixture detection NLL improves from 0.455411 to 0.318508. Joint-minus-detection, the conditional ratio increment under shared identity, increases from 0.203094 to 0.224402. The ratio coefficients did not change, but the detection-conditioned satellite weights did. Thus detection improves more than the complete joint score, and the next geographic test must retain and inspect this tradeoff rather than assuming every component improves.

The separate conditional ratio dispersion audit also found 5.7768 times the model-implied track residual-sum variation. This first detection-only prototype does not address all reception-model misspecification. A random intercept changes marginal detection means as well as dependence, so its benefit does not uniquely identify temporal correlation as the cause.

## Numerical and reproducibility checks

- Original fixed-grid full fit failed its integration-accuracy check and is preserved; no original LOSO runs were launched.
- The initial mode-centered retry stopped on a bracket solver failure before writing any artifact. The exact failing track is now an independent-integration regression test.
- Refined full fit and all six LOSO shards completed. Maximum 64-versus-128-point candidate-track likelihood difference across every arm and split is 0.000001286, below the unchanged 0.001 tolerance.
- Sigma-zero scores reproduce the original core to at most 8.88e-16 in the full fit.
- Independently verified all seven artifact hashes and every recorded code hash after aggregation.
- All 173 tests in the experiment directory pass.

No geographic search, candidate sharing between priors, production modification, or new RF collection occurred. The next step is a frozen same-grid comparison on the existing development cases, then genuinely disjoint geographic confirmation if it improves. Neither step has been completed for this model.

Artifacts: `track_random_intercept_refined.json`, `track-random-intercept-refined-full.json`, six `track-random-intercept-refined-fold-*.json` files, `run_track_random_intercept_refined.py`, and `TRACK_RANDOM_INTERCEPT_REFINEMENT_PROTOCOL.md`.
