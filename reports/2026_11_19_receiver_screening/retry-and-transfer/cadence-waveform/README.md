# Chronological saved-IQ retry cadence

Waiting two seconds after a missed retry saved **5.0% detector CPU on DS26-0237** and **12.9% on DS29-0082**. It retained one of two rescues on the lower edge and all five rescues on the upper edge. The timer keys are physical receiver and actual RF. Each timer advances only upon observing the fractional gate of a freshly executed retry. [Frozen plan](plan.json) · [Protocol](PROTOCOL.md)

Each policy ran in two interleaved rounds, with a rotating policy order at every visit. The timers started empty in each span and round. The four spans were selected by a fixed hash of recording and chunk coordinates, using only the physical exclusion roster and a minimum of 32 valid visits per span. Every visit in each span retained its original order and host delivery timestamp. [Plan and worker receipts](receipts/)

| Recording | Scheduled visit spans | Valid visits |
|---|---|---:|
| DS26-0237, lower edge | 2688–2751 and 5248–5311 | 128 |
| DS29-0082, upper edge | 0–63 and 5824–5887 | 93 |

The hook runs inside the installed original producer, after both 12-anchor primary evaluations. When the timer suppresses a retry, it reuses the current receiver's actual primary evaluation object and runs no wide FFT or refinement. The recipe uses the same qualified grid, exact row selector and pruned fine-CFO kernel in all three modes. [Raw implementation](../../../../tools/pipeline_eval/qualification/cadence_waveform.py)

The saved delivery timestamps drive the timer. The replay processes each span at host speed and measures the resident detector separately from IQ reading and authentication. The timing chart covers waveform acquisition and projection. [Timing chart](timing.pdf) · [Stage descriptor](stage-figure.json)

## DS29-0082 upper edge

Waiting after a miss cut retries from **35 to 18**, retained all **five rescues**, and saved **8.12 detector CPU seconds per round (12.9%)**. In the wait-after-hit policy, 32 retries retained four rescues and saved 1.95 detector CPU seconds. Both rounds produced the exact expected ordered factors, including rejected candidates, on all 93 valid visits in each policy. The 35 original physical exclusions remained excluded. [Packet and timing audit](audit.json)

| Policy | Actual wide calls | Rescues | Detector CPU (s/round) | Retry CPU (s/round) | Median detector CPU (ms/valid visit) |
|---|---:|---:|---:|---:|---:|
| Full conditional | 35 | 5 | 63.20 | 16.56 | 518.97 |
| Wait after miss | 18 | 5 | 55.08 | 8.67 | 495.77 |
| Wait after hit | 32 | 4 | 61.25 | 15.09 | 514.99 |

The equal-paced control spaces each policy's retry count over the same eligible visits per span, receiver and RF. Its CPU estimate composes measurements of the full and suppressed paths on the same visit where available. For a suppressed path without a direct measurement, it subtracts the observed retry CPU from the full detector CPU. The upper miss-count control retained four rescues at an estimated 54.58 CPU seconds per round and used eight inferred suppressed-path costs. The hit-count control retained four at an estimated 61.63 CPU seconds and used one inferred cost. [Control composition and cost sources](audit.json)

## DS26-0237 lower edge

Waiting after a miss cut retries from **17 to eight**, retained **one of two rescues**, and saved **3.54 detector CPU seconds per round (5.0%)**. Waiting after a hit ran the same retries and produced the same factors as full conditional. The equal-paced miss-count control retained one rescue at an estimated 67.02 CPU seconds per round and used five inferred suppressed-path costs. [Packet and timing audit](audit.json)

| Policy | Actual wide calls | Rescues | Detector CPU (s/round) | Retry CPU (s/round) | Median detector CPU (ms/valid visit) |
|---|---:|---:|---:|---:|---:|
| Full conditional | 17 | 2 | 70.96 | 7.04 | 496.58 |
| Wait after miss | 8 | 1 | 67.42 | 3.24 | 491.82 |
| Wait after hit | 17 | 2 | 71.42 | 7.15 | 497.36 |

The original lower service shared CPU12 early in the replay and reached its 720-second cap before emitting a complete packet receipt. The timed lower result comes from the complete recovery on CPU13 with the same frozen spans, detector, interleaving, cap and nice level. Its elapsed time including reading and authentication was 519.24 s. The upper service ran on CPU16 and took 416.98 s. Both completed workers stayed below 233 MiB cgroup peak and used zero swap. [Original lower service log](receipts/DS26-0237.log.gz) · [Recovery service log](receipts/recovery/DS26-0237.log.gz) · [Upper service log](receipts/DS29-0082.log.gz)

Across the two completed workers, all 1,536 projected packets agreed with the independent cold-start factor schedule, including the 1,326 valid dual-receiver packets. The grid telemetry confirmed every suppressed wide call was absent. No valid detector invocation completed within 20 ms. [Sealed evidence](stage-lock.json) · [Per-round timing](stage.csv)
