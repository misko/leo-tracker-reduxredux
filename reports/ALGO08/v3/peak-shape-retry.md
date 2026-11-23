# Short-peak shape gave negligible retry advantage on the weak cohort

The frozen peak-shape rule bought 11 retries on 34 weak positive radio lanes. Even granting a perfect replacement for each matched frequency it selected, discrepancy from the full receiver would fall to **50.70 Hz RMS**, compared with **50.77 Hz** for the square root of the expected mean squared error at the same uniform retry budget. Both start at 61.73 Hz on 30 matched lanes. This provides little reason to pay for the shape statistic on weak inputs. [Protocol](peak-shape-retry-protocol.md) · [Exact result](measurements/peak-shape-retry.json)

| Archived cohort | Paid / positive lanes | Matched / different among retries | Fraction of correctable squared discrepancy captured | Uniform expectation ± one random-selection SD | Best possible matched RMS / square root of uniform expected MSE |
|---|---:|---:|---:|---:|---:|
| Dense DS30-0008 | 9 / 35 | 8 / 1 | 30.27% | 25.71% ± 10.26 pp | 76.77 / 79.24 Hz |
| Weak DS26 clips | 11 / 34 | 8 / 3 | 32.54% | 32.35% ± 15.87 pp | 50.70 / 50.77 Hz |

The short receiver ranked signals using the smaller of two half-aperture log-power peak curvatures, each discounted by the relative height of its best separated competitor. The dense lower-quartile threshold of 0.07810 was set from short-side scores and applied unchanged on weak clips. The weak result exceeds the prespecified uniform expectation by 0.19 percentage points. Variation among equal-count selections dwarfs this difference on both cohorts. The standard deviations describe random selection on these fixed lanes. New recordings could have different signal conditions. Three of four weak different-signal lanes were selected, but replacing a detection with another carrier has unknown consequences for localization.

Neither aperture emitted a new measurement in this diagnostic. The prior split-spectrum instrumentation cost 1.34% / 2.26% additional native CPU per issued dense / weak lane, before external peak extraction. The estimate above grants zero overhead and perfect recovery. For the ongoing prototype it favors testing a genuinely cheap remeasurement of all short positives before depending on this selector for speed or accuracy. [Archived waveform study and cost](split-spectrum.md) · [Implementation](peak_shape_retry.py)
