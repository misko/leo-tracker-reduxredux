# One centre-based Doppler update with exact owners

One linearized site update missed the installed-v3 position accuracy threshold in **all four calibration arms**, despite exact curved and predictive owners and signed aliases. It reduced the exact centre-to-endpoint likelihood loss and improved held Doppler predictions on both recordings. The complete paired diagnostic took **6.45 ms** on weak DS30-0016 and **10.68 ms** on North after the dormant owner oracle supplied its rows. The result rules out qualifying this frozen update on the two development inputs. [Frozen protocol](centre-oracle-step-protocol.md) · [Summary receipt](measurements/centre-oracle-step-summary.json) · [Complete sealed readouts](measurements/centre-oracle-step.json.gz)

## What the update used

An unchanged saved short-receiver solve reproduced the original publication's selected endpoint, RF RMS, observation IDs, roles and owners in both arms. A separate prior sealed study supplied the exact signed aliases for verification. The new numerical diagnostic received only the selected support, same original observed CFO and RF, original region and causal orbit and phase priors. It kept **93 curved and 23 predictive observations** on weak, and **287 curved and 60 predictive** on North. The archived fitted endpoints and residual-derived weights were used only for control verification or scoring. No surveyed or simulated position entered either fit. [Owner capture](centre_oracle_step_trial.py) · [Previous signed alias evidence](fixed-causal-estimation.md)

The site starts at the supplied centre and the phase expansion uses the causal prior mean. It differentiates the nominal range rate at that point in the original geographic chart. The local fit holds nuisance columns fixed, including receiver hardware and smooth terms, phase and orbital modes, and 300 Hz per-track bias priors. It uses the released Graph noise scales and the original \(\sqrt{2}\) multiplier on predictive noise. The surrogate assumes a Gaussian prior with the causal widths and unit noise precision and family powers. Under that Gaussian approximation, placing predictive rows in the shared nuisance solve represents the same conditional Gaussian factorization with independent predictive track biases. The robust check re-evaluates the original curved and predictive likelihood at the centre and endpoint with unit family powers. That check can reoptimize its own precisions and coefficients without affecting either proposed location. Neither arm makes another site update or phase refresh. [Implementation](centre_oracle_step.py) · [Released predictive noise model](../../../src/leo/analysis/localization_v3/predictive_linear.py)

This differs from the earlier affine experiment, which started from the selected endpoint weights and measured an approximation to the curved likelihood. The dense mixture oracle supplied curved ownership and tested an iterative cold fit. The full-arc design evaluated centre information with zeroed CFO and then used an iterative signed fit on South. The postfit geographic jackknife's single step used the already-fitted endpoint and exact original phase expansion. The existing stock-finish and profiled-Gamma studies preserve the phase refreshes and nonlinear solver. [Affine](../single-core-2x/solver-affine.md) · [Mixture oracle](mixture-oracle.md) · [Complete-arc design](arc-design.md) · [Postfit jackknife](geographic-jackknife.md) · [Stock finish](../single-core-2x/solver-stock-finish.md) · [Profiled Gamma](profiled-gamma-live.md)

## Position and RF results

All values in paired cells are fixed-zero / fitted \(c\). Each pair uses identical rows, aliases, priors and location bounds, with the fitted arm adding the original RF-dependent nuisance column.

| Containing offer | Installed v3 error km | Original same-packet error km | One-step error km | One-step added error vs v3 km |
|---|---:|---:|---:|---:|
| Weak DS30-0016 | 1.644 / 1.661 | 1.311 / 1.694 | **2.871 / 3.603** | +1.228 / +1.942 |
| North | 0.106 / 0.141 | 0.390 / 0.121 | **2.073 / 2.151** | +1.967 / +2.011 |

All positions remained inside the square. Both projected site information matrices had positive eigenvalues on each recording. Weak eigenvalues were **0.052–0.102 / 0.047–0.100** and North **0.413–3.578 / 0.395–2.313** in normalized loss units per km². The result shows an accuracy failure with a finite two-dimensional update. [Physical reference and original transfer](weak-combined-raw.md) · [Public North control](north-causal-transfer.md)

| Containing offer | Held normalized MSE, centre → move | Exact loss, centre → move | Endpoint curved RF RMS Hz | Endpoint predictive RF RMS Hz |
|---|---|---|---:|---:|
| Weak DS30-0016 | 1.050 / 1.021 → 0.974 / 0.929 | 510.63 / 518.58 → 506.83 / 516.02 | 119.30 / 117.86 | 106.89 / 608.88 |
| North | 7.721 / 8.591 → 6.759 / 6.864 | 682.63 / 644.89 → 559.61 / 578.97 | 67.31 / 67.98 | 264.73 / 342.91 |

The held check trained on earlier times and forecast the last fifth of each arc, leaving **25** held observations on weak and **79** on North. It used the frozen linearization and training-only nuisance fit for each location. Its independence is conditional on the full oracle roster, whose original selection used the entire recording. The held error improved by **7.2–20.1%**. The separate exact endpoint RF check shows larger predictive residuals in both fitted-\(c\) arms than in their fixed-zero counterparts. The location errors worsened as well. These RF results are conditional on the one-step phase expansion and unit family powers. [Held computations and exact RF readouts](measurements/centre-oracle-step.json.gz)

## Measured work

| Offer | Original owner-oracle replay CPU s | Paired centre preparation and exact scores CPU ms | Two Schur updates CPU ms | Two exact endpoint checks CPU ms | Two held checks CPU ms | Complete paired diagnostic CPU ms |
|---|---:|---:|---:|---:|---:|---:|
| Weak | 3.338 | 3.884 | 0.420 | 1.760 | 0.266 | 6.447 |
| North | 4.108 | 6.571 | 0.483 | 3.054 | 0.440 | 10.675 |

The oracle replay used the released receiver evidence and stopped at the original selected publication boundary. The paired diagnostic includes centre preparation, one exact robust likelihood calculation at each centre and endpoint, the two bounded linear algebra updates, and truth-free held arithmetic. Figure rendering, evidence grids and new qualification are outside these clocks. An attainable replacement still needs owners and signed aliases. The saved result supplies no qualifying speedup or localization evidence for a different derivative or repeated phase/site update. Six focused tests passed. [Tests](../../../tests/pipeline_eval/test_centre_oracle_step.py)

Run the trial once per case as `centre_oracle_step_trial.py physical OUTPUT` and `centre_oracle_step_trial.py north OUTPUT` using the pinned requests from the existing fixed-causal study. Use the report folder, installed payload, release source and checkout in the discovery path in that order, with the released interpreter and archive-readable account. Run under the shared Gauss lock at CPU 2, nice 15, I/O priority 7 and one numerical thread. Keep outputs in new tmpfs scratch. After both results seal, run `centre_oracle_step_score.py DIRECTORY NEW_SUMMARY NEW_FULL` using the repository source environment. [Bindings and build pins](centre_oracle_step_trial.py) · [Independent scoring](centre_oracle_step_score.py)
