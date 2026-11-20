# Full-roof receiver comparison

On the exact **135-recording** roof panel, five-refresh compact v5 secant preserved aggregate original v5 accuracy and published all 135 fixes in both calibration arms. Among the native receivers, the smooth clock produced the lowest median error and fixed training published the most fixes. With fitted `c`, the smooth clock had a 1.284 km median with 119 fixes. Fixed training published 133 fixes with a 1.638 km median. Native fitted P95 errors ranged from 4.656 to 4.751 km.

## Matched position results

| Receiver | Calibration | Published | Within 2 km | Median / P95 error (km) | Within 5% / 10% of paired v5 | Median RF RMS (Hz) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Compact v5 secant | `c=0` | 135/135 | 116 | 0.977 / 2.936 | 129 / 131 | 71.2 |
| Compact v5 secant | fitted `c` | 135/135 | 114 | 0.989 / 2.817 | 129 / 131 | 71.0 |
| Native joint orbits | `c=0` | 119/135 | 77 | 1.759 / 4.695 | 33 / 34 | 182.6 |
| Native joint orbits | fitted `c` | 119/135 | 80 | 1.584 / 4.723 | 32 / 34 | 159.2 |
| Native training update | `c=0` | 133/135 | 76 | 1.853 / 4.559 | 34 / 35 | 184.6 |
| Native training update | fitted `c` | 133/135 | 85 | 1.638 / 4.656 | 37 / 37 | 162.0 |
| Native smooth clock | `c=0` | 119/135 | 80 | 1.530 / 4.463 | 37 / 40 | 151.7 |
| Native smooth clock | fitted `c` | 119/135 | 88 | 1.284 / 4.751 | 45 / 47 | 126.0 |

Median and P95 describe published fixes. Threshold counts use all 135 attempts and require a published coordinate. Each paired test compares the candidate’s geographic error with 1.05 or 1.10 times original no-repair v5’s error on that recording and arm. Original no-repair v5 had medians of 0.982 and 0.988 km, and P95s of 2.941 and 2.819 km. The other three original v5 options changed the aggregate median by less than 0.04 km, with the same P95s. The standard chart includes all four archived options for both datasets. [Per-recording errors](scores.csv) · [Distributions and paired counts](summary.json)

The two datasets behave differently. DS26 fitted smooth clock published 112/127 with a 1.397 km median, compared with compact’s 127/127 at 1.004 km. DS29 fitted smooth clock published 7/8 with a 0.714 km median, compared with compact’s 8/8 at 0.748 km. Among common fitted publications, the median distance between compact and each native position was 1.575 km for joint, 1.724 km for training and 1.267 km for smooth clock. Clock and joint differed by 0.737 km median across their 115 common fixes. Their identical overall 119 counts masked different withheld recordings. [Paired geographic distributions](summary.json)

RF RMS is conditional on each solver’s used observations and may be available even when it withholds. With fitted `c`, median paired native RMS fell by 22.2 Hz for joint, 23.3 Hz for training and 25.2 Hz for smooth clock. Geographic error improved on 72/119, 83/133 and 64/119 of their common within-method arm fixes. Compact’s median arm-to-arm position shift was 0.064 km. These frequency and geographic statistics have separate denominators and answer different questions. [Calibration ablation](summary.json)

## Measured work and provenance

| Receiver | Median full worker elapsed | Median full worker CPU | Peak RSS | Reported solver stage, median elapsed |
| --- | ---: | ---: | ---: | ---: |
| Compact v5 secant | 129.88 s, 121 fresh | — | — | 16.36 s cavity, 135 receipts |
| Native joint orbits | 5.36 s | 5.00 s | 150.0 MiB | 1.89 s joint backend |
| Native training update | 5.97 s | 5.47 s | 150.1 MiB | 2.26 s fixed-owner backend |
| Native smooth clock | 6.03 s | 5.68 s | 151.3 MiB | 2.45 s clock backend |

All four replays use complete archived native GLRT, the same causal catalogue and the same original region for each recording. Compact runs its full measured native preparation, initial five-refresh fitting, conservative recovery, family, signed and cavity stages. Its 121 fresh jobs finished in 36 min 44 s under a 38-minute batch cap, with at most 480 seconds per submitted job. Six prior timing and eight prior confirmation rows are authenticated separately. The three native paths reconstruct byte-identical anonymous Graph projections and apply their respective position fits under a 512 MiB virtual address-space cap. Worker CPU, RSS and elapsed times come from their separate recorded host runs. Archived RF acquisition and raw IQ detection are upstream of these measurements. [Compact receipt](../../secant-full/receipt.json) · [Native joint seal](../native-full/prediction-lock.json) · [Fixed training seal](../train-update/prediction-lock.json) · [Clock seal](../native-clock-full/prediction-lock.json)

The aggregator re-derived all 405 native roof request digests, checked each original region and archive digest, authenticated the compact source and prior results, and verified all 540 original v5 executions against their same-input request seals and frozen coordinates. SHA-256 links to each source archive, receipt and replay plan are in the source ledger. No receiver ran during the comparison. [Source ledger](sources.json) · [Figure seal](roof-lock.json)

## Reproduction

The optional archive audit reads the archived v5 execution JSON and their request receipts as well as the portable sealed results. The same summary and plot can be rebuilt without the option from the verified portable prediction and reference bundles.

```bash
scratch=$(mktemp -d /tmp/full-receiver-comparison.XXXXXX)
.venv/bin/python -B -m tools.pipeline_eval.qualification.full_receiver_comparison \
  --output "$scratch/evidence" --audit-original-executions
.venv/bin/python -B -m tools.pipeline_eval figures --panel screening \
  --evidence "$scratch/evidence" --out "$scratch/charts"
.venv/bin/python -B -m tools.pipeline_eval.qualification.gallery_check \
  "$scratch/charts" --expected-charts 1
```

[Chart definition](figures.json) · [Fitted `c` chart](charts/fitted_c/full-receiver-comparison-roof135.png) · [`c=0` chart](charts/c0/full-receiver-comparison-roof135.png) · [Both PDF and PNG sets](charts/index.html)
