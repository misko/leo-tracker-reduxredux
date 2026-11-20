# Standalone C acquisition through receiver position

The C detector processed two complete five-minute roof recordings from different capture producers. It retained every original passing candidate and passed fresh measurements to the compact receiver. Its fitted positions were 734 m and 516 m from the survey, both within 10% of every original v5 option that returned a fix. With zero calibration, removing a track gave v5 a much better fix on DS29. [DS26 fitted comparisons](portable-field/charts/fitted_c/portable-field-ds26-0020.png) · [DS29 fitted comparisons](portable-command/charts/fitted_c/portable-command-ds29-0082.png) · [All modifications, stage timings and point data](benchmark/index.html)

| Recording | Portable, zero / fitted | v5 no repair or selective gap | v5 omit one | v5 omit two | Full portable command |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0020 | 813 / 734 m | 818 / 739 m | 756 / 670 m | timed out | 330.83 s, eight host cores |
| DS29-0082 | 568 / 516 m | 567 / 517 m | 115 / 486 m | 115 / 486 m | 275.97 s, five host cores |

All 106 signed chunks completed on each recording. DS26 had 6,761 valid visits and three exclusions. DS29 had 4,868 valid visits and 1,904 exclusions. Every one of the 11,629 valid dual-antenna visits exceeded 20 ms of detector wall time. On DS26, matched to an earlier accelerated run on the same eight cores, detector CPU fell from 2,002 to 1,633 s, raw elapsed time from 282 to 267 s and full command time from 345 to 331 s. The DS29 historical run used a different CPU allocation. A full recording completed inside its recorded delivery span on that host. Physical embedded end-to-end throughput remains unmeasured. [DS26 clocks and parity](portable-field/README.md) · [DS29 clocks and parity](portable-command/README.md) · [Authenticated recording-locator smoke test](portable-command/LOCATOR-SMOKE.md)

The full raw paths retained 14,242 passing candidates on DS26 and 4,582 on DS29. One rejected DS26 coarse candidate changed across a near tie. Both DS29 candidate streams had 42,162 entries and matched in rank and decision under the recorded numerical tolerances. The compact positions computed from archived factors and fresh factors were within 0.08 mm of one another in all four arms. The RF-calibration fit lowered conditional frequency RMS by 0.0345 Hz on DS26 and 0.320 Hz on DS29, while survey error fell by 79.3 m and 52.3 m respectively. [DS26 scores](portable-field/scores.csv) · [DS29 scores](portable-command/scores.csv)

## Changes with measured costs

| Change | Comparison and outcome |
| --- | --- |
| C detector interface | On primary-pass, retry and reject visits, traced project Python fell from 1,018 lines in 66 functions to 150 in nine. Four numerical libraries became one. Compiled C source including headers grew from 826 to 1,803 lines. Maintaining both routes increases total source. [Footprint and exact counts](detector-footprint/README.md) |
| Compact fine-verification workspace | Across 12 visits from three producers, eight interleaved pairs reduced median dual-detector CPU from 365 to 336 ms and named workspace from 5.59 to 2.27 MiB, preserving all 224 ordered candidates per run. [Timings, memory and ARM numerical checks](verifier-memory/README.md) |
| Shared coarse phase sums | The candidate preserved ordered packets across 12 visits and reduced median paired whole-detector CPU by 3.98%. A sliding-window alternative increased it by 11.11%. [Timings and three-producer parity](coarse-tiles/README.md) |
| Faster catalogue parsing | Public parse CPU fell by 61% on each of two full causal catalogues, and all 66,981 propagated states matched. On three recording pairs, compact receiver preparation saved 1.15–2.89 CPU seconds with identical positions. Total elapsed and CPU times moved in both directions. [Public parser](catalog-checksum/repo-parser/README.md) · [Complete compact runs](catalog-checksum/README.md) |
| Eight samples for orbit screening | On six roof captures, the Lobatto rule kept all 756 original track shortlists, reduced orbit-time evaluations by 70.6%, and reproduced the native solver's positions. Fitted median error for that solver was 1.270 km against 0.889 km for v5. [Timing and both calibration distributions](track-quadrature/README.md) |
| Arrival-time buffering | The best four-worker modeled queue, with positions recomputed from its admitted data, gave 1.170 / 1.196 km at zero / fitted calibration on DS26, against 0.813 / 0.734 km with every valid visit. A short paced host replay recovered three of the five timely visit identities predicted by the model. [Queue measurements and positions](native-arrival/README.md) |
| Pilot cancellation | On 42 visits it recovered zero of 24 missed original winners. Twenty-two were outside the shortened timing search. Two injected secondary pilots were recoverable. [Waveform data and stage figure](pilot-cancellation/README.md) |

## Independent geographic evidence

At eight beacon sites in one metropolitan area, with each site held out of calibration, the correct area ranked first on 24/24 containing panels. The decision rule accepted four containing offers, falsely accepted one of 24 omissions, explicitly rejected 16 omissions and withheld the other seven omissions. It published zero field coordinates. The first placement design leaked a geometric cue. The reported results use a rerun with symmetric spherical placements. The same rule published a 46.7 m fix and rejected the omission at a separate simulated site. [Field and simulation results](site-region-sets/README.md)

On 11 measured captures from two visits to one Prague roof, pooling orbit phase and clock drift improved the training frequency fit. It released zero of two containing and zero of 16 omitted offers. Forced errors were 5.33 km and 4.08 km, against 4.41 km for the city-centre guess. These inputs use the authors' selected tracks and trajectories. A blind full wideband replay from a second physical receiving site remains outstanding. [Prague errors and held frequency scores](session-geometry/README.md)

The gallery includes both calibration views, each scheduled outcome and the measurements behind the figures. [Benchmark gallery and rebuild command](GALLERY.md) · [Receiver commands](../../../tools/pipeline_eval/README.md)
