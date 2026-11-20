# Receiver redesigns on the original roof and held locations

[Open the 28 position-error charts](charts/index.html) · [Open the original ten changes](../../2026_11_19_position_atlas/original-ten.html)

Each rooftop chart puts the modification and the original v5 options on the same recording IDs. The cumulative curves count every scheduled recording. The dots and median diamonds use only returned positions. A forced position is shown separately when the receiver saved one. A timeout has no returned position and gives no evidence that the receiver would have withheld. The independent location charts name their own controls and distinguish simulated locations from measured installations.

## How selecting only successful v5 runs changes the answer

The first comparison used 127 DS26 recordings where all four original configurations finished on both repeats, plus eight DS29 recordings at the same installation. The new DS26 panel includes all 159 in the original roster. One has no native detector archive. Both calibration settings retain it. [Per-recording originals and native replays](roof-selection/native/README.md)

| DS26 recordings | Original no repair | Selective gap | One omitted | Two omitted | Compact v5 secant | Native smooth clock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Common 127 | 127 | 127 | 127 | 127 | 127 | 112 |
| Other 32 | 16 | 14 | 11 | 5 | 22 | 23 |
| All 159 | 143 | 141 | 138 | 132 | 149 | 135 |

Compact v5 returned seven fixes on recordings where no-repair v5 had failed or timed out. It timed out on one recording where v5 had returned a fix. On all 159, the fitted median/P95 among returned positions were 1.014/3.541 km for compact v5 and 0.988/3.266 km for original v5. On just the 142 recordings where both published, these were 0.996/3.288 km and 0.994/3.304 km. Compact v5's error was at most 110% of the original on 138 of those 142 in each calibration setting. [All 159, fitted](charts/fitted_c/ds26_roof_completion-all159.png) · [All 159, zero calibration](charts/c0/ds26_roof_completion-all159.png) · [Excluded 32](charts/fitted_c/ds26_roof_completion-excluded32.png)

The first time budget allowed compact v5 to start 23 of the 31 eligible excluded recordings. An independently recorded follow-up started the other eight with the same 195-second worker cap. Six returned positions and two failed. The combined comparison preserves every outcome from the first run. [First time budget](charts/fitted_c/ds26_roof_completion-budget-all159.png) · [Additional eight](charts/fitted_c/compact_roof_completion.png) · [Attempt and score records](roof-selection/completion/README.md)

The calibration comparison keeps the observations, candidate sets, offered regions and search budgets fixed within each method. Across all eligible DS26 recordings with a measured frequency fit, the median fitted-minus-zero change in compact v5's conditional Doppler RMS was −0.014 Hz on 149 recordings. For the smooth clock it was −24.291 Hz on the fit and −8.070 Hz on held measurements across 158 recordings. The geographic distributions above use published positions. [Per-recording data](roof-selection/comparison/scores.csv) · [Paired scores and denominators](roof-selection/comparison/summary.json) · [Source receipts](roof-selection/comparison/source-audit.json)

The smooth clock recovered ten of the 32 recordings where original no-repair v5 gave no position and lost three that v5 solved. On the full panel, its fitted-calibration median and P95 were 1.413 and 4.780 km. Among 125 paired fixes its error was at most 110% of v5 on 48 recordings with fitted calibration and on 40 with zero calibration. The fitted radio residual on the excluded recordings fell by a median 25.1 Hz. Fitting the calibration term improved the position on 16 of the 23 published recordings. [Full distribution](charts/fitted_c/ds26_selection_native_clock-all159.png) · [Excluded recordings](charts/fitted_c/ds26_selection_native_clock-excluded32.png) · [Calibration analysis](roof-selection/native/README.md)

## What changed along the pipeline

| Change | Positions and cost on its measured inputs |
| --- | --- |
| Reuse interpolation weights across four detector outputs | On 15 held saved-IQ visits the detector emitted identical candidates. The host's fractional-delay stage used 4.44% less CPU and the complete detector used 0.32% more. Replacing the measured visits in the two original recordings preserved the DS26 fix and the DS29 withholding decision. [Chart and timings](ordinary-front/README.md) |
| Reuse native detections and orbit states across acquisition cutoffs | Both implementations matched on all 32 checkpoints across eight inputs. Median worker CPU fell from 7.35 to 5.41 s and peak RSS rose from 138 to 171 MiB. They published the same six correct-offer fixes and both false fixes when the true region was just outside. [Measurements](prefix-reuse/README.md) |
| Fit a probability distribution over satellite identities | All ten roof queries published and all three wrong offers withheld. On seven shared reserve fixes, fitted-calibration error increased by a paired median 735 m against the exact joint receiver. All three wrong offers passed the held-track check and were stopped by the tile-edge check. [Distributions](soft-identity/README.md) |
| Predict signed orbit timing from preceding catalogues | On 3,065 held satellite/date pairs, the timing proxy's RMS increased from 5.350 to 5.946 s. Roof coverage dropped from four of six to two of six in each calibration arm. Both authentic omitted offers withheld. [Catalogue and geographic results](phase-forecast/README.md) |
| Use a simpler initial satellite assignment ahead of compact v5 | On 24 reserve recordings this returned 20 positions, with three timeouts and one failed fit. Fitted median/P95 were 0.860/3.471 km versus 0.748/2.496 km for compact v5, which returned all 24. On one recording the radio fit improved while position error rose from 0.296 to 8.452 km. [Per-recording errors](bridge-reserve/README.md) |
| Skip the final repair only when its frozen guard allows it | On the one completed same-core pair, both fitted positions and both radio residuals were identical. The complete worker used 117.56 s CPU versus 156.63 s. The other two planned recordings lacked a completed pair within the time cap. [Attempts and timing](late-cost/README.md) |
| Check how strongly any one satellite controls a fix | Across 52 wrong offers the whole-orbit deletion check reduced false fixes from seven to one. Across 52 correct offers, publications also fell from 35 to 19. On a separate 12-plus-12 offer reserve, it removed the only false publication and four of eight correct publications. [Errors and withholding](orbit-influence/README.md) |
| Keep discovery residuals only for satellites that need them | The unrestricted ordinary DS29 worker kept the same position and radio results. Its peak RSS fell from 882,412 to 828,212 KiB. Under a 512 MiB no-swap limit the worker passed discovery, then stopped in family confidence. [Hard-cap trial](discovery-memory/README.md) |
| Compute family timing widths from the three required epochs | On ordinary DS29 the confidence stage used 0.672 s CPU versus 3.376 s. All 145 radio profiles, their ranks and both positions were identical. A later allocation still took the full worker above the memory limit. [Allocation trace and endpoint charts](family-memory/README.md) |
| Combine sparse discovery and the three-epoch family lookup | Both unrestricted positions matched the original on ordinary DS29. A 512 MiB no-swap run finished family confidence and then stopped before family nomination. [Paired outcomes](compact-memory-combined/README.md) |
| Reuse the sampled widths in the signed orbit-timing check | The complete unrestricted DS29 worker again produced identical positions and radio fits. Peak RSS fell from 817,572 to 582,508 KiB. Under 512 MiB it completed the signed check, then ran out of memory during family nomination. [Position and memory receipts](signed-context-memory/README.md) |
| Run the same compact secant solver on new site geometries | The two simulated sites are 17,066 km apart. Fitted errors were 1.272 and 0.833 km. Both wrong-tile runs and the shifted-tile trial on measured DS26 data timed out in recovery. [Containing and omitted distributions](compact-transfer/README.md) |

The host timing measurements use the boundaries named in each row. Cortex-A9 detector results use emulation. The complete memory-cap tests use a host worker with swap disabled and a real memory limit. DS26 and DS29 still represent one physical rooftop.

## Rebuild the figures

Run this from the repository root. The saved position and recording receipts are sufficient for both calibration settings.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/redesign --out /tmp/receiver-redesign
```
