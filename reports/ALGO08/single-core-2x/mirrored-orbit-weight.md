# Whole-satellite weights for the mirrored face test

## Frozen rule

Keep the latest nominal trajectory and the previously hash-locked face predictions, tracks and nuisance projection. Earlier tests changed the mean with a signed phase shift or rolling state extrapolation. The guard's receiver agreement and the solver's track-support powers do not weigh whole predicted orbits by their pre-capture revision stability. [Mean comparison](mirrored-causal-forecast.md) · [Guard](regional-exterior-veto.md) · [Track-support powers](../../../src/leo/analysis/localization_v3/family_weighting.py)

For each satellite, project the latest-minus-previous retarded Doppler at the common face midpoint through the same fixed nuisance space. Use its mean squared residual over all that satellite's points as the historical variance proxy. Use the squared simultaneous receiver differential RMS as a common noise floor, with the difference divided by √2 and receiver nuisance terms removed. Give satellite `s` the fixed mass `1 / (historical_MSE_s + stereo_MSE)` and normalize those masses to sum to one. The control gives every satellite equal mass. Each satellite contributes its mean squared scoring residual, regardless of its number of tracks, receivers or observations. Both models use the same unweighted nuisance projection so this isolates the mass change. The historical weights and stereo floor are hash-locked before opening the after-capture generator TLE. No position labels, sign changes or future element fields enter the weights.

Score the two locked, noiseless later-orbit face observations separately at both sites. Recheck after each single NORAD omission, refitting the common nuisance projection on retained observations and renormalizing the frozen masses. The after-capture TLE is the held-time target and both sites reuse that orbit revision. Advance only if both faces at both public sites are separated by the weighting rule. No full-solver or raw replay is part of this check.

## Lower mismatch, same face decisions

Both methods selected A for both later-orbit face observations at both sites. With all satellites included, the frozen weights got **2 of 2 A faces** and **0 of 2 B faces** correct. They brought the northern B comparison within 0.001622 Hz RMS of a tie without reversing it. The southern B preference remained decisively in favor of A. The weighting fails the advancement criterion in `46759c279`. [Complete face scores and satellite removals](measurements/mirrored-orbit-weight-scores.json)

| Site | Satellite mass | Noiseless A scores, A / B, Hz RMS | Noiseless B scores, A / B, Hz RMS | Correct A after removing one orbit | Correct B after removing one orbit |
|---|---|---:|---:|---:|---:|
| North | Equal | 6.653260 / 7.233602 | 6.213608 / 6.741527 | 12 / 12 | 1 / 12 |
| North | Historical | 3.159954 / 3.245272 | 3.199521 / 3.201143 | 11 / 12 | 4 / 12 |
| South | Equal | 1.660548 / 2.661008 | 1.145583 / 1.666577 | 13 / 13 | 0 / 13 |
| South | Historical | 1.234777 / 2.317988 | 0.691059 / 1.235519 | 13 / 13 | 1 / 13 |

The stereo floor was 5.132 Hz RMS in the north and 6.627 Hz in the south. The projected latest-minus-previous disagreement across individual satellites ranged from 1.473 to 21.970 Hz RMS in the north and from 0.149 to 64.223 Hz in the south. The normalized historical masses consequently ranged from 0.89% to 15.93% in the north and 0.14% to 12.84% in the south. The lower weighted mismatch describes frequency fit under a different allocation of mass. The two fixed-face outcomes above supply the geographic check. [Pre-reveal weights and epoch gaps](measurements/mirrored-orbit-weights.json)

The pre-capture archive and saved factors produced a weight lock of `ed599f98d595e6d9f975c7df05f27b6e3d7a11476a27643256a987bc242eced1`. The separate scorer verified that digest and the earlier prediction lock before loading the later generator TLE. The leave-one-satellite-out counts show sensitivity on this held revision, with no claim of calibrated uncertainty or site transfer. The track offsets absorb `c` in both controls. No full solver was run. Seven component tests passed. [Runner](mirrored_orbit_weight_trial.py) · [Component tests](../../../tests/pipeline_eval/test_mirrored_orbit_weight_trial.py)
