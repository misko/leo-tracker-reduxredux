# Position error, processing time and memory from GLRT to a receiver fix

[Browse the 24 paired charts](charts/index.html) · [Original ten modifications](../../2026_11_19_position_atlas/original-ten.html) · [All 159 DS26 recordings](../redesign/charts/fitted_c/ds26_roof_completion-all159.png)

Compact v5 is the closest measured replacement for the original five-minute roof receiver. Across the 142 DS26 recordings both methods solved, their median and 95th-percentile position errors agree within 1% in both calibration settings. Across four fresh timing pairs, compact v5 ran 3.65× faster at the median on the same host core. A separate change to the order of satellite-state reads completed one entire post-GLRT solve under a real 512 MiB limit with zero swap. [Full-roster scores](../redesign/roof-selection/comparison/scores.csv) · [Same-core timings](same-core-baseline/README.md) · [Memory-limited solve](recovery-reads/README.md)

## Accuracy depends on which recordings count

| Panel and solver | Fixes | Zero calibration median / P95 (km) | Fitted calibration median / P95 (km) |
| --- | ---: | ---: | ---: |
| All DS26, original v5 without repair | 143/159 | 0.980 / 3.155 | 0.988 / 3.266 |
| All DS26, compact v5 | 149/159 | 0.990 / 3.545 | 1.014 / 3.541 |
| Same published fixes, original v5 without repair | 142/142 | 0.982 / 3.173 | 0.994 / 3.304 |
| Same published fixes, compact v5 | 142/142 | 0.980 / 3.159 | 0.996 / 3.288 |
| All DS26, smooth clock | 135/159 | 1.579 / 4.474 | 1.413 / 4.780 |

Compact stayed within 110% of original v5 error on 138 of the 142 paired fixes in each arm. Over each method's own published fixes, compact's P95 rose 8.4% with fitted calibration and 12.3% with zero calibration. It gained seven publications and lost one. The full distribution retains all 159 recordings in the denominator. The DS26 and DS29 captures share the same physical installation. [Matched and all-recording distributions](../redesign/README.md) · [All four original v5 options](../redesign/roof-selection/comparison/scores.csv)

## Which changes earned their cost

| Change | What the paired test established |
| --- | --- |
| Share three initial branches across calibration arms, publish after the cavity fit | Four same-core recordings covered both datasets and two runtime strata. Compact made 15 initial orbital refreshes versus 30 for original v5. The median speedup was 2.34× through the common numerical stages, 3.42× through each method's position decision and 3.65× through usable output including original reporting. The eight pairs of coordinates were 3.6–11.6 m apart. [Times and position charts](same-core-baseline/README.md) |
| Keep only the fine-frequency FFT bins the GLRT detector reads | Candidate fields matched on all 12 eligible stored-IQ visits. Total detector CPU fell 5.73% on x86 and 0.96% in Cortex-A9 emulation. Both versions missed the 20 ms host dual-receiver target on all 58 timed calls. Downstream substitution used the measured visits and retained ordinary factors elsewhere. [Detector, controls and position replay](ordinary-glrt/README.md) |
| Reorder orbit recovery for a 512 MiB budget | Tiling the coarse family scores alone reached the first scratch write and ran out of memory. Evicting the written pages got farther but hit the 180 s limit. Holding 128 orbit rows while testing all phases finished DS29-0082 in 93.55 s with zero swap. Physical reads were 3.22 GB on the complete capped run versus 34.13 GB already read by the interrupted control. Both positions and conditional residuals reproduced the unrestricted control exactly. [Family scoring](nomination-memory/README.md) · [Page eviction](recovery-cache-memory/README.md) · [Row-major reads](recovery-reads/README.md) |
| Propagate the actual states requested at the time-grid edges | Four previously failed recordings reached normal selection. Three returned fitted-calibration errors of 0.651, 1.508 and 0.743 km, and one withheld. All four unchanged control recordings reproduced both coordinates and RF residuals exactly. [Per-recording evidence](orbit-domain/README.md) |
| Use the missing-history rule for an older orbit that predicts decay | The same older element failed on two recordings. The current elements remained valid. Both recordings recovered fixes, with fitted errors of 2.608 and 0.326 km. Two unaffected controls matched exactly. This was tested independently of the grid-edge repair. [Exact inputs and outcomes](previous-orbit/README.md) |
| Continue after a single optional calibration fit fails | On the two diagnosed recordings, 19/22 and 4/16 family fits failed. The remainder gave no qualifying replacement, and the solver withheld on both. Four control recordings retained their fixes. [Rejections, comparisons and curves](optional-cavity/README.md) |
| Decode time-ordered GLRT peaks directly against causal orbits | Six of eight matched roof offers published and five landed within 5 km in each arm. Folded Doppler achieved one within 5 km and original v5 achieved eight. Both omitted offers withheld. The first implementation produced zero usable paths. [First attempt, revised decoder and controls](peak-paths/README.md) |
| Fit one timing displacement per candidate satellite across track fragments | On eight new recordings the simpler model published three fixes versus seven for each control. It also published on one of three incorrect offers. Backend CPU medians were 1.11 s for the new model and 1.18–1.24 s for its controls. [Matched error, held Doppler and runtime](shared-orbit-fit/README.md) |
| Check support before expensive recovery, then check the tile edge before publishing | At one new simulated site, the early check rejected a wrong region whose unguarded estimate missed by 75 km, but still published on a near miss. At a second simulated site the terminal check preserved both valid offers and withheld the false fix 1.63 km outside. This second test contains one independent inside/outside pair. [Early recovery check](transfer-budget/README.md) · [Independent edge test](transfer-budget/interior-guard/README.md) |
| Give compact v5 a deadline and reserve time for smooth clock | In the 159-recording timing model, 180 seconds yielded 151 fixes with fitted P95 of 4.233 km, compared with 149 fixes and 3.541 km for compact alone. Three real pinned launches exercised completion, timeout and numerical failure. [Full-roster model](deadline-roof/README.md) · [Three live executions](deadline-live/README.md) |

The timing comparison starts from saved GLRT detections. Its original production path also wrote eight PNGs per recording. The detector has a separate saved-IQ timing measurement, and the 512 MiB result uses an x86 Linux host. Physical embedded throughput and independent measured multi-satellite sites remain open. Errors above use surveyed roof coordinates or sealed simulation truth. The linked studies report conditional Doppler residuals separately for the observations consumed by each receiver.

## Regenerate the charts

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/deployment \
  --out /tmp/receiver-deployment
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check \
  /tmp/receiver-deployment --expected-charts 24
```

The gallery includes a full-resolution PNG per chart and calibration arm, printable PDFs and the CSV rows behind the figures. The cumulative curves count each attempted recording or offered region in the indicated panel. Dots and median diamonds describe the returned positions. Each page identifies its measured roster and input conditions.
