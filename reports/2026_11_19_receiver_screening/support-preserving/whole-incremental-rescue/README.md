# Stock-first incremental rescue on complete saved recordings

The incremental detector preserved all **8,519 stock-positive receiver packets** and added **902 positive packets** across the two complete saved-IQ recordings. It tightened both DS29-0316 position errors to 0.194 km, about 24 m better than the unconditional fifth center. On DS26-0197 it increased both errors relative to both controls. The complete host services returned both positions in 230.00 and 239.65 s at the enforced 512 MiB zero-swap cap. Only 11 of 13,535 measured detector calls met 20 ms wall time. [Position scores](scores.csv) · [Raw detector audit](probe-audit.json) · [Service and resource clocks](deadlines.csv)

## Full saved-IQ execution

DS26-0197 and DS29-0316 repeat the already scored fifth-center comparison. The services replayed the complete recorded dual-CI16 span on the same authenticated capture manifests, original invalid visits, acquisition clocks and receiver/RF mappings. The phase-release receiver used the exact frozen numerical installation, original causal TLE history and original blind offered tile. Both calibration arms share each mode's effective observations and search budget. The new services ran on CPUs 16/17 and 22/23, with a 450 s per-recording deadline and no swap. Earlier stock and unconditional fifth-center controls ran on CPUs 4/5 and 6/7. [Prospective input lock](input-lock.json) · [Compiled release and qualification](candidate-lock.json) · [Complete prediction seal](prediction-lock.json)

The native stock pass runs first. A lane with an existing positive skips the scout and donor search. A negative lane runs the same differential scorer on that physical receiver only. Its highest-ranked point supplies a clipped ±1-epoch region if all its epochs fall outside the stock search. The detector reuses the prepared samples and the warm workspaces, then scores that one region over the same 21 CFO bins and through the unchanged native fine and fractional gates. It keeps the archived-equivalent stock packet if the donor fails. Before whole replay, the installed producers independently reproduced original stock factors on six authentic saved windows covering zero, one and two stock-positive lanes. This included a live DS26-0197 rescue on RX1 while RX0 retained its stock-positive packet. [Native stage qualification](../incremental-rescue/feature-gate.json) · [DS26 installed canary](DS26-0197-installed.json) · [DS29 installed canary](DS29-0316-installed.json)

| Recording | Valid dual calls | Stock-positive lanes, all exact | Negative lanes scouted | Actual extra regions | Added positives, incremental / fifth | Incremental gains physically matching fifth winner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0197 | 6,761 | 4,219 | 9,303 | 9,227 | 417 / 339 | 329 |
| DS29-0316 | 6,774 | 4,300 | 9,248 | 9,216 | 485 / 417 | 402 |

No stock-positive lane scouted or searched again. All 108 proposals with overlapping stock neighborhoods skipped donor search. All remaining negative packets stayed exact. Each qualifying donor left exactly one additional positive lane. Physical matches use a circular two-sample timing tolerance and 1 kHz absolute CFO tolerance on the corresponding winning probes. The common support counts of newly positive receivers were 336 and 416. [Per-call execution and probe ledger](visits.jsonl.gz)

## Position and conditional frequency

| Recording | Receiver | Horizontal error, `c = 0` / fitted `c` | Conditional Doppler RMS, `c = 0` / fitted `c` |
| --- | --- | ---: | ---: |
| DS26-0197 | Stock wide | 0.792 / 0.992 km | 80.516 / 80.556 Hz |
| DS26-0197 | Unconditional fifth | 0.759 / 0.937 km | 83.485 / 83.501 Hz |
| DS26-0197 | Incremental | 1.045 / 1.191 km | 84.099 / 84.094 Hz |
| DS29-0316 | Stock wide | 0.834 / 0.852 km | 119.815 / 119.818 Hz |
| DS29-0316 | Unconditional fifth | 0.218 / 0.218 km | 120.068 / 120.063 Hz |
| DS29-0316 | Incremental | 0.194 / 0.194 km | 120.630 / 120.625 Hz |

Each method was within 10% of original no-repair v5 on one of two recordings in both calibration arms. The original v5 reference is 0.528 / 0.689 km for DS26-0197 and 1.007 / 1.011 km for DS29-0316. All four original v5 settings use their capture-era factors and appear in the standard charts. The DS29 geographic improvement came with a higher conditional RF RMS and objective. These frequency metrics apply to each method's fit on its selected observations. [Both calibration charts](charts/README.md) · [Complete coordinates and objective receipt](positions.jsonl.gz)

## Measured detector and position costs

| Recording and branch | Calls within 20 ms wall | Detector wall median / p95 | Detector CPU total | Raw / position wall | Whole pipeline wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0197 stock | 6,304 / 6,761 | 15.58 / 20.98 ms | 104.83 s | 77.71 / 48.55 s | 127.02 s |
| DS26-0197 fifth | 3,522 / 6,761 | 19.86 / 30.92 ms | 131.73 s | 96.00 / 64.46 s | 161.44 s |
| DS26-0197 incremental | 7 / 6,761 | 36.68 / 46.91 ms | 239.93 s | 149.15 / 79.83 s | 230.00 s |
| DS29-0316 stock | 6,282 / 6,774 | 15.69 / 21.00 ms | 105.97 s | 76.79 / 55.63 s | 133.24 s |
| DS29-0316 fifth | 3,349 / 6,774 | 20.04 / 33.13 ms | 132.25 s | 110.88 / 61.25 s | 173.15 s |
| DS29-0316 incremental | 4 / 6,774 | 37.40 / 47.24 ms | 247.05 s | 152.48 / 86.19 s | 239.65 s |

Incremental scout CPU averaged 4.60 and 4.57 ms per actual dual visit. The extra native region added 6.40 and 7.28 ms. The measured remainder of the native call, including the stock pass and wrapper bookkeeping, averaged 24.35 and 24.48 ms. Factor assembly took 1.02 and 0.98 s. Both services reached the 512 MiB charged limit with zero swap and completed under the roughly 300 s original acquisition span. Individual call compliance uses its own measured 20 ms wall threshold. The whole-service timing comparisons retain the different CPU pairs and host load. [Full resource receipts](resources.json) · [Split call clocks](probe-audit.json)

The paired runtime diagnostic used the same six saved windows as the installed canaries, one window with each stock-positive lane count per recording, all three implementations on one assigned core, and six counterbalanced repeats. With two positive lanes the median incremental CPU was 27.24 and 24.20 ms versus 35.12 and 28.74 ms for the fifth center. With one or two negative lanes the four corresponding incremental medians were 32.16–39.40 ms versus 27.55–30.08 ms for the fifth center. The small matched stage isolates a workload dependence also present in the complete detector trace. The whole comparisons represent one roof and two recordings. [Matched host detector figure](paired-host-detector.pdf) · [Measured host repetitions](paired-host-detector.csv)
