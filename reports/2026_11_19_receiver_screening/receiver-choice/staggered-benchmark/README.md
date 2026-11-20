# Position accuracy when one antenna gets the fifth timing search

The receiver searches four pilot-timing regions on both antennas. Each time it returns to an RF centre, it alternates which antenna gets a fifth search. This choice needs one bit of state per RF centre and uses only the order of valid radio visits. On two new, complete lower-edge recordings it produced the smallest position error of the receivers tested, **50 m** on DS26-0144 and **286 m** on DS29-0491 with fitted calibration. [Two-recording error distribution](charts/fitted_c/staggered-benchmark-fresh.png) · [Direct packet verification](direct-parity.csv)

## Across the 22 recordings

Twenty earlier recordings had both complete detector streams available. We selected the specified measured antenna outputs and ran the position solver again. On the two new recordings the receiver started from the actual saved I/Q. All 22 recordings share a single surveyed roof. Every row below returned all 22 fixes in both calibration settings. Threshold counts compare each recording against its own original no-repair v5 error, and include recordings with smaller errors.

| Receiver | Median km, zero / fitted | P95 km, zero / fitted | Within +5%, zero / fitted | Within +10%, zero / fitted |
| --- | ---: | ---: | ---: | ---: |
| v5 no repair or selective gap | 0.739 / 0.724 | 1.760 / 1.769 | 22 / 22 | 22 / 22 |
| v5 one or two omitted tracks | 0.703 / 0.695 | 1.760 / 1.769 | 22 / 22 | 22 / 22 |
| Four timing regions | 0.774 / 0.776 | 1.543 / 1.437 | 12 / 13 | 13 / 13 |
| Five timing regions | 0.742 / 0.782 | 1.556 / 1.522 | 13 / 13 | 13 / 14 |
| Alternating fifth antenna | **0.668 / 0.649** | **1.355 / 1.388** | 12 / 12 | 12 / 12 |

Alternating lowered the fitted median by 127 m relative to four regions. The median of the 22 individual changes was an 18 m improvement. The largest improvement was 1.16 km, and the largest worsening was 0.99 km. On the twenty reconstructed recordings alone the staggered fitted median was 0.681 km, with 10/20 within the 10% allowance. [All-recording fitted distribution](charts/fitted_c/staggered-benchmark-all.png) · [Zero calibration](charts/c0/staggered-benchmark-all.png) · [Earlier twenty](charts/fitted_c/staggered-benchmark-reconstructed.png) · [Per-recording comparisons](paired-errors.csv)

Six earlier recordings were outside the allowance with both fixed detectors under both calibration settings. Alternating still missed all six. Across the full 22, selecting the closer of the two fixed positions using survey truth would pass 15 recordings at zero calibration and 16 with fitted calibration. After the experiment we also computed the smallest error anywhere on the short great-circle arc joining the two fixed estimates. Even that truth-assisted bound misses all six difficult recordings under both settings. With fitted calibration just 16/22 can meet the allowance anywhere on that arc. [Earlier difficult recordings](charts/fitted_c/staggered-benchmark-difficult.png) · [Counts and upper bounds](choice-counts.csv) · [Survey-based arc calculation for each case](fixed-endpoint-geometry.csv)

Fitting calibration on the staggered stream lowered its conditional Doppler RMS by a paired median 0.013 Hz and increased its position error by a paired median 0.9 m. The new receiver's two raw-I/Q fixes had lower geographic error than both fixed branches, while four regions had the lowest conditional RF RMS on both. [Calibration effects](calibration-effects.csv) · [Coordinates scored and conditional frequency results](scores.csv)

## Runtime boundaries

All 27,056 antenna outputs across the two fresh recordings matched the assigned four- or five-region branch. The alternating implementation finished 7,273 of 13,528 complete detector calls within 20 ms. Its two complete host replays took 321.7 and 348.3 s through position. The fixed-four runs took 202.6 and 263.0 s, and fixed-five took 279.0 and 286.2 s. The fixed and alternating services used different core assignments and execution layouts. The twenty reconstructed runs contribute only a measured position-worker clock for the alternating method. [Time and scope per run](timing.csv) · [Held same-core detector measurement](../staggered-native/README.md) · [Direct complete replays](../staggered-whole/README.md)

## Rebuild

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver staggered --out /tmp/staggered-benchmark
```

The command reads frozen results and regenerates four distributions in both calibration settings, the four original reference options, all 132 method/recording/calibration rows, the raw per-lane comparison, timing, and the geometric diagnostics. It checks the original request, causal catalogue, region and native measurement identities. [Protocol](PROTOCOL.md) · [Recording groups](roster.json) · [Input checksums](inputs.json)
