# Smaller Doppler grid on eight complete roof recordings

**Keep the 21-bin grid.** The reduced grid met the 20 ms detector deadline on **24,515/52,081** visits, down from **24,736/52,081**. It also reduced the number of zero-calibration fixes within 10% of original v5 from **4/8 to 3/8**. With fitted calibration the count stayed **4/8**. Both branches returned all eight positions in both calibration arms. [Protocol](PROTOCOL.md) · [Audit and per-recording scores](audit.json)

| Position distribution | Zero calibration | Fitted calibration |
| --- | --- | --- |
| All eight recordings | [PNG](charts/c0/wide-cfo-stride-all.png) | [PNG](charts/fitted_c/wide-cfo-stride-all.png) |
| Two additional waveforms | [PNG](charts/c0/wide-cfo-stride-additional.png) | [PNG](charts/fitted_c/wide-cfo-stride-additional.png) |

Each chart shows both detector branches and all four original v5 choices. The two additional waveforms were selected by first-segment manifest SHA-256 before replay. They are independent of the previous waveform cohort and come from the same physical roof. [Interactive comparison](charts/index.html) · [Zero-calibration PDF](charts/c0/modifications.pdf) · [Fitted-calibration PDF](charts/fitted_c/modifications.pdf) · [Selection receipt](selection.json)

## Detector deadline and complete service

Both detectors replayed all valid dual-RX visits from saved I/Q, using four proposed pilot starts, the full ±800 kHz range and the same fine, fractional and compact position code. The candidate tests 11 evenly spaced bins and restores the skipped neighbors of the strongest bin in each time region. The maximum coarse cell count falls from 252 to 156 per receiver. The prior bounded detector trace measured a 39% cell reduction and higher coarse CPU with the repair loop. [Detector-stage study](../cfo-stride/README.md)

| Recording cohort | Valid visits per detector | 21 bins, wall ≤20 ms | Reduced grid, wall ≤20 ms | Mean detector CPU, 21 bins → reduced |
| --- | ---: | ---: | ---: | ---: |
| All eight | 52,081 | 24,736 (47.50%) | 24,515 (47.07%) | 20.32 → 20.59 ms |
| Six previous waveforms | 38,641 | 18,766 (48.56%) | 19,125 (49.49%) | 20.18 → 20.46 ms |
| Two additional waveforms | 13,440 | 5,970 (44.42%) | 5,390 (40.10%) | 20.72 → 20.95 ms |

All 16 detector stages completed. The aggregate gate-positive count fell from 161,486 to 160,714. It counts candidates on both receivers. On eight completed service pairs, the reduced grid took 3.59 s less median paired wall time and 0.94 s less median paired cgroup CPU, with shorter wall time on six pairs and lower CPU on four. The raw-stage median paired change was −3.64 s and the fit-stage change was −0.51 s. Full service includes reading, assembling and fitting. The 20 ms counts time the individual dual-RX detector calls. These measurements use the Intel Core Ultra 9 285K host and local ext4 scratch, with two pinned cores per pair. Every service reached 512 MiB peak cgroup charged memory with zero swap and returned within the registered 360 s deadline. [Service receipts](resources.json)

## Geographic error against original no-repair v5

Within 5% and 10% means the returned error is at most 1.05 or 1.10 times the original no-repair v5 error for the same recording and calibration arm. Both arms use the same inputs and solver budget within each detector branch. All scheduled recordings remain in the denominator.

| Panel and calibration | Returned, 21 bins → reduced | Within 5%, 21 bins → reduced | Within 10%, 21 bins → reduced |
| --- | ---: | ---: | ---: |
| All eight, zero | 8/8 → 8/8 | 3/8 → 3/8 | 4/8 → 3/8 |
| All eight, fitted | 8/8 → 8/8 | 4/8 → 4/8 | 4/8 → 4/8 |
| Two additional, zero | 2/2 → 2/2 | 0/2 → 0/2 | 0/2 → 0/2 |
| Two additional, fitted | 2/2 → 2/2 | 1/2 → 1/2 | 1/2 → 1/2 |

| Recording | Original v5, zero / fitted (km) | 21 bins, zero / fitted (km) | Reduced, zero / fitted (km) | Service wall, 21 bins / reduced (s) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 1.278 / 1.208 | 1.003 / 0.935 | 0.676 / 0.618 | 190.3 / 136.5 |
| DS26-0122 | 0.751 / 0.747 | 1.320 / 1.318 | 1.296 / 1.294 | 136.7 / 137.0 |
| DS26-0162, additional | 0.399 / 0.415 | 0.682 / 0.670 | 0.685 / 0.672 | 192.5 / 205.0 |
| DS26-0237 | 0.362 / 0.271 | 0.382 / 0.323 | 0.466 / 0.436 | 133.1 / 132.3 |
| DS29-0082 | 0.567 / 0.517 | 2.489 / 2.346 | 2.952 / 3.009 | 142.6 / 141.4 |
| DS29-0174 | 0.885 / 0.917 | 0.793 / 0.806 | 0.822 / 0.837 | 200.5 / 194.6 |
| DS29-0247 | 1.320 / 1.458 | 1.326 / 1.338 | 1.299 / 1.314 | 208.4 / 198.4 |
| DS29-0519, additional | 0.248 / 0.319 | 0.334 / 0.324 | 0.334 / 0.325 | 271.0 / 241.2 |

The reduced grid lost its zero-calibration pass on DS26-0237. Across all eight, its median position error fell from 0.898 to 0.753 km with zero calibration and from 0.871 to 0.755 km with fitted calibration. The 95th percentiles rose from 2.082 to 2.373 km and from 1.993 to 2.416 km. The median paired error change was +0.9 m and +2.0 m. The adoption rule required both a better matched 20 ms deadline fraction and retention of the within-10% count in each arm, including the two additional recordings as their own panel. The reduced grid failed the deadline and overall zero-calibration conditions. [Exact threshold flags, timing and scores](scores.csv)

## Conditional Doppler fit

Median conditional RF RMS with zero calibration was 85.48 Hz for 21 bins and 85.47 Hz for the reduced grid. With fitted calibration it was 85.50 Hz and 85.46 Hz. The reduced grid had lower conditional RMS on four of eight recordings in each arm. Its conditional frequency objective was lower on three of eight in each arm. These values describe the models fitted to the observations selected by each detector. Geographic errors use the surveyed position independently. [RF and geographic scores](scores.csv)

## Historical control verification

The 21-bin control re-created the six overlapping primary scout-full native factor files byte-for-byte. The audit checked the same waveform authority, acquisition clocks, invalid-visit exclusions, receiver order and candidate payloads, causal TLE request and offered tile. The five available primary position-arm payloads reproduced exactly. In the sixth case, DS29-0082, the primary control timed out after completing detection. This study reproduced its complete primary native factors and matched both position arms of the separate deadline repeat exactly. The two additional waveforms have no historical waveform control in this comparison. [Primary comparison](../../acquisition-support/scout-full/README.md) · [Separate repeat](../../acquisition-support/deadline-repeat/README.md)

The prediction seal binds all 16 first-attempt results and native factor archives. The audit reproduces from those sealed products and the earlier published controls. [Prediction seal](prediction-lock.json) · [Execution freeze](source-lock.json) · [Reproducible chart specification](figures.json)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.full_stride_audit
```
