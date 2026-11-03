# Frequency calibration transfers, but saved location rankings do not improve

Calibrating the complete candidate-set likelihood on two datasets improves
predictive density on every scan in the third dataset. Repeating this for
DS9/DS10/DS11 gives 12/12 predictive gains. It changes none of the saved location
hypothesis selections, so this is not a geographic improvement.

| Excluded target dataset | Scale (Hz) | Signal probability | Mean target log-density gain (nats/group) |
|---|---:|---:|---:|
| DS9 | 44.98 | 0.9382 | 0.8825 |
| DS10 | 42.83 | 0.9389 | 0.7757 |
| DS11 | 50.07 | 0.9339 | 1.0168 |

The baseline uses 200 Hz and probability 0.5. Both parameters maximize the
mean of eight donor scans' mean candidate-set log likelihoods. Each source group
appears once with its complete admitted candidate set, preserving the existing
uniform-clutter model. Target data do not enter calibration; GPS is not used.
All optima are interior to the fixed bounds (1–2000 Hz, probability .001–.999).
The profile search covers 61 log-scale points before local refinement.

The 7,933 eligible groups out of 13,530 have one active prediction and at least
one candidate. Pooled nearest-peak coverage changes as follows:

| Nominal | Original observed | Calibrated observed |
|---|---:|---:|
| 50% | 93.34% | 54.34% |
| 90% | 96.96% | 90.92% |
| 95% | 97.66% | 94.26% |

These are frequency-region coverage measurements, not geographic confidence
regions or verified emitter-presence probabilities. Per-scan 50% coverage still
ranges from 32.85% to 67.62%. DS11 retains a systematic central excess. Admitted
peaks are detector-selected and may be dependent or nonuniform under clutter;
this experiment does not remove those model limitations. These are previously
exposed development recordings, not final independent-recording validation.

![Excluded-dataset frequency calibration](candidate-density-transfer-v1.png)

## Geographic test

After sealing calibration, score all converged saved chronological-split modes
with the excluded-dataset parameters. Seal rankings before loading the geographic
reference. All 12 winners are identical to the original checking-score winners.

| Method on the same 12 scans | Median error (m) | p90 error (m) |
|---|---:|---:|
| Original all-data baseline | 1,892 | 3,998 |
| Training-only split winner | 2,033 | 5,355 |
| Original checking-score ranking | 2,099 | 5,355 |
| Calibrated checking-score ranking | 2,099 | 5,355 |

All 12 saved fits qualify; 3/12 calibrated selections are within 1 km and 8/12
within 3 km. Even the reference-selected best saved modes yield median 2,033 m
and p90 5,235 m. That oracle is diagnostic only and does not bound unexplored
solutions. Improving selection among these saved modes cannot reach the target.

Source/input seals and training prediction parity pass. Two tests verify exact
likelihood parity against the production candidate function across parameter
settings, and recovery of known synthetic parameters with differing peak counts.
Calibration took 0.38 seconds; reconstructing/scoring saved modes took 18.95
seconds for all 12 scans. These are incremental diagnostics, not cold end-to-end
runtime measurements. No new localization fits, uncertainty estimates, RF,
production changes, or full64 promotion.

Next: a three-scan controlled continuous refit with frozen excluded-dataset
parameters and unchanged initialization/identity policy. Compare against the
existing uncalibrated candidate refit and all-data baseline. Preserve the 90-second
cold pipeline requirement; a warm diagnostic alone cannot establish runtime
compliance. Do not expand to64 merely because candidate density improves.

Evidence: `candidate-calibration-inputs-v1.json`,
`candidate-density-transfer-v1.json`, `calibrated-checking-modes-v1.json`,
`calibrated-checking-modes-v1-evaluation.json`, and their SHA256 sidecars.
