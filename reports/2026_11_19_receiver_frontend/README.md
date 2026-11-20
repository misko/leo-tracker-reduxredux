# Position error for each receiver modification

[All roof charts, counts and both calibration settings](figures/README.md) · [Original ten full-pipeline directions on 127 DS26 and eight DS29 recordings](../2026_11_18_pipeline_eval/figures/fitted_c/modifications.pdf) · [Geographic transfer and missing-region charts](transfer-figures/README.md)

The upper plots show the fraction of **all attempted recordings** with a returned position within the distance on the horizontal axis. A curve ending at 50% means the method published on half the recordings. The lower plots show each returned position and mark its median with a diamond. Each original v5 option is scored on exactly the recordings named on that page. DS26 and DS29 come from the same roof. The chart captions state whether inference started with raw samples, stored detections or prepared Doppler tracks.

| Modification | What was measured | Figure or evidence |
|---|---|---|
| Ordinary native fractional GLRT, then full v5 | Every eligible visit from six complete recordings with their capture-era clocks. Four recordings were added to the two earlier raw replays. | [Position chart](figures/fitted_c/native-to-v5.png) · [Individual errors](ordinary/position-errors.csv) · [Timing](ordinary/runtime.csv) |
| Fixed native winner gate | A stronger detector threshold selected on DS26-0036. All six complete candidate sets went through fresh v5 inference with the frozen rule. | [Position chart](figures/fitted_c/native_winner.png) · [Detector and position results](winner/README.md) |
| One physical receiver | Fresh single-input detection on every eligible window in two complete recordings, followed by full v5. The corresponding stored-factor experiment also compares two sources of detections. | [Complete IQ](figures/fitted_c/single_rx0.png) · [Stored-factor controls](figures/fitted_c/single_rx0_factors.png) · [Paired detector timings](single/README.md) |
| Late-pilot confirmation | A waveform check on 224 scheduled IQ visits from two recordings. Its difference in retention between archive-matched and native-only proposals fell below the preregistered threshold. Position was unmeasured. | [Matched v5 references](figures/fitted_c/pilot_confirmation.png) · [Test results](confirmation/README.md) |
| Sliding-tone pilot grid | All 16 scheduled visits reproduced the original detector outcomes, including two capture exclusions. Holdout detector CPU fell 23.4% on DS26 and 6.9% on DS29. The predeclared speed target was 25% on each. Position was unmeasured. | [Matched v5 references](figures/fitted_c/spectral_grid.png) · [Timing, bounds and candidate comparisons](spectral/README.md) |
| Longitude check before publishing | The original four-region offers are compared against rotated offers. The chart pairs the eight DS29 recordings with all four v5 options. The transfer book also scores physical sites, simulations and missing-region cases. | [Roof chart](figures/fitted_c/off_region_test.png) · [Transfer chart](transfer-figures/fitted_c/off_region_test.png) · [Fresh simulation](transfer-figures/fitted_c/fresh80.png) |

## Complete receiver measurements

The six-case geographic accuracy gate compares ordinary native GLRT plus the full numerical v5 solver with original no-repair v5 separately in each dataset and calibration arm. It requires matching the published and within-5-km counts, and at most 10% deterioration in median and P95 error. Each dataset has three recordings. A P95 calculated from three observations is sensitive to a single bad recording. [Predeclared criteria](PROTOCOL.md) · [Accuracy distributions](ordinary/distributions.csv)

| Three recordings per dataset | v5 median / P95, km | Ordinary native median / P95, km |
|---|---:|---:|
| DS26, fitted calibration | 0.747 / 1.162 | 0.821 / 1.211 |
| DS26, zero calibration | 0.751 / 1.226 | 0.896 / 1.218 |
| DS29, fitted calibration | 0.917 / 1.404 | 1.225 / 2.518 |
| DS29, zero calibration | 0.885 / 1.276 | 1.159 / 2.638 |

Both detectors returned positions within 5 km for all six recordings in both arms. Only the fitted DS26 arm met the full distribution criterion. Complete ordinary replays took 228–521 seconds on the host. One of six finished within the approximately 300-second recorded span. Several replays ran concurrently on distinct CPU pairs with shared storage. Those times include detecting, assembling and fitting each recording once. [Per-recording timing](ordinary/runtime.csv) · [Frequency-fit RMS, sample counts and position errors](ordinary/position-errors.csv)

The single-input detector kept all 54,669 retained RX0 candidates across 11,633 valid visits and took about 1.8× less detector CPU on the paired timing windows. Fitted position error on DS26-0036 went from 0.186 km with the ordinary dual detector to 6.008 km with one receiver. On DS29-0082 it went from 2.662 to 2.157 km. Complete single-input host replays took 356.95 and 224.58 seconds for roughly 300 seconds of recording. [Factor and position parity](single/README.md)

The geographic check kept the same eight StarLoc fixes, with 2.593 km median error. On historical synthetic missing-region queries it reduced false fixes from 6/40 to 2/40. On the independently generated fresh panel both the longitude check and its matched arc control published 32/40 present fixes, landed within 5 km on 21/40 and withheld on all 40 missing-region offers. Present-query median runtime on the original transfer panel rose from 1.05 to 14.75 seconds. [Sealed comparison](regions/README.md)

On the denser of the two original raw replays, the recorded visit count allows one detector core an average 44.34 ms per eligible visit before positioning. The earlier compact-v5 finish used 1,389,240 KiB peak RSS on the x86 host on DS26-0036. The archived Pluto+ had 506,568 KiB total RAM. The Cortex-A9 detector ran under QEMU on a matched IQ window. Physical timing and peak memory for the complete current 10 MS/s receiver remain unmeasured. [Embedded compute and memory measurements](embedded/README.md)

## Reproduce the figures

The first two commands use the saved predictions and require no radio hardware. To plot a single modification, add `--variant single_rx0`. The third command reruns a complete recording on the archive host and writes its scored result with both calibration arms.

```sh
.venv/bin/python -m tools.pipeline_eval figures --out /tmp/receiver-position-figures
.venv/bin/python -m tools.pipeline_eval figures --panel transfer124 --out /tmp/receiver-transfer-figures
.venv/bin/python -m tools.pipeline_eval full --case DS29-0174 --out /tmp/receiver-runs
```
