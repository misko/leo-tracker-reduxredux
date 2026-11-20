# Original-quality GLRT at the live recorded arrival clock

The original-quality FIFO emitted **387 of 4,868 valid visits (7.95%)** on DS29-0082 and withheld both positions for `no_active_curvature`. Fast four emitted **4,836 (99.34%)** and returned **2.485 / 2.340 km** error at `c = 0` / fitted `c`. Every staged buffer was ready on time in both runs. Neither detector delivered a positive probe within 20 ms of its original arrival. [Raw timing and support](timing.csv) · [Observed age and coverage](pace.png) · [Position scores](scores.csv)

DS29-0082 replays twice at its original physical delivery times. The qualified original-quality combined detector runs first and the released fast four-region dual detector second. Both use CPU10, one active detector, one waiting visit, depth-eight input prefetch and a 512 MiB charged receiver limit with zero swap. Each complete clock preserves all 6,772 arrivals, including 1,904 hardware-invalid visits. There is no new RF acquisition. [Protocol](PROTOCOL.md) · [Source and binary lock](source-lock.json) · [Exact physical arrival ledger](clock-events.json.gz)

## Original detector and staged input

The original worker runs the capture-whole qualified FFT grid, conditioned CFO and fused refinement libraries through the pinned legacy capture Python and producer. It retains the full original detector policy. The fast path runs the unchanged released wide fractional stereo library. Each valid original call must execute the qualified full-grid computation. Both paths authenticate all actual emitted candidate fields against their own independently measured complete replay. A real first-16-window preflight reproduced both packets on every visit, including 13 valid and three hardware-invalid arrivals. [Paired prefix](preflight.json) · [Original complete qualification](../../antenna-confirmation/capture-whole/README.md)

CPU11 authenticated and predecoded 10,835,200,000 bytes into a read-only tmpfs source, with every archived chunk and window hashed and the entire staged file read back independently. Input-manifest publication to the validated ready receipt took 55.71 s at the host file clock. Predecode resource markers recorded 49.76 s of CPU and a 10.50 GiB charged peak in the separate 12 GiB no-swap cgroup. That source remained blocked during the receiver clocks. A separate CPU12 experiment shared the exact source bytes, and cleanup followed both studies' confirmed terminal consumers. [Source staging clock](source-timing.json) · [Staging and compressed-input receipt](ready.json) · [Source cleanup](source-terminal.json)

## Observed pacing and retained support

Release age starts at the original scheduled arrival. Detector wall and CPU describe measured calls on the active worker. Every valid queue drop stays in the denominator. Deadline support counts actual positive GLRT probes in emitted packets by 20 ms. The timing decomposition separates late source buffers from delay after the buffer was available. [Actual timing](timing.csv) · [Arrival delay decomposition](arrival-decomposition.csv) · [Coverage and age figure](pace.png) · [Raw prediction seal](raw-prediction-lock.json)

| Actual CPU10 clock on DS29-0082 | Original quality | Fast four |
| --- | ---: | ---: |
| Physical arrivals | 6,772 | 6,772 |
| Hardware-invalid captures | 1,904 | 1,904 |
| Emitted / valid | 387 / 4,868 | 4,836 / 4,868 |
| Valid queue drops | 4,481 | 32 |
| Late source buffers | 0 | 0 |
| P95 release delay (ms) | 6.46 | 0.74 |
| Detector wall median / P95 (ms) | 670.20 / 1,292.33 | 29.60 / 49.36 |
| Detector CPU median / P95 (ms) | 646.28 / 1,240.09 | 25.72 / 31.95 |
| Arrival-to-emission age median / P95 (ms) | 1,360.81 / 2,215.77 | 31.16 / 56.36 |
| Emitted within 20 ms from arrival | 0 | 4 |
| Positive visits / probes emitted | 108 / 151 | 1,588 / 2,043 |
| Positive probes emitted within 20 ms | 0 | 0 |

The clock span was 299.997 s per run. The complete original and fast manager intervals were 304.78 and 303.75 s, and 606.06 s elapsed between the earliest worker start and latest drain. Receiver charged peaks were 241.1 and 214.6 MiB with zero swap. The external source had zero measured CPU use during each receiver clock and about 10.25 GiB charged memory at both ends. [Receiver and source receipts](raw)

## Position on actual emitted factors

Each compact position stage uses only the emitted packet subset of that complete clock, the original 25 km search offer, frozen causal orbital history and unchanged compact numerical configuration. Both calibration arms share the input inventory within each method. Separate geographical error and conditional frequency-fit measurements accompany the four original capture-era v5 options. [Position-input seal](position-input-lock.json) · [Terminal prediction seal](prediction-lock.json) · [Geography and RF scores](scores.csv)

Each paired value lists `c = 0` / fitted `c`.

| Position input | Geographic error (km) | Conditional RF RMS (Hz) | Conditional frequency objective |
| --- | ---: | ---: | ---: |
| Original-quality FIFO emissions | Withheld / withheld | | |
| Fast-four FIFO emissions | 2.485 / 2.340 | 84.548 / 84.365 | 11,581.57 / 11,583.17 |
| Earlier complete original-quality factors | 0.568 / 0.516 | 97.003 / 96.684 | 6,337.72 / 6,342.81 |
| Earlier complete fast-four factors | 2.489 / 2.346 | 84.421 / 84.248 | 11,677.73 / 11,679.34 |
| Original v5 no repair or selective gap | 0.567 / 0.517 | | |
| Original v5 one or all omitted-track nomination | 0.115 / 0.486 | | |

The original live compact service completed successfully and withheld both endpoints because its emitted factors had no active curvature. It took 1.04 s after worker entry. Fast four used 2,043 observations on 70 tracks and returned both arms in 44.07 s. The fast-four positions were close to its earlier complete-factor endpoints and exceeded the original v5 10% allowance in each arm. The earlier complete original-quality run used a different raw scheduling boundary. [Actual compact services](positions.jsonl.gz) · [Complete reference comparisons](../../antenna-confirmation/capture-whole/scores.csv)

Re-score the paired sealed position results and regenerate the figures.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.paced_original_results score
```
