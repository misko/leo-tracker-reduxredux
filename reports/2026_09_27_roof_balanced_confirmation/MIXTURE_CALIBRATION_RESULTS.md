# Candidate-mixture calibration passes its predictive gate

All six conditional reception leave-one-session-out folds completed and passed the unchanged numerical checks after bounded Newton refinement. Each refined fold took 12.49–13.91 seconds; its original raw fit remains separately preserved. The final aggregate verifies input/code/protocol bindings, partitions, feature schemas, raw and refined artifacts, observation counts, and likelihood components.

Lower joint negative log likelihood (NLL) is better. Scores are track-normalized reception likelihoods, not distance errors.

| Held calibration recording | Tracks | Direction-free M0 | Mean-direction M1 | Candidate-mixture M1 |
|---|---:|---:|---:|---:|
| 39ac2b14d1bb5f0f | 62 | 0.963619 | 0.643367 | 0.444380 |
| 4c56320fb5ca6994 | 60 | 1.084753 | 0.853258 | 0.643844 |
| 9d7b6a0db558703a | 57 | 1.125688 | 0.852660 | 0.747918 |
| aa9770c66396e928 | 55 | 1.263223 | 1.118557 | 0.796944 |
| c559f436d578c9bd | 52 | 1.020220 | 0.899678 | 0.551970 |
| da2858f6cd2521b7 | 58 | 1.003113 | 0.920897 | 0.778932 |
| Pooled, equal track weight | 344 | 1.074718 | 0.876168 | 0.658506 |

All predeclared advancement checks passed:

- All arms/folds meet gradient, curvature, and multistart stability requirements.
- Pooled mixture NLL is lower than both M0 and the same-objective mean-direction control.
- Six of six scans improve versus mean, exceeding the required four.
- Removing c559, the largest favorable contribution, leaves a positive mean-versus-mixture gain of 0.194503 NLL per track.

## What this establishes—and what it does not

The model that fits candidate-specific likelihoods with one shared satellite identity per track predicts reception evidence better on these conditional calibration holdouts than the matched mean-direction model. The matched control has the same nuisance variables, full-row weighting, ridge convention, variance estimation, optimizer, and starts, isolating candidate marginalization from those other modeling changes.

Frequency parameters, identities, and prior weights were fitted using all six calibration sessions. These are therefore conditional reception holdouts, not fully nested end-to-end validation. Both priors and geographic errors are absent from the advancement decision. Shared-observation frequency/reception dependence and approximate antenna/pose calibration remain limitations.

This passes the gate for a geographic experiment; it does not prove better distance accuracy, calibrated geographic uncertainty, or improved tracking resolution. The next scoped test is a fixed-coordinate comparison of Doppler-only, the same-objective mean-direction calibration, and candidate-mixture calibration, preserving independent Sacramento/Reno candidate fitting. Already-unblinded location grids remain development data. A subsequent resolution claim requires a frozen estimator and disjoint confirmation.

Source: `mixture_calibration_polished.json` and its seven bound refined artifacts, with their separately preserved raw fits. The experiment suite passed 92 tests before the runs. Software checks are not a substitute for the geographic test.
