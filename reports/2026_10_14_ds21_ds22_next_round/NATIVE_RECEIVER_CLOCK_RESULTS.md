# Native common receiver clocks: negative first six-start result

The matched full-band probe worsened both configured-reference distances. Only five of twelve fits passed the unchanged independent stationarity check under the original 20-second/600-iteration limits. No model was promoted and no failed start was retried.

| Case | Model | Configured distance km | Objective | Likelihood NLL | Posterior RMS Hz | Stationary new starts |
|---|---|---:|---:|---:|---:|---:|
| 001 | Original C | 21.266493 | 41863.551059 | 41529.962579 | 146.023317 | — |
| 001 | Native common clock | 29.257438 | 42408.127844 | 41991.555740 | 155.290260 | 1/6 |
| 019 | Original C | 142.113760 | 41673.350596 | 41281.479093 | 154.112857 | — |
| 019 | Native common clock | 151.943354 | 41242.425723 | 40715.794380 | 131.841548 | 4/6 |

DS22's reference remains configured-unconfirmed. The full case pair was sealed and training-selected before the reference join; no verified accuracy or full-dataset target is claimed.

The 001 result demonstrates a search shortfall: the original selected C endpoint, embedded with zero new clock coefficients, has exactly the original objective 41863.551059 under the augmented model, lower than every returned new fit. The feasible optimum of the augmented model therefore cannot be worse than the original point, although the prescribed cold-start search found a worse stationary solution. This result does not establish that the augmented model itself must prefer a farther position. It also does not license treating a failed fit as stationary.

On 019, the selected training objective, likelihood NLL and frequency RMS all improve while the configured position distance worsens. Additional receiver flexibility therefore has not solved the ranking problem in this probe. The all-band variants do not yet have matched augmented half-band results; the original half-band results cannot substitute for that missing experiment.

All six original starts, original per-start disk centers, candidate banks, observations, timing priors, fitted c and receiver band offsets were retained. Only the new 18 common receiver clock coefficients were added, initialized to zero, using the exactly qualified B node basis and prior at native candidate timestamps. Selection used only stationary training objectives. Original C matrices remain immutable controls.

001 selected start 2 (stationarity 0.0000863445); its other five starts exhausted the allowance without convergence. 019 selected start 0 (stationarity 0.0004246564), with starts 1, 4 and 5 also stationary; starts 2 and 3 failed stationarity. All twelve calls returned and all failures remain in the sealed matrices. Whole-case runs took 158.343750 and 148.221892 seconds respectively, below the 180-second internal bounds. The original fit function reports a small post-optimizer audit overhead beyond the nominal 20-second optimization cutoff on timed-out calls.

Source runner `1e4011de8`; post-seal evaluator `de2510695`; four runner/evaluator tests and Ruff pass, in addition to the eight prior model/qualification tests. Receipts: `local/ds22-native-clock-fit-v1/DS22-{001,019}` and `local/ds22-native-clock-comparison-v1/report.json`. The subsequent frozen held-frequency evaluation is reported in `NATIVE_RECEIVER_CLOCK_HELD_RESULTS.md`: 019 improves in both held bands despite worsening configured-reference distance. Neither training nor held frequency-score improvement is treated as position-accuracy evidence.
