# Constant-phase profiles across multiple dwells of one shared track

This repeats the per-window RX1-minus-RX0 phase enumeration across 12 frozen visits from one persisted shared RF track in `scan-hop-e46d3aba244cf641`. The track is channel 2 upper, target index 5, with 106 visits shared between the receiver-local tracklets over 44.3 seconds. Those tracklets contain 109 RX0 and 141 RX1 observations. Each of the 12 visits has exactly one retained phase-blind paired GLRT source in the prior raw-IQ replay.

This is strong operational evidence that RX0 and RX1 were following the same RF trajectory. It is not an independently established satellite catalogue identity. The 12 visits were selected by the earlier frozen phase-replay policy before this heatmap was examined, so phase appearance did not select the dwells.

![Twelve per-dwell phase heatmaps](figures/2026_09_22_multi_dwell_track_phase/multi-dwell-phase-heatmaps.png)

Each panel is a separately retuned 120 ms dwell. It uses 233 overlapping 2 ms windows at 0.5 ms stride. The color evaluates signed coherence at 721 candidate phase offsets; black points mark the most-likely phase. The dashed line separates the first 60 ms used by the per-dwell broadband alignment model from its second-half application.

The per-dwell correction estimates relative RX1 frequency/drift and fractional delay, then applies the same 1.675 MHz common-band filter to both receivers. It does not equalize the remaining frequency-dependent channel response. Positive phase is `arg(RX1 * conj(RX0))`. The phase intercepts are not connected across retunes.

## Results

| Visit | Track time | Median coherence | Median prediction error | Scalar-described energy | Linear residual frequency | Linear phase RMS | Median conditional phase SE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 376 | +0.0 s | 0.174 | 0.9847 | 3.04% | +2.5 Hz | 55.6° | 4.4° |
| 453 | +9.8 s | 0.161 | 0.9869 | 2.60% | +4.2 Hz | 41.1° | 4.3° |
| 486 | +14.0 s | 0.226 | 0.9741 | 5.12% | +19.5 Hz | 114.2° | 3.4° |
| 513 | +17.5 s | 0.215 | 0.9767 | 4.60% | +11.9 Hz | 114.3° | 3.5° |
| 537 | +20.5 s | 0.198 | 0.9801 | 3.94% | +3.6 Hz | 69.7° | 4.0° |
| 564 | +23.9 s | 0.224 | 0.9747 | 5.00% | −24.6 Hz | 108.9° | 3.8° |
| 588 | +27.0 s | 0.206 | 0.9785 | 4.25% | −2.4 Hz | 52.5° | 3.6° |
| 614 | +30.3 s | 0.191 | 0.9817 | 3.63% | +23.5 Hz | 112.3° | 4.2° |
| 638 | +33.3 s | 0.170 | 0.9854 | 2.90% | +16.9 Hz | 120.1° | 4.6° |
| 668 | +37.2 s | 0.143 | 0.9897 | 2.05% | +28.5 Hz | 115.8° | 5.3° |
| 697 | +40.9 s | 0.137 | 0.9906 | 1.87% | −5.3 Hz | 91.4° | 5.4° |
| 724 | +44.3 s | 0.093 | 0.9957 | 0.86% | −11.2 Hz | 106.6° | 7.7° |

`Scalar-described energy` is median coherence squared. It is the fraction of RX1 energy described by a single gain-and-phase-scaled RX0 waveform in a window, under this model. It is not total satellite signal power. `Linear residual frequency` is the slope of one unwrapped linear phase fit over the dwell. Its circular residual RMS is 41–120°, showing that this single-number slope is generally a poor description of the trajectory.

![Per-dwell metrics along the track](figures/2026_09_22_multi_dwell_track_phase/multi-dwell-summary.png)

The common component is strongest in the middle of the track: median coherence reaches 0.215–0.226 in visits 486, 513 and 564, then declines to 0.093 by visit 724. Every dwell shows a moving phase ridge. Several later halves exhibit rapid wraps even though coherence remains measurable. One constant phase per dwell, or one residual frequency over the whole dwell, is therefore inadequate.

The conditional local phase estimates are much tighter than the failure of a global line: median deletion-jackknife SE is 3.4–7.7°, while the phase trajectory itself changes by many cycles. That supports a locally tracked phase/frequency model, with uncertainty propagated per window. It does not support joining absolute phase between retunes; retuning and receiver/LNB terms leave an unknown intercept for every dwell.

## Comparison with the other phase approaches

![Four phase approaches on the same dwells](figures/2026_09_22_multi_dwell_track_phase/multi-method-phase-comparison.png)

The comparison retains four observables:

- black: rolling common-band scalar phase from the preceding heatmaps;
- blue square: one full-band cross-spectrum intercept at its declared reference time and frequency;
- red triangle: source-specific known-edge-pilot phase at its own center sample;
- green/purple: second-half phase tracked from A frequency groups and independently inferred from disjoint B groups, both in the fitted broadband-channel gauge.

The edge-pilot, broadband-intercept and common-band scalar methods have different waveform, timing, frequency and channel-response gauges. Their absolute vertical separation is not a calibrated phase error and cannot be removed by assuming a shared satellite. The GLRT itself is phase-blind and therefore contributes source/timing/frequency evidence rather than another phase point.

| Visit | Edge-pilot phase | Broadband intercept | A-tracked/B-held coherence | Wrong-time coherence | B residual phase |
|---:|---:|---:|---:|---:|---:|
| 376 | +143.6° ± 7.5° | +27.6° ± 1.0° | 0.170 | 0.009 | −2.8° |
| 453 | +128.2° ± 3.8° | −169.9° ± 1.2° | 0.161 | 0.006 | +3.7° |
| 486 | +67.4° ± 1.6° | −171.6° ± 0.9° | 0.227 | 0.009 | −1.3° |
| 513 | −165.2° ± 4.1° | +0.4° ± 1.5° | 0.210 | 0.010 | −4.6° |
| 537 | −16.5° ± 6.6° | +169.3° ± 1.7° | 0.191 | 0.013 | −3.3° |
| 564 | −144.0° ± 5.3° | −98.7° ± 0.9° | 0.224 | 0.013 | +1.6° |
| 588 | −17.4° ± 6.1° | +57.5° ± 1.0° | 0.199 | 0.004 | +3.3° |
| 614 | +159.9° ± 2.3° | +32.8° ± 1.2° | 0.191 | 0.007 | −0.4° |
| 638 | −111.9° ± 5.3° | +95.2° ± 1.2° | 0.168 | 0.002 | −3.8° |
| 668 | +162.0° ± 3.1° | +44.2° ± 1.5° | 0.154 | 0.008 | +1.0° |
| 697 | +47.9° ± 6.6° | −91.5° ± 1.6° | 0.131 | 0.005 | −0.1° |
| 724 | +37.3° ± 6.0° | +99.5° ± 22.3° | 0.036 | 0.111 | −54.2° |

For the first 11 visits, A-derived phase predicts the disjoint B bands with aggregate residual between −4.6° and +3.7°. Tracked coherence is 0.131–0.227, versus wrong-time controls of 0.002–0.013. This independently supports the moving broadband phase ridge. Visit 724 fails: tracked coherence 0.036 is below its 0.111 wrong-time control, its residual is −54.2°, and the broadband intercept uncertainty expands to 22.3°. It should remain unavailable for precise broadband phase interpretation despite its retained edge-pilot detection.

## Reproduction and artifacts

- [All 2,796 window estimates](figures/2026_09_22_multi_dwell_track_phase/multi-dwell-windows.csv).
- [Cross-method summary](figures/2026_09_22_multi_dwell_track_phase/multi-method-summary.csv).
- [Full models, source bindings and results](figures/2026_09_22_multi_dwell_track_phase/multi-dwell-results.json).
- [Reproduction script](figures/2026_09_22_multi_dwell_track_phase/plot_multi_dwell_phase.py).

The result binds the raw input manifest, shared-tracking manifest, two receiver-local tracklet IDs and raw-recording authority digest. The script verifies the frozen 12-visit selection, target index, paired-source count, track membership and manifest before reading IQ. A known-tone control verifies relative-frequency and fractional-delay correction signs. Saved IQ is read-only; no new RF was collected.

Run with the source and environment at research commit `660bd85a`:

```bash
sudo -u leo env OPENBLAS_NUM_THREADS=1 MPLCONFIGDIR=/tmp/leo-multi/mpl \
  PYTHONPATH=src:tools .venv/bin/python \
  /path/to/published/reports/figures/2026_09_22_multi_dwell_track_phase/plot_multi_dwell_phase.py \
  --research-root "$PWD" --bulk-root /srv/bulk/leo --output /tmp/leo-multi
```

The next useful estimator is a smooth local residual phase/frequency tracker inside each dwell, validated on disjoint frequency groups as before. Geometric interpretation still requires separating stable receiver/LNB/channel phase and respecting the lack of phase continuity across retunes.
