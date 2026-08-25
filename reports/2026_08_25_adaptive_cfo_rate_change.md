# Effect of longer frame-CFO history on apparent Doppler-rate estimates

## Result

The fixed 500 ms causal fit changes the **short-timescale rate state** much more
than it changes the **central rate of a track**.

On H7, the only holdout capture with complete provenance and sufficient support,
the median paired rate shift from fixed 125 ms to fixed 500 ms was between
`-31` and `+10 Hz/s` across the three forecast horizons. This is less than 1%
of the approximately `-3.2 kHz/s` apparent CFO rate. Individual causal states,
however, moved by a median `247–282 Hz/s`; the 90th percentile absolute change
was `658–739 Hz/s`. The longer fit reduced the within-cell rate MAD by 53–72%
and reduced future odd-Qin CFO RMS by 32–63%.

This is evidence of **lower observed rate-state dispersion rather than a
wholesale rate offset**.
The current adaptive selector does not improve the result: on H7 it worsened
future-CFO RMS at 125 and 500 ms and improved it only modestly at 1,000 ms.

The seven-capture holdout remains **INCONCLUSIVE**. Five of 55 frozen tiles
failed exact source/epoch binding, and only H7 supplied complete provenance plus
the preregistered numerical support at all three horizons. No estimator is
promoted by this analysis.

All rates below are receiver-relative apparent CFO rates. They are not yet
calibrated physical satellite Doppler rates or range accelerations.

## Methods and definitions

The comparison uses three causal frequency-only trackers:

- `fixed_125ms`: robust line fitted to the trailing 125 ms of qualified
  frame-CFO measurements;
- `fixed_500ms`: the same model fitted to the trailing 500 ms;
- `adaptive_75_500ms`: an even-Qin-only selector among 75, 125, 250, and
  500 ms histories.

Only past even-Qin frame estimates train the downstream tracker. Future odd-Qin
CFO is the response. The upstream Standard GLRT source, epoch, and alias were
selected using both Qin parities, so the comparison is fit-withheld within a
frozen source hypothesis rather than end-to-end odd-independent. The response
mask is also conditioned on future-target even-Qin qualification; this is not
an end-to-end sensitivity measurement on low-coherence frames.

For a target at horizon `H`, the rate state is evaluated at the last training
frame no later than `target - H`. A paired rate difference is

```text
delta_rate = fixed_500ms.rate_hz_s - fixed_125ms.rate_hz_s
```

at the identical causal cutoff. The median paired difference must not be
replaced by the difference between two separately computed marginal medians.
Rate MAD is the median absolute deviation about the rate median. Forecast RMS
first averages squared future odd-Qin error within device-sample-anchored
one-second blocks.

The persisted 1,416 forecast targets reduce to 1,239 unique causal cutoff
states when deduplicated by capture, training tile, and actual cutoff frame.
Repeated horizons with the same cutoff carried an identical fitted CFO, rate,
and selected-history state; forecast variance still changes with horizon. The
tracker itself runs at each supported 750 Hz frame, but the persisted forecast
diagnostic samples targets every 15 frames (approximately 20 ms); these 1,239
rows are therefore reported cutoff states, not every 1.3 ms tracker output.

## Deduplicated rate-state comparison

This table gives the most direct answer to how much the rate estimate itself
changed. All rate columns are in `Hz/s`; MAD is computed around each method's
own median.

| Capture | Provenance and support | Unique cutoff states | Median fixed 125 ms | Median fixed 500 ms | Median paired delta | Median absolute delta | Rate MAD, 125 -> 500 ms | Median adaptive |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| H1 | Incomplete; no forecasts | 0 | — | — | — | — | — | — |
| H2 | Incomplete; numeric support | 472 | -3,877.7 | -3,917.2 | -9.0 | 60.6 | 103.6 -> 55.7 | -3,917.2 |
| H3 | Incomplete; partial numeric support | 111 | -3,046.8 | -3,097.7 | -66.9 | 77.2 | 97.1 -> 64.5 | -3,097.7 |
| H4 | Complete but sparse | 8 | -3,834.0 | -4,034.6 | -109.3 | 264.3 | 189.4 -> 18.9 | -4,034.6 |
| H5 | Complete but sparse | 7 | -3,248.2 | -3,467.0 | -319.8 | 319.8 | 133.6 -> 82.3 | -3,467.0 |
| H6 | Incomplete and sparse | 51 | -3,727.7 | -3,658.2 | +52.3 | 200.4 | 182.2 -> 47.9 | -3,646.1 |
| H7 | **Fully evaluable** | 590 | -3,217.6 | -3,210.0 | -12.7 | 265.0 | 238.2 -> 93.4 | -3,230.3 |

On H7, the fixed-500 central shift is only `-12.7 Hz/s`, approximately 0.4%
of the central rate, while the typical local state moves by `265.0 Hz/s` and
the rate MAD falls by 60.8%. The large absolute change with a small signed
change is the signature of smoothing rather than a new track-wide slope.

## Decision-quality result: H7

H7 is the only capture for which the rate and forecast comparison is both
provenance-complete and numerically supported.

| Forecast horizon | Paired targets | Median rate, 125 -> 500 ms | Median paired delta | Median / p90 absolute delta | Rate MAD, 125 -> 500 ms | Future CFO RMS, 125 -> 500 ms |
|---:|---:|---:|---:|---:|---:|---:|
| 125 ms | 352 | -3,220.73 -> -3,206.38 Hz/s | -1.37 Hz/s | 281.53 / 739.21 Hz/s | 251.08 -> 93.11 Hz/s (-62.9%) | 103.15 -> 70.70 Hz (-31.5%) |
| 500 ms | 238 | -3,216.40 -> -3,215.48 Hz/s | -30.89 Hz/s | 246.57 / 658.34 Hz/s | 217.23 -> 101.47 Hz/s (-53.3%) | 276.31 -> 102.10 Hz (-63.0%) |
| 1,000 ms | 107 | -3,260.17 -> -3,258.45 Hz/s | +10.39 Hz/s | 251.24 / 694.49 Hz/s | 217.25 -> 61.72 Hz/s (-71.6%) | 558.06 -> 234.23 Hz (-58.0%) |

The local rate change matters more as the forecast horizon grows:

| Forecast horizon | Median absolute rate change | Median rate contribution `H * absolute rate change` | Median total prediction change |
|---:|---:|---:|---:|
| 125 ms | 281.53 Hz/s | 35.29 Hz | 54.72 Hz |
| 500 ms | 246.57 Hz/s | 123.29 Hz | 134.27 Hz |
| 1,000 ms | 251.24 Hz/s | 251.24 Hz | 268.79 Hz |

The persisted rows satisfy

```text
prediction_delta = cutoff_cfo_delta + actual_horizon * rate_delta
```

to numerical precision. Thus a roughly 0.25 kHz/s local slope correction can
produce a roughly 0.25 kHz prediction change at a one-second horizon even when
the capture-level central rate barely moves.

## Comprehensive holdout table

`N` is the number of paired future targets in the successful-tile diagnostic.
`delta` is the paired fixed-500-minus-fixed-125 rate change. Incomplete captures
were reindexed over successful tiles for this post-hoc diagnostic, so their
numbers are not frozen-gate results. Sparse cells do not satisfy the
preregistered target, block, or coverage requirement. Horizon-level rate
summaries are target-weighted; a cutoff state may recur at another horizon.

| Capture / horizon | Provenance and support | N | Median rate, 125 -> 500 ms | Median delta | Median / p90 absolute delta | Rate MAD, 125 -> 500 ms | Future CFO RMS, 125 -> 500 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| H1 / 125 ms | Incomplete; unavailable | 0 | — | — | — | — | — |
| H1 / 500 ms | Incomplete; unavailable | 0 | — | — | — | — | — |
| H1 / 1,000 ms | Incomplete; unavailable | 0 | — | — | — | — | — |
| H2 / 125 ms | Numeric support; incomplete | 293 | -3,872.77 -> -3,900.50 Hz/s | -1.96 Hz/s | 57.76 / 190.70 Hz/s | 107.00 -> 69.15 Hz/s (-35.4%) | 56.57 -> 51.44 Hz (-9.1%) |
| H2 / 500 ms | Numeric support; incomplete | 179 | -3,888.56 -> -3,928.06 Hz/s | -24.66 Hz/s | 61.83 / 176.95 Hz/s | 96.88 -> 42.83 Hz/s (-55.8%) | 84.92 -> 55.88 Hz (-34.2%) |
| H2 / 1,000 ms | Sparse; incomplete | 63 | -3,933.09 -> -3,960.44 Hz/s | -24.36 Hz/s | 55.73 / 128.37 Hz/s | 63.75 -> 24.69 Hz/s (-61.3%) | 165.82 -> 90.63 Hz (-45.3%) |
| H3 / 125 ms | Numeric support; incomplete | 100 | -3,038.12 -> -3,089.52 Hz/s | -65.61 Hz/s | 77.23 / 192.91 Hz/s | 95.22 -> 58.29 Hz/s (-38.8%) | 302.37 -> 295.42 Hz (-2.3%) |
| H3 / 500 ms | Sparse; incomplete | 11 | -3,143.92 -> -3,238.30 Hz/s | -70.79 Hz/s | 70.79 / 189.25 Hz/s | 121.32 -> 19.01 Hz/s (-84.3%) | 218.77 -> 203.86 Hz (-6.8%) |
| H3 / 1,000 ms | Incomplete; unavailable | 0 | — | — | — | — | — |
| H4 / 125 ms | Complete but sparse | 8 | -3,834.02 -> -4,034.63 Hz/s | -109.30 Hz/s | 264.32 / 391.45 Hz/s | 189.42 -> 18.90 Hz/s (-90.0%) | 465.74 -> 464.54 Hz (-0.3%) |
| H4 / 500 ms | Complete but unavailable | 0 | — | — | — | — | — |
| H4 / 1,000 ms | Complete but unavailable | 0 | — | — | — | — | — |
| H5 / 125 ms | Complete but sparse | 7 | -3,248.24 -> -3,467.00 Hz/s | -319.82 Hz/s | 319.82 / 470.22 Hz/s | 133.64 -> 82.25 Hz/s (-38.5%) | 121.00 -> 85.18 Hz (-29.6%) |
| H5 / 500 ms | Complete but unavailable | 0 | — | — | — | — | — |
| H5 / 1,000 ms | Complete but unavailable | 0 | — | — | — | — | — |
| H6 / 125 ms | Sparse; incomplete | 38 | -3,649.78 -> -3,647.43 Hz/s | -29.85 Hz/s | 204.89 / 964.57 Hz/s | 194.98 -> 55.92 Hz/s (-71.3%) | 189.95 -> 181.27 Hz (-4.6%) |
| H6 / 500 ms | Sparse; incomplete | 13 | -3,727.72 -> -3,674.30 Hz/s | +6.80 Hz/s | 190.18 / 538.65 Hz/s | 207.31 -> 54.60 Hz/s (-73.7%) | 184.33 -> 154.47 Hz (-16.2%) |
| H6 / 1,000 ms | Sparse; incomplete | 7 | -3,815.69 -> -3,690.58 Hz/s | +85.09 Hz/s | 151.71 / 181.05 Hz/s | 33.02 -> 44.49 Hz/s (+34.7%) | 182.31 -> 94.06 Hz (-48.4%) |
| H7 / 125 ms | **Fully evaluable** | 352 | -3,220.73 -> -3,206.38 Hz/s | -1.37 Hz/s | 281.53 / 739.21 Hz/s | 251.08 -> 93.11 Hz/s (-62.9%) | 103.15 -> 70.70 Hz (-31.5%) |
| H7 / 500 ms | **Fully evaluable** | 238 | -3,216.40 -> -3,215.48 Hz/s | -30.89 Hz/s | 246.57 / 658.34 Hz/s | 217.23 -> 101.47 Hz/s (-53.3%) | 276.31 -> 102.10 Hz (-63.0%) |
| H7 / 1,000 ms | **Fully evaluable** | 107 | -3,260.17 -> -3,258.45 Hz/s | +10.39 Hz/s | 251.24 / 694.49 Hz/s | 217.25 -> 61.72 Hz/s (-71.6%) | 558.06 -> 234.23 Hz (-58.0%) |

There is no valid seven-capture aggregate rate change. Only 6 of 21 cells met
the numeric support thresholds on available tiles, and only H7's three cells
also had complete capture provenance.

## Relation to the upstream GLRT trend

The following capture-level table deduplicates repeated horizon rows into unique
causal cutoff states. The upstream value is the selected final-trajectory linear
coefficient read from the external final-bank artifact pinned by each holdout
configuration entry. It is provided only as context: it is noncausal, used both
Qin parities, and is not rate truth.

| Capture | Upstream GLRT trajectory | Unique cutoff states | Median fixed 125 ms | Median fixed 500 ms | Median adaptive | Median paired 500 - 125 |
|---|---:|---:|---:|---:|---:|---:|
| H1 | -3.347 kHz/s | 0 | — | — | — | — |
| H2 | -3.856 kHz/s | 472 | -3.878 kHz/s | -3.917 kHz/s | -3.917 kHz/s | -0.009 kHz/s |
| H3 | -3.031 kHz/s | 111 | -3.047 kHz/s | -3.098 kHz/s | -3.098 kHz/s | -0.067 kHz/s |
| H4 | -3.959 kHz/s | 8 | -3.834 kHz/s | -4.035 kHz/s | -4.035 kHz/s | -0.109 kHz/s |
| H5 | -3.519 kHz/s | 7 | -3.248 kHz/s | -3.467 kHz/s | -3.467 kHz/s | -0.320 kHz/s |
| H6 | -3.627 kHz/s | 51 | -3.728 kHz/s | -3.658 kHz/s | -3.646 kHz/s | +0.052 kHz/s |
| H7 | -3.222 kHz/s | 590 | -3.218 kHz/s | -3.210 kHz/s | -3.230 kHz/s | -0.013 kHz/s |

On H7, all three central estimates remain near `-3.22 kHz/s`. Agreement with
the GLRT context is not an accuracy test, but it reinforces that the 500 ms fit
is stabilizing a local rate rather than selecting a different rate branch.

## Adaptive selector

The adaptive selector chose 500 ms for 1,012 of the 1,416 adaptive forecast
targets (71.5%), 250 ms for 174, 125 ms for 169, and 75 ms for 61. Outside H7
it usually collapsed to the fixed-500 result. H7 is therefore the useful
falsifier:

| H7 horizon | Median adaptive rate | Median paired delta from fixed 125 ms | Median absolute delta | Adaptive future RMS change from fixed 125 ms |
|---:|---:|---:|---:|---:|
| 125 ms | -3.228 kHz/s | 0 Hz/s | 118.99 Hz/s | +7.9% worse |
| 500 ms | -3.232 kHz/s | 0 Hz/s | 108.55 Hz/s | +28.0% worse |
| 1,000 ms | -3.292 kHz/s | 0 Hz/s | 111.42 Hz/s | -5.9% better |

The selector's near-zero median paired change is not evidence of a better
state. It often retained the 125 ms history, while occasional shorter-history
choices produced heavy tails and degraded the two shorter forecasts. The
present adaptive rule should remain rejected.

## Development-cohort cross-check

The earlier D1–D3 development cohort showed the same fixed-500 pattern more
uniformly. Fixed 500 ms improved every dwell at every forecast horizon:

| Development capture | Unique cutoff states | Median rate, 125 -> 500 ms | Median paired delta | Median absolute delta |
|---|---:|---:|---:|---:|
| D1 | 70 | -3,682.8 -> -3,706.2 Hz/s | +6.8 Hz/s | 110.4 Hz/s |
| D2 | 74 | -3,661.3 -> -3,642.7 Hz/s | +9.8 Hz/s | 66.8 Hz/s |
| D3 | 76 | -3,712.7 -> -3,630.6 Hz/s | +108.2 Hz/s | 341.2 Hz/s |

| Forecast horizon | Equal-dwell fixed 125 ms RMS | Equal-dwell fixed 500 ms RMS | Change | Adaptive RMS | Adaptive change |
|---:|---:|---:|---:|---:|---:|
| 125 ms | 55.75 Hz | 41.06 Hz | -26.3% | 69.01 Hz | +23.8% |
| 500 ms | 141.37 Hz | 74.47 Hz | -47.3% | 172.60 Hz | +22.1% |
| 1,000 ms | 233.99 Hz | 98.28 Hz | -58.0% | 368.30 Hz | +57.4% |

Across its nine dwell-by-horizon cells, fixed 500 ms changed an individual rate
by a median absolute `52–323 Hz/s` and reduced rate MAD by 41–95%. This agrees
with the H7 interpretation: longer history chiefly removes short-window rate
variation that does not predict future odd-Qin CFO.

## Scientific interpretation

The current evidence supports four bounded conclusions:

1. The promising change is fixed 500 ms history, not the adaptive selector.
2. On supported data, fixed 500 ms usually changes the central rate by tens of
   hertz per second, while changing individual causal states by a few hundred
   hertz per second.
3. The larger local changes matter for 0.5–1 second CFO prediction and are
   accompanied by lower withheld-response error, especially on H7.
4. The result remains conditional on the selected source/epoch/alias and does
   not establish physical Doppler acceleration or satellite identity.

A longer linear fit can also suppress real curvature or an abrupt physical
change. Reduced dispersion is therefore not, by itself, proof of lower
Doppler-rate bias. Promotion requires direct polynomial-phase injection truth
and new unseen captures with adequate source-bound support.

If a rate change were entirely propagation Doppler, the illustrative mapping
would be

```text
delta_acceleration_los = -(speed_of_light / carrier_frequency) * delta_rate
```

At 12 GHz, `0.25 kHz/s` would correspond to approximately `6.2 m/s^2`. That
conversion must not be applied as a measurement claim here: transmitter,
receiver, LNB, and sample-clock terms have not been separated from geometric
Doppler.

## Reproducibility

This report is a read-only derivation from the committed development and
holdout artifacts. The GLRT-context coefficients were read from the external
final-bank artifacts whose identities are pinned in the holdout configuration.
It did not reopen raw IQ.

- holdout outcome:
  `reports/2026_08_25_recent_adaptive_cfo_holdout.md`
- frozen holdout identities and final-bank pins:
  `config/analysis/recent-adaptive-cfo-holdout-v1.json`
- holdout diagnostic summary:
  `reports/figures/2026_08_25_recent_adaptive_cfo_holdout_diagnostic/diagnostic-summary.json`
- holdout forecast rows:
  `reports/figures/2026_08_25_recent_adaptive_cfo_holdout_diagnostic/diagnostic-forecast-rows.csv`
- holdout artifact closure:
  `reports/figures/2026_08_25_recent_adaptive_cfo_holdout_diagnostic/artifact-manifest.json`
- development outcome:
  `reports/2026_08_25_recent_adaptive_cfo_tracking.md`
- development summary:
  `reports/figures/2026_08_25_recent_adaptive_cfo_track/summary.json`
- development forecast rows:
  `reports/figures/2026_08_25_recent_adaptive_cfo_track/forecast-rows.csv`
- development artifact closure:
  `reports/figures/2026_08_25_recent_adaptive_cfo_track/artifact-manifest.json`

The underlying holdout result remains inconclusive, fixed 125 ms remains the
baseline, fixed 500 ms remains a shadow/research challenger, and the current
adaptive selector remains rejected.
