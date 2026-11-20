# Position error for each receiver modification

[Open the per-modification chart gallery](charts/index.html) · [Compare four full receivers on the same 135 recordings](full-receivers/charts/index.html) · [Open the original ten modifications](../../2026_11_19_position_atlas/original-ten.html)

Each roof chart uses the same recording IDs for the modification and the four original v5 options. Each dot is one position. The published-position curve divides by **every scheduled recording**, so its final height gives coverage. Rows labeled *forced* include the receiver’s best guesses even on recordings where it withheld a fix. A diamond marks each row’s median. Use the calibration switch to see the matched `c = 0` and fitted-`c` results. [Per-recording roof errors](charts/fitted_c/modifications.csv) · [Per-query location errors](charts/fitted_c/transfer.csv)

## Full roof recordings

Each receiver below started from the same stored GLRT detections, causal catalogue and 25 km region. DS26 contributes 127 recordings and DS29 contributes eight, all at one installation. The 5 km column counts successes among **all 135**. Median and P95 describe the fixes the receiver published. The complete comparison has separate results for all four original options. [Charts for both arms](full-receivers/charts/index.html) · [Checked input identities and original v5 executions](full-receivers/sources.json) · [Recording-level errors](full-receivers/scores.csv)

| Receiver | Published | Within 5 km, zero / fitted | Median / P95 at `c = 0`, km | Median / P95 at fitted `c`, km |
| --- | ---: | ---: | ---: | ---: |
| Original v5, no repair | 135/135 | 133 / 133 | 0.982 / 2.941 | 0.988 / 2.819 |
| Compact v5 secant | 135/135 | 133 / 133 | 0.977 / 2.936 | 0.989 / 2.817 |
| Native smooth clock | 119/135 | 114 / 115 | 1.530 / 4.463 | 1.284 / 4.751 |
| Native curve anchors | 108/135 | 103 / 104 | 1.800 / 4.810 | 1.579 / 4.530 |
| Native adaptive orbit phase | 90/135 | 87 / 86 | 1.600 / 4.317 | 1.383 / 4.063 |

Compact v5 stayed within 10% of the original no-repair error or did better on 131/135 recordings in each arm. A separate six-recording paired host study measured a 1.52-fold median speedup from native GLRT factors to the compact decision. Faster newly built receivers took median host wall times of 6.03 seconds for smooth clock, 3.55 seconds for anchors and 6.45 seconds for adaptive phase on their full-roof schedules. Original v5 retained higher coverage and smaller errors. Physical embedded timing and a matched wideband recording from a different installation remain open. [Timing boundaries and count of individual regressions](full-receivers/README.md) · [Paired solver timing](../../2026_11_19_receiver_convergence/position-fit/README.md)

## What changed from acquisition through position

| Change | Measured outcome | Plot or study |
| --- | --- | --- |
| Scout raw IQ using three pilot lags | Reduced detector CPU by 47% but retained 4/26 held positive detections. One downstream recording substituted eight IQ visits out of 6,765. | [Partial-IQ position chart](charts/fitted_c/differential_gate.png) · [Detector evidence](pilot-acquisition/README.md) |
| Stream orbital preparation and release each history snapshot after its last use | Exact preparation and both positions on the two measured ordinary-factor recordings. Preparation reached 479 and 485 MiB. The complete v5 workers still reached 1,354 and 1,270 MiB. | [Regional streaming](charts/fitted_c/prep_stream_sky.png) · [Snapshot release](charts/fitted_c/history_stream_prep.png) · [Memory and CPU](history-stream/README.md) |
| Replace dense Doppler noise matrices with a scalar filter | The compiled version cut stored filter bytes 6.48-fold on 18 roofs. Complete worker CPU increased by 27 ms at the paired median. All 21 decisions agreed. | [Scalar version](charts/fitted_c/innovation_noise-roof.png) · [Compiled version](charts/fitted_c/compiled_innovation-roof.png) · [Memory and tolerances](compiled-noise/README.md) |
| Cache fixed terms in satellite matching | Same decisions and positions within 12 micrometres in the repeated 10-query study. Matching CPU fell 8.2%, equivalent to about 0.08% of the complete worker. | [Roof plot](charts/fitted_c/cached_association-roof.png) · [Timing attribution](cached-association/README.md) |
| Allow one frequency offset per assigned Doppler track | All 144 pairs retained the same orbit assignments and aliases. On the 125 roofs outside the first offset study, 109 fell within 5 km versus 106 with zero offset. Among 105 shared fixes, median zero-calibration error improved from 1.759 to 1.590 km. The fitted median moved from 1.584 to 1.589 km. Both receivers withheld all nine historical omissions. | [Initial confirmations](charts/fitted_c/marginal_offset-confirmation.png) · [125 additional recordings](charts/fitted_c/marginal_full-unseen.png) · [All 135](charts/fitted_c/marginal_full-roof.png) · [Omitted regions](charts/fitted_c/marginal_full-omitted.png) |
| Find a satellite from anonymous Doppler curvature, then free its orbital phase | Recovered the diagnosed satellite at the top of the blind search, with one independent curved training track. The wider full-panel receiver published 90/135. | [Identification and position](charts/fitted_c/phase_capture-diagnosis.png) · [Full adaptive phase](charts/fitted_c/phase_support_roof.png) |
| Keep independent Doppler anchors | First two small panels gave eight fixes within 5 km out of eight. Full native replay gave 103/135 within 5 km at zero calibration and 104/135 fitted. | [Initial eight](anchor-receiver/README.md) · [Full replay](charts/fitted_c/native-anchor-full-roof.png) · [Near-edge offers](charts/fitted_c/native-anchor-near-edge.png) |
| Simplify the receiver clock, or add a clock to fixed anchors | The 12-parameter clock published 119/135 with a fitted median of 1.484 km. Adding the larger clock to anchors lowered RF RMS on all 134 completed fits but cost eight publications overall. | [12-parameter clock](charts/fitted_c/native_compact_clock-roof.png) · [Fixed-anchor clock](charts/fitted_c/native_anchor_clock-roof.png) |
| Use one blind Doppler seed in the compact v5 cavity fit | First seed returned no fixes on six recordings. Detrending the seed returned 6/6 in 37–48 seconds. Two recordings had large position regressions. Three confirmation recordings were selected by hash before the change. | [First seed](charts/fitted_c/bridge_cavity_center_profile.png) · [Confirmation](charts/fitted_c/bridge_cavity_confirmation.png) · [Individual errors and timings](bridge-cavity/README.md) |
| Package the native receiver as a standalone GLRT-to-position command | Five independent launches reproduced the scientific outputs, including withholding. Peak resident memory was 141 MiB. | [Capture-era joint](charts/fitted_c/portable_native_joint-capture-era.png) · [Ordinary factors](charts/fitted_c/portable_native_joint-ordinary.png) · [Smooth clock](charts/fitted_c/portable_native_clock-capture-era.png) · [Wrong region](charts/fitted_c/portable_native_clock-omitted-tile.png) · [Run the command](portable-worker/README.md) |

Two single-seed failures had different causes. On DS29-0082, the bridge changed two retained satellite identities. For one of them, 28 held observations predicted the original identity more accurately. On DS26-0066 the methods agreed on every shared identity, but the bridge lost 455 observations and missed a later v5 repair. Its frequency RMS improved by about 5 Hz while geographic error grew. [Per-track replay of the two regressions](bridge-cavity/diagnostic/README.md)

## Can the receiver tell that the correct region is missing?

The earlier nine omitted offers were at least 20 km outside the supplied tile. On ten measured recordings with new offers only 1–2 km or 6 km outside, smooth clock published **3/20** false fixes and fixed training published **5/20**. A new rule reran the position search on an expanded 50 km square centered on its first fix. On ten additional DS26 recordings it kept both false publications, at approximately 8.3 km error, and discarded four valid publications. The false pair came from two offers on the same recording. [New near-edge tests](charts/fitted_c/boundary-roof-primary-original-gates.png) · [Radius gate on six different recordings](charts/fitted_c/boundary-roof-reserve-containment.png) · [Independent recenter test](charts/fitted_c/native_recenter_verify-prospective.png)

Five simulated sites with causal orbits and measured receiver noise provide different Earth geometries. Smooth clock published one of five containing offers and zero of ten omitted offers. Fixed training published three of five containing offers and three of ten omitted offers. Its farthest false position was 44.6 km from the simulated site. These simulations start at GLRT factors. The 135 wideband roof recordings represent one physical site. [Simulated-site chart](charts/fitted_c/anonymous_native_region_challenge.png) · [Geometry, RF and location errors](region-challenge/README.md)

## Rebuild these charts

Run this from the repository root. It reads the saved predictions and writes one PNG per comparison and calibration setting, PDF books and a CSV of the points. Scoring and rendering these files work offline.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/refinement --out /tmp/receiver-refinement
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check /tmp/receiver-refinement
```
