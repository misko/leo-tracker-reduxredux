# Single-seed bridge into the v5 cavity fit

A blind, detrended Doppler seed reduced full stored-GLRT-to-position wall time from 94.70 to 44.98 seconds on DS26-0036 and from 49.18 to 37.47 seconds on DS29-0082. Both calibration arms returned fixes on all six recordings. The bridge missed the joint target of 10–30 seconds and geographic error within 10% of original v5. Its inference stages after native preparation took 15.31–25.14 seconds. DS29-0082 and the separate stress recording DS26-0066 lost substantial position accuracy in both arms. [Per-arm charts](charts/index.html) · [Scores](scores.csv)

## Receiver path

The seed projects the complete visible causal catalogue at the supplied roof centre once. It ranks each curved track by the residual after removing the track’s independent frequency offset and linear rate from the measured-minus-predicted Doppler and from the phase derivative. The original phase prior, ±15-second phase bound and 450 Hz residual limit apply to the resulting statistic. Track phases are pooled by the satellite-wise median. One joint zero-calibration fit estimates receiver offsets and drift, then one physical reassociation and a joint refit supply the warm start for both calibration arms.

The warm start replaces the initial three-seed scan. The paired conservative stage uses two early rounds and up to 24 position steps, reuses the original paired exclusion gates, and omits exhaustive salvage. The existing Armijo optimizer handles position steps. The original family/history, predictive, signed and cavity gates and late budgets run beyond the seed. The early retention gate kept 808–2,604 points across the six recordings. The bridge ends at compact v5’s cavity result. The later full-v5 position repair remains represented by its archived reference endpoints.

The first centre profile fit satellite phase and an intercept before estimating shared radio drift. It returned zero fixes, including five withholds and one recorded empty-mask failure. That entire experiment remains available under its original source lock. DS26-0036 and DS29-0082 drove the detrender choice. The three hashed confirmation IDs were fixed before either trial. [First experiment and worker snapshot](center-profile/README.md) · [Protocol](PROTOCOL.md)

## Timing

Both fresh compact controls replayed the same native input, causal catalogue and supplied region as their candidate on the same pinned CPU. The candidate ran first on CPU 20, and the control ran first on CPU 22. The stress and confirmation groups have source-bound historical compact controls. Their archived runtimes are excluded from fresh speed comparisons.

| Recording | CPU | Compact wall → bridge (s) | Compact CPU → bridge (s) | Compact initial + conservative → bridge (s) |
|---|---:|---:|---:|---:|
| DS26-0036 | 20 | 94.70 → 44.98 | 86.82 → 43.11 | 40.32 → 3.31 |
| DS29-0082 | 22 | 49.18 → 37.47 | 48.09 → 35.50 | 12.90 → 1.13 |

Across all six bridge runs, full wall was 37.47–47.79 seconds and worker CPU was 35.50–47.17 seconds. The logged native preparation stage took 14.05–20.01 seconds and starts after reading the stored native document. The full timing also includes binding and building the projector library. Subtracting only the measured native preparation stage from full wall leaves 19.66–28.92 seconds, including the other wrapper work. Initial plus conservative inference took 1.13–4.60 seconds. The two source-locked experiments completed 710.7 seconds after the first budget lock, within the shared 900-second limit. [Stage timings and endpoints](scores.csv) · [Frozen source and schedule](source-lock.json)

## Accuracy and frequency fit

Errors below use the full original v5 baseline and the same receiver reference. The final columns give the bridge’s conditional Doppler RMS on its retained observations. On the fresh compact controls, the c0 and fitted RMS were respectively 74.761 and 74.682 Hz for DS26-0036, and 97.004 and 96.684 Hz for DS29-0082. In DS29-0082, fitting c slightly reduced the bridge’s conditional RMS while geographic error increased. Candidate and compact RMS can describe different retained observation sets. The scores list the other three original v5 reference roles and the matched compact result separately.

| Recording | Cohort | c0 error, original → bridge (km) | Fitted c error, original → bridge (km) | Bridge c0 RMS (Hz) | Bridge fitted c RMS (Hz) |
|---|---|---:|---:|---:|---:|
| DS26-0036 | Development | 1.278 → 0.892 | 1.208 → 0.752 | 74.648 | 74.648 |
| DS29-0082 | Development | 0.567 → 1.430 | 0.517 → 1.539 | 98.537 | 98.149 |
| DS26-0066 | Stress | 1.244 → 2.846 | 1.218 → 2.786 | 64.935 | 65.001 |
| DS26-0313 | Confirmation | 1.300 → 1.343 | 1.321 → 1.478 | 62.039 | 62.001 |
| DS26-0279 | Confirmation | 0.989 → 0.332 | 0.988 → 0.331 | 60.683 | 60.683 |
| DS29-0604 | Confirmation | 0.982 → 0.971 | 1.041 → 1.020 | 79.694 | 79.734 |

The development and stress cohorts missed the 10% geographic gate in both arms. On confirmation, c0 median was 0.971 km versus 0.989 km original, and P95 was 1.306 km versus 1.269 km original. The fitted arm’s median improved to 1.020 km from 1.041 km, while P95 rose to 1.432 km from 1.293 km, an increase of 10.8%. The six candidate runs establish measured fixes on this roster. The samples of two development, one stress and three confirmation recordings leave corpus-wide coverage and accuracy open. The frozen v5 binding accepts only the original 25 km roof tile. This experiment contains no alternate roof offers. [Cohort gate results](summary.json) · [Position archives and checksums](receipt.json)

The two largest regressions separate into different failure modes. DS29-0082 changed two satellite labels that survived the seed and conservative gates. The cavity’s held-family prediction preferred the original identity for one of them. DS26-0066 agreed with the original on all shared retained track labels but omitted 455 points before the family fit. The full original v5 also improved that recording with a separate reassociation after compact v5’s cavity boundary. [Matched checkpoint and held-family diagnostic](diagnostic/README.md)
