# Controlled recorded pace from predecoded local IQ

Staggered fifth returned lower position error in both run orders on this recording. Fused four emitted more visits in both. In the AB pair every buffer was ready on time. Staggered then dropped 377 of 6,704 valid visits, compared with 103 for fused four, and used 4.40 ms more median detector CPU on the same 6,225 emitted visits. Fitted-`c` error in that pair was 0.471 km for staggered and 0.884 km for fused four. [Receiver timings](timing.csv) · [Position error charts, zero calibration](charts/c0/modifications.pdf) · [Position error charts, fitted calibration](charts/fitted_c/modifications.pdf)

Four host replays on DS29-0174 compare fused four and staggered fifth in BA then AB order. The callers used CPU22 and the persistent native helper used CPU23. All replays share the original 300.006 s arrival clock, one waiting visit, the same 512 MiB receiver cap and zero swap. This is one saved waveform and one surveyed roof. [Protocol](PROTOCOL.md) · [Replay and binary lock](source-lock.json)

## Input and charge boundary

The external staging service decoded all 6,774 original physical windows into a 10,838,400,000-byte local tmpfs file. It authenticated 106 original compressed members and each original window's CI16 SHA-256. An independent full readback matched the write digest `28c041dc6e6d8541392992f255bf0d32689603815b7be7cf9e3b555597dd1074`. The input ledger preserves hardware-invalid windows, both receivers, recorded delivery timestamps, RF center, tick counters and per-window hashes. It is portable without the local scratch IQ file. [Staging lock](source-stage-lock.json) · [Authenticated input receipt](ready.json) · [Per-window metadata ledger](members.json.gz)

The source stayed blocked inside its separate 12 GiB zero-swap cgroup during timing. Each receiver prefetch loop read fixed-size decoded buffers from the read-only staged file and used its original depth-eight prefetch and one waiting slot. Every measured emission had to match the predeclared full native packet fingerprint. The external input cache remains outside the receiver cap. [Receiver traces and cgroup marks](raw) · [Source release receipt](source-terminal.json)

## Arrival outcomes and latency

Arrival age is elapsed from the archived due time to actual emission. Its percentiles describe emitted visits. Release delay describes every physical visit. The source audit splits each observed release delay into any buffer-ready lateness beyond the due time and the remaining delay from the later of buffer readiness and due time to observed release. The latter includes host scheduling and the queue handoff. The same decomposition applies to the two earlier authenticated QNAP-fed replays. [Raw timing and memory](timing.csv) · [Arrival delay decomposition](arrival-decomposition.csv) · [Startup and later emissions](startup.csv) · [Timing and coverage figure](pace.png)

| Order and receiver | Emitted / 6,704 valid | Queue drops | Late buffers | P95 release / age (ms) | Detector wall median / P95 (ms) | Emissions within 20 ms of due time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BA staggered fifth | 4,919 (73.37%) | 1,785 | 73 | 49.00 / 188.77 | 18.59 / 92.80 | 2,380 |
| BA fused four | 6,154 (91.80%) | 550 | 0 | 1.34 / 77.65 | 14.81 / 48.06 | 4,516 |
| AB fused four | 6,601 (98.46%) | 103 | 0 | 0.13 / 21.03 | 13.43 / 19.47 | 6,194 |
| AB staggered fifth | 6,327 (94.38%) | 377 | 0 | 0.24 / 33.71 | 16.82 / 28.82 | 4,630 |

All 6,774 arrivals were accounted for in each run, including 70 hardware-invalid windows. The earlier QNAP-fed fused/staggered runs had 40/133 late buffers and P95 release delay of 0.87/32.70 ms. In the staged BA staggered run, 376 of 444 releases delayed by more than 20 ms already had the buffer at the due time. Both staged AB runs had zero late buffers. That pair still had 274 additional staggered queue drops, with staggered costing a median 4.40 ms additional summed detector CPU and 3.33 ms additional wall per call on the same 6,225 emitted visits. On the 4,548 common BA emissions, the respective differences were 2.70 ms CPU and 3.10 ms wall. [Arrival decomposition](arrival-decomposition.csv) · [Paired per-call cost](paired-visit-cost.csv)

Each real receiver service ran for 303.28–304.12 s, and elapsed time across the four clocks was 1,211.88 s. Receiver `memory.peak` was 247.6–259.2 MiB with zero swap. The source recorded zero CPU time across all four timing intervals. Its charged memory at the end of the receiver clocks was 10.26 GiB, including the 10.09 GiB decoded payload. The external stage reached its 12 GiB charge cap during construction and readback. The source service stopped and released the 10.8 GB CI16 file before the position fits. [Source terminal receipt](source-terminal.json) · [Actual raw resource ledgers](raw)

## Position and frequency fit

An actual compact phase-release solve used each clock's emitted packet set. Each solve shares the original 25 km tile and causal TLE history with the four archive controls. Its `c = 0` and fitted `c` arms share the detector inputs, configuration and numerical budget. Geographic error uses the surveyed roof. Residual RMS and the frequency objective are conditional on the fitted observations. [Position input seal](position-input-lock.json) · [Terminal prediction seal](prediction-lock.json) · [Both-arm geographic and RF scores](scores.csv)

Each paired value lists `c = 0` / fitted `c`.

| Position input | Error (km) | Conditional RF RMS (Hz) | Conditional frequency objective |
| --- | ---: | ---: | ---: |
| BA staggered fifth | 0.659 / 0.706 | 94.01 / 94.07 | 24,579.23 / 24,571.04 |
| BA fused four | 0.938 / 0.839 | 105.12 / 105.21 | 23,323.50 / 23,323.63 |
| AB fused four | 0.843 / 0.884 | 100.49 / 100.64 | 31,572.21 / 31,562.48 |
| AB staggered fifth | 0.427 / 0.471 | 98.57 / 98.70 | 30,616.37 / 30,596.75 |
| Original v5 no repair or selective gap | 0.885 / 0.917 | | |
| Original v5 one or all omitted-track nomination | 0.881 / 0.912 | | |

All four fits published both arms under the shared 512 MiB cap and zero swap. The four compact-worker walls were 53.1–74.8 s. In the BA pair, fused/staggered fits used 3,865/3,242 observations and 125/118 tracks. In the AB pair they used 4,101/4,083 observations and 126/134 tracks. In the earlier QNAP-fed run the geographic ranking favored fused four. That run retained a different set of physical visits, and all six paced outcomes describe the same waveform. [Measured compact resources](positions.jsonl.gz) · [Earlier geographic scores](../../receiver-choice/equal-pace/scores.csv)

The archived detector output and survey never drive a live queue decision. Earlier QNAP-fed measurements are a labeled reference. Re-score without replaying saved IQ.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.paced_controlled_arrival_audit
.venv/bin/python -m tools.pipeline_eval.qualification.paced_controlled_results score
```
