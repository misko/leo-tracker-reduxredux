# Full replay of the 1,000 Hz Doppler track prior

The frozen 1,000 Hz prior improved the `c = 0` median error on common fixes from the 125 roofs new to this test. The fitted-`c` median rose by 5 m, so the predeclared median criterion across both calibration settings failed. Both settings gained three fixes within 5 km across all scheduled roofs. Both methods withheld all nine historical omitted-tile offers.

## Prospectively scored position errors

| Metric on 125 roof recordings new to this offset test | `c = 0`, zero → 1,000 Hz | Fitted `c`, zero → 1,000 Hz |
| --- | ---: | ---: |
| Published | 111 → 110 | 111 → 110 |
| Within 5 km out of 125 | 106 → 109 | 106 → 109 |
| Median on 105 common fixes | 1.759 → 1.590 km | 1.584 → 1.589 km |
| P95 on 105 common fixes | 4.593 → 4.496 km | 4.605 → 4.467 km |
| Published-only worst error | 6.044 → 5.311 km | 6.194 → 5.340 km |
| All-attempt median | 1.887 → 1.816 km | 1.755 → 1.805 km |

Five recordings published only with the offset prior, six published only at zero variance, and nine withheld in both. All-attempt percentiles retain withheld or failed recordings in their denominators. Coverage remained below 95%, so the all-attempt P95 and worst entries are null. The separate common-fix and published-only percentile distributions describe measured coordinates. The 125-recording panel contains 122 DS26 and three DS29 recordings.

Across all 135 roofs, publication changed from 119 to 118 and fixes within 5 km changed from 114 to 117 in both calibration settings. The four original v5 options each published 135 positions and placed 133 within 5 km in each setting. Their medians ranged from 0.953 to 0.988 km across the four options and both calibration settings. The five standard plots show all 135, the 125 new-to-this-test cases, the four original diagnostics, the six previously salted cases, and the nine omissions. Each roof chart includes the four original v5 references.

## Frequency and omitted offers

| Median on 125 roofs new to this test | `c = 0`, zero → 1,000 Hz | Fitted `c`, zero → 1,000 Hz |
| --- | ---: | ---: |
| Held Gaussian deviance per point, relative to the shared base covariance | 8.335 → 1.895 | 8.229 → 1.893 |
| Relative held log determinant per point | 0 → 0.198 | 0 → 0.198 |
| Held raw RMS | 1,334.7 → 1,347.5 Hz | 1,283.7 → 1,328.0 Hz |
| Final raw RMS | 182.6 → 383.2 Hz | 161.6 → 372.6 Hz |

The held score integrates the Gaussian offset over each held track and includes its relative covariance log determinant. The raw RMS uses the residual before any track-constant adjustment. The per-recording scores also give the quadratic and phase-prior contribution separately. Those frequency measurements have their own columns and denominators.

On omitted offers the same prior reduced median held deviance from 34.243 to 3.990 at `c = 0` and from 33.757 to 3.989 with fitted `c`. The number of omissions rejected at the held-support check changed from five to one, while other gates withheld the remaining offers. This includes the three earlier omissions and six new to the offset test. Both methods withheld all nine, with forced medians near 30 km. Lower held deviance on its own supplies little evidence that a tile contains the receiver.

## Frozen inputs

Each of the 144 pairs ran fresh from the same complete native detection archive and causal catalogue on the same pinned CPU, with order alternating by the prospective plan. All matched their archived Graph digest. The four training, held and final ownership and alias receipts agreed across every pair. The 26 prior decisions and all 52 prior forced endpoints reproduced exactly. The paired worker stage took 169.2 elapsed seconds on eight assigned CPUs.

The only model change was the independent source-fixed Gaussian constant per Graph track. The pinned v5 source specifies its prior per merged carrier component, which can group a different sample set. Both calibration settings retain the same anonymous Graph ownership, CFO integer branches, raw tracks, orbital propagation, gate thresholds and solver budgets. The separate accounting for the held log determinant does not participate in publication decisions.

[Prospective protocol](PROTOCOL.md) · [Per-recording scores](per-recording.csv) · [Full distributions](summary.json) · [Prediction lock](prediction-lock.json)

```sh
report=reports/2026_11_19_receiver_screening/refinement/marginal-full
python -m tools.pipeline_eval figures --panel screening --evidence "$report" --arm both --out /tmp/marginal-full-figures
```
