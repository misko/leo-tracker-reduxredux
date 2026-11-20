# Direct partner-on-hit at the original recorded pace

Partner-on-hit increased outputs within 20 ms from **67 to 3,529** of 6,704 valid arrivals. On-time outputs carrying at least one positive probe fell from **9 to 4**. Roof error increased from **0.562 / 0.607 km** with stock dual to **0.993 / 1.085 km** with direct partner-on-hit at `c = 0` / fitted `c`. [Deadline support](deadline-support.csv) · [Timing plot](pace.png) · [Zero calibration](charts/c0/modifications.pdf) · [Fitted calibration](charts/fitted_c/modifications.pdf)

DS29-0174 replays twice at its original 300.006 s host delivery schedule. Stock dual runs first and direct partner-on-hit follows. Both use one detector worker on CPU10, one waiting visit, the same released stock-wide fractional native library, a 512 MiB charged memory limit and zero swap. There is no new collection. [Protocol](PROTOCOL.md) · [Executable and dispatch lock](detector-lock.json) · [Live source lock](source-lock.json)

The direct branch runs one actual physical receiver first. It runs the other receiver only if an actual primary candidate passes the existing full fractional gate. The primary alternates separately at each exact RF center. Hardware-invalid visits leave the counter alone. Valid dropped visits still occupy their position in the physical sequence. Both probes keep their original metadata. An unmeasured partner has an empty candidate list. The expected full emission hashes come from an independent archived stock projection and verify the real result after detection. A fixed first-32-window preflight exercised both primary lanes and 20 one-lane versus 12 two-lane decisions with exact packet equality. [Actual preflight](preflight.json)

## Source and replay boundary

An external CPU11 service independently authenticated 106 original compressed members and all 6,774 staged CI16 windows. The 10,838,400,000-byte tmpfs file had the same full readback SHA as the preceding controlled-pacing experiment. The recording clock, RF, sample support and invalid status remain bound by the window ledger. The 12 GiB no-swap source cgroup stayed blocked during both clocks. It is separate from each receiver cgroup. [External staging receipt](ready.json) · [Per-window source ledger](members.json.gz) · [Source release](source-terminal.json)

The receiver used its original depth-eight source prefetch and one waiting detector visit. Timing records every raw clock outcome, including invalid visits and queue drops. Arrival age starts at the frozen due time. Detector-call wall excludes waiting for admission. Independent timing columns separate input readiness from delay after the buffer became available. [Both complete raw traces](raw) · [Timing and active support](timing.csv) · [Delay decomposition](arrival-decomposition.csv) · [Paced timing plot](pace.png)

| Observed deadline and work on DS29-0174 | Stock dual | Direct partner on hit |
| --- | ---: | ---: |
| Emitted / 6,704 valid visits | 6,627 | 6,612 |
| Queue drops | 77 | 92 |
| Hardware invalid | 70 | 70 |
| Late source buffers | 0 | 0 |
| Release delay P95 (ms) | 1.17 | 1.45 |
| Detector wall median / P95 (ms) | 28.70 / 51.68 | 16.37 / 47.99 |
| Detector CPU median / P95 (ms) | 25.22 / 32.36 | 13.63 / 32.39 |
| Arrival-to-emission age median / P95 (ms) | 30.87 / 61.97 | 18.59 / 59.75 |
| Emitted within 20 ms of due time | 67 | 3,529 |
| Actual physical antenna calls | 13,254 | 8,688 |
| Positive probes in retained packets | 4,116 | 3,220 |

On exactly 6,535 common emitted visits, the direct branch saved a median 9.89 ms of detector CPU and 10.62 ms of detector wall. Positive-probe counts on these same visits were 4,069 for dual and 3,181 for direct. The direct worker omitted the partner on 4,536 emitted visits, including 902 with an independently verified positive partner in stock. [Common-emission cost and support](common-cost.json)

The direct worker delivered 3,525 of its 3,529 on-time outcomes after a primary miss, with zero positive probes in those emissions. Only 4 of 2,076 direct primary hits met the due-to-output target, carrying seven positive probes. The corresponding stock dual count was ten probes across nine timely positive visits. Native wall median/P95 was 13.97/32.30 ms for direct single-lane misses and 31.46/64.26 ms for direct two-lane hits. [Positive support by deadline and branch](deadline-support.csv) · [Direct arrival trace](raw/hit/trace.json.gz)

The two whole clock services ran for 303.26 and 303.20 s. The elapsed paired worker interval was 603.98 s. Stock and direct receiver charged peaks were 216.3 and 213.2 MiB, with zero swap. The external source used zero CPU during both clocks and was charged about 10.25 GiB at both closes. Its temporary CI16 file was released before positioning. [Worker and source resources](timing.csv) · [Source terminal receipt](source-terminal.json)

## Position and RF fit

The compact solver runs each genuinely retained emission set using the original 25 km offer, causal TLE history and the same numerical settings across `c = 0` and fitted `c`. Geographical scores use the surveyed roof. RF RMS and frequency objective are conditional on each fit's recruited observations. [Position-input lock](position-input-lock.json) · [Terminal prediction lock](prediction-lock.json) · [Position and conditional RF scores](scores.csv)

Each paired value lists `c = 0` / fitted `c`.

| Position input | Geographic error (km) | Conditional RF RMS (Hz) | Conditional frequency objective |
| --- | ---: | ---: | ---: |
| Stock dual, actual emitted packets | 0.562 / 0.607 | 101.00 / 101.16 | 31,689.75 / 31,682.42 |
| Partner on hit, actual emitted packets | 0.993 / 1.085 | 98.00 / 98.06 | 25,241.29 / 25,232.16 |
| Original v5 no repair or selective gap | 0.885 / 0.917 | | |
| Original v5 one or all omitted-track nomination | 0.881 / 0.912 | | |

Both actual compact fits published both arms. Stock dual stayed within 5% of the matching v5 no-repair error for each arm. Direct partner-on-hit exceeded the 10% allowance in both. The actual position worker used 4,116 observations on 131 tracks for dual and 3,220 observations on 111 tracks for direct. The respective worker walls were 79.1 s and 96.3 s, recorded on separate position cores after both IQ clocks finished. [Measured position resources](positions.jsonl.gz)

The paired timings describe the one-worker host boundary. Earlier parallel fused-four and unpaced direct-on-hit results use their separately labeled measurements. Re-score the sealed endpoint data without rereading IQ.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.paced_hit_results score
.venv/bin/python -m tools.pipeline_eval.qualification.paced_hit_deadline_audit
```
