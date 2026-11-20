# One physical antenna per valid RF visit

Run the stock four-center wide GLRT on one antenna at a time. Each recorded RF center starts on RX0 and alternates on valid visits. A capture-invalid visit consumes no turn. The unmeasured antenna keeps its original physical ID and geometry with an empty candidate array. The complete RF revisit and clock sequence is unchanged. This trial uses the installed stock library with a true one-receiver native context on the contiguous samples from the selected lane. Both IQ streams were read from the saved stereo archive throughout the replay. [Protocol](PROTOCOL.md) · [Frozen inputs, native release and dispatch schedules](source-lock.json)

The diagnostic case was DS29-0082. DS26-0014 had the smallest first-segment manifest SHA-256 among five earlier prospectively selected DS26 recordings. Both are from one roof. The measured runs used the same truth-free requests, original 25 km offers, causal catalogues and installed compact phase release as the published four-center controls. [Complete prediction and resource seal](prediction-lock.json)

## Whole-IQ coverage and projection proof

Both direct runs returned both position arms. Each recording contained 6,772 scheduled visits. DS26 had 6,772 valid visits. DS29 had 4,868 valid and 1,904 originally invalid visits. Every valid visit ran one native antenna call. No valid call was dropped and no invalid capture was filled. RX0/RX1 ran 3,388/3,384 calls on DS26 and 2,436/2,432 on DS29. Each of the eight recorded RF centers saw both antennas, with their counts differing by at most one. [Physical support and digest audit](parity.json) · [Per-visit detector and clock receipts](visits.jsonl.gz)

Every one of the 11,640 measured selected-lane candidate arrays matched the corresponding published four-center array. All 11,640 partner arrays were empty as directed. The projected and directly measured complete native documents had identical bytes and SHA-256 on both recordings. The stock two-antenna streams contained 3,925 and 2,063 probes with a passing candidate. One antenna delivered 1,990 and 1,037 on DS26 and DS29 respectively. These proofs qualify use of the projection on the measured boundary and provide direct checks for the separate expanded-roster analysis. [One-lane native DS26](native/DS26-0014.json.gz) · [One-lane native DS29](native/DS29-0082.json.gz)

## Measured detector work

The direct services had a 450-second runtime cap, 512 MiB charged memory and zero swap. Their individual capture spans were 299.9973 and 299.9971 s. The archived stock runs used the same two independent chronological segment workers and four-region detector, under a 360-second cap and different CPU pairs and host load. The comparison shows actual measured time at each boundary. Both candidate runs peaked at the charged 512 MiB limit. [Complete timing and headroom](deadlines.csv) · [Authentic historical stock timings](stock-runtime.json)

| Recording and branch | Cores | Wall ≤20 ms | P95 detector wall | Detector CPU | Whole pipeline wall / CPU | Service wall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0014 stock four | 20/21 | 6,382 of 6,772 | 20.20 ms | 113.94 s | 149.73 / 177.71 s | — |
| DS26-0014 one antenna | 12/13 | 6,428 of 6,772 | 20.10 ms | 90.84 s | 140.40 / 162.91 s | 148.91 s |
| DS29-0082 stock four | 18/19 | 38 of 4,868 | 35.05 ms | 126.01 s | 142.59 / 207.94 s | 142.80 s |
| DS29-0082 one antenna | 14/15 | 4,518 of 4,868 | 25.43 ms | 64.88 s | 134.06 / 131.55 s | 135.61 s |

The one-antenna services ran half as many receiver analyses, with 20.3% and 48.5% less measured detector CPU than the archived stock runs. The archived DS26 service has 149.90 s supervisor elapsed time. Its systemd lifetime is unavailable. A separate stage experiment timed the same deployed detector on identical saved inputs and found x86 median detector CPU of 16.10 ms for two antennas and 8.02 ms for one. The whole-recording comparison is offline and processes every valid visit. [Matched native stage timing](../one-lane-arm/README.md)

## Position error and frequency fit

Both detector policies met the +5% and +10% margins against original no-repair v5 on one of two recordings per calibration arm. The one-antenna rule improved the difficult DS29 fix by 1.76 km at `c = 0` and 1.62 km with fitted `c`, and its remaining errors exceeded both v5 margins. DS26 error increased by 0.76 and 0.29 km while still meeting both margins. [All four original v5 options and measured results](scores.csv) · [Both calibration arms, pooled and per-recording charts](charts/README.md)

| Recording | Original no-repair v5, `c = 0` / fitted `c` | Stock four, `c = 0` / fitted `c` | One antenna, `c = 0` / fitted `c` |
| --- | ---: | ---: | ---: |
| DS26-0014 | 3.415 / 3.405 km | 0.472 / 0.755 km | 1.236 / 1.050 km |
| DS29-0082 | 0.567 / 0.517 km | 2.489 / 2.346 km | 0.728 / 0.728 km |

One-antenna conditional frequency RMS was 99.836 / 99.757 Hz on DS26 and 105.188 / 104.964 Hz on DS29. The stock values were 97.385 / 97.570 and 84.421 / 84.248 Hz. Conditional RMS depends on the observations the detector supplies. Within each one-antenna calibration pair, fitted `c` decreased RMS by 0.078 and 0.224 Hz, and reduced the position errors by 185 m and less than 1 m. [Matched within-branch calibration deltas and frequency scores](calibration.csv)

## Startup and comparison provenance

The first two launches stopped before decoding IQ because the measurement hook was placed at the installed source function the archive reader authenticates. The corrected transport observes the authenticated segment iterator and keeps that installed function in place. The one-lane policy, native binary, selected recordings and comparison inputs stayed fixed. Both zero-IQ launch attempts and their terminal receipts are preserved separately from the two complete scientific attempts. The earlier historical DS29 stock timeout also remains in the original attempt ledger. [Startup source and receipts](startup-incident/source-lock.json) · [Historical stock attempts](../../track-recovery/wide-roster/attempts.json)

## Physical board availability

On 2026-11-19 the host enumerated the development PlutoSDR+ ending `4759d` over USB. The active production scanner was assigned to the separate unit ending `a5d4d`. The development LAN preflight used the documented privileged route and its project-pinned key. SSH returned 255 at strict host-key verification, with no remote shell output. The earlier USB Ethernet check had also stopped at strict host-key verification. The host exposed an unopened serial device and zero local remote-processor endpoints. An authenticated idle board could therefore not be established. No benchmark payload was transferred, and no hardware settings or acquisition state changed. [Current preflight receipt](board-availability.json) · [Prior LAN and USB route checks](../../receiver-core/board-replay/README.md)

The physical Cortex-A9 receipt covers the earlier DS9 2.5 MS/s detector. It passed 80 ordinary and 80 fractional saved dwells and took 32.525 s for the complete test, including its dual and extracted single calls. The current 10 MS/s one-lane stage has native x86 and emulated AArch64 measurements. Physical timing for this detector remains unavailable. [Historical physical board receipt](../one-lane-arm/historical-board.json) · [Current stage results](../one-lane-arm/README.md)
