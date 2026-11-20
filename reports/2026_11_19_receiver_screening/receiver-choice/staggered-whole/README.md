# Staggered fifth center on complete saved IQ

This receiver assigns fifth-center detection to one physical antenna and stock detection to the other on every valid visit. Each RF starts with fifth-center on RX0 and alternates on subsequent valid visits at that RF. Invalid acquisitions preserve their counter and reason without changing the rotation. The measured packets come from the whole raw IQ pass. [Protocol](PROTOCOL.md) · [Frozen source, capture and detector binding](source-lock.json)

The paired stock/fifth panel independently selected the two complete lower-edge recordings, DS26-0144 and DS29-0491. The staggered replay reads and authenticates each compressed chunk in chronological order. It uses CPU18 for the reader and first native antenna, CPU19 for the persistent second native antenna, and runs one recording at a time. It hands the actual emitted complete native document to the same installed phase-release solver as the homogeneous controls. The service allows 480 seconds, 512 MiB, and zero swap across both stages. The solver runs with one numerical thread and may schedule on either allowed core. Every accuracy comparison uses the matched causal catalogue and original offered tile. [Fresh paired controls](../fresh-panel/README.md)

The clock to native output begins once both IQ lanes are available. Whole-stage wall time includes decoder authentication, native assembly, and preparation of the position request. Recorded capture duration is approximately 300 seconds. The replay measures host throughput. The native-window study compares stock, fifth and staggered timing on fixed cores. The DS29-0174 study measures actual elapsed packet age in a separate arrival-paced replay. [Matched native workload](../staggered-native/README.md) · [Arrival-paced study](../equal-pace/README.md)

## Complete physical and native parity

The receiver processed all **13,528 valid dual-antenna visits** across both recordings and preserved all **18 acquisition exclusions**. Every one of the **27,056 emitted probe rows** matched its corresponding released stock or fifth-center row byte for byte, including every candidate field. Visit metadata, physical counters and delivery clocks also matched. On DS26, the mixed visit differed from stock at 3,519 visits and from all-fifth at 3,481. On DS29 the corresponding counts were 3,470 and 3,450. [Per-branch native SHA, antenna counts, and discrepancies](probe-parity.json) · [Native call records](visits.jsonl.gz)

## Native response

| Recording | Both decoded rows, p50 / p95 / p99 | Complete within 20 ms | Median process CPU | Median RX0 / RX1 thread CPU |
|---|---:|---:|---:|---:|
| DS26-0144 | 20.42 / 47.40 / 97.36 ms | 3,179 / 6,756 | 29.98 ms | 14.98 / 14.71 ms |
| DS29-0491 | 18.46 / 61.11 / 207.35 ms | 4,094 / 6,772 | 28.16 ms | 14.03 / 13.73 ms |

Together, **7,273/13,528 (53.8%)** of the complete native calls finished within 20 ms. The typed output boundary reached 20 ms on 3,312/6,756 DS26 visits and 4,201/6,772 DS29 visits. The fifth-center control measured on separate pinned serial-detector pipelines had median response of 33.22 ms on DS26 and 32.29 ms on DS29, with zero 20 ms calls on either. These complete captures use different host core layouts for the staggered and homogeneous controls. [Measured timing chart](staggered-whole-timing.png) · [Exact host clocks](timing.csv) · [Homogeneous timing rows](../fresh-panel/deadlines.csv)

| Recording | Raw plus handoff | Position stage | Raw through position | Cgroup CPU | Raw process peak RSS |
|---|---:|---:|---:|---:|---:|
| DS26-0144 | 229.57 s | 92.18 s | 321.75 s | 330.07 s | 270.2 MiB |
| DS29-0491 | 251.55 s | 96.71 s | 348.26 s | 323.52 s | 270.8 MiB |

Both whole-replay services reached a 512 MiB peak charge including file cache and completed with zero swap and zero OOM kills. The separate homogeneous controls split segments between two independent reader and detector processes. Their raw-to-position handoffs were approximately 118/155 s for stock/fifth on DS26 and 129/148 s on DS29. The observed per-visit native responsiveness and whole-recording throughput describe different execution boundaries. [Cgroup witnesses and service clocks](resources.json)

## Position and conditional RF fit

All three detector policies published on both recordings in both calibration arms. The staggered receiver had the smallest position error among the matched policies on both recordings and in both arms. All four original v5 options gave the same geographic error within each recording and calibration arm. DS26 uses the authenticated archive controls. The DS29 controls were executed separately on its authenticated capture-era factors. Two recordings at one roof establish the measured endpoints and have limited geographic coverage. [Zero-calibration position chart](charts/c0/staggered-whole.png) · [Fitted-calibration position chart](charts/fitted_c/staggered-whole.png) · [Per-arm position, RF and fit-score rows](position-scores.csv)

| Recording | Measured policy | Position error, zero / fitted | Conditional RF RMS, zero / fitted |
|---|---|---:|---:|
| DS26-0144 | Staggered | 0.018 / 0.050 km | 78.949 / 78.933 Hz |
| DS26-0144 | Stock four centers | 0.162 / 0.180 km | 67.840 / 67.787 Hz |
| DS26-0144 | Fifth on both antennas | 0.264 / 0.176 km | 78.918 / 78.897 Hz |
| DS26-0144 | Original v5 options | 0.192 / 0.229 km | |
| DS29-0491 | Staggered | 0.309 / 0.286 km | 103.768 / 103.755 Hz |
| DS29-0491 | Stock four centers | 1.501 / 1.443 km | 102.353 / 102.343 Hz |
| DS29-0491 | Fifth on both antennas | 0.751 / 0.694 km | 107.512 / 107.440 Hz |
| DS29-0491 | Original v5 options | 1.767 / 1.780 km | |

Stock had the lowest conditional RF RMS among the three matched detector policies on both recordings. Fitted calibration lowered the staggered conditional RF RMS by about 0.016 Hz on DS26 and 0.013 Hz on DS29. Geographic error increased by 32 m on DS26 and decreased by 23 m on DS29. The prediction seal preceded reference scoring. The figure seal binds all matched outcomes, both original reference inputs and the per-probe verification. [Prediction seal](prediction-lock.json) · [Figure seal](figure-lock.json)
