# Bounded detector arrivals on DS26-0020

One second of buffering recovered enough detector output to compute positions, but no tested policy came within 10% of original v5. Four-worker FIFO gave the lowest error among the bounded policies, at **1.170 km with c = 0 and 1.196 km with fitted c**. This is 43.0% and 61.9% above the original v5 no-repair errors of 0.818 km and 0.739 km. Full portable C gave 0.813 km and 0.734 km. This is one recording in the frozen DS26 excluded-32 panel. [Position scores](scores.csv) · [Position charts](charts/README.md)

## Delivery and queue readiness

The full recording has 6,764 physical dual-receiver arrivals, including three invalid captures. Signed hardware sample end counters span 299.970 s at 10 MHz. Signed host delivery clocks span 299.968 s. Queue admission uses the host delivery clock and original validity gate. Inference uses the original hardware-counter observation times and complete probe pairs. Every queue had eight waiting slots for 12.8 MB of CI16 payload plus one or four in-flight windows. The deadline was one second after the last physical delivery. A visit also had to finish within one second of its own delivery. [Frozen protocol](PROTOCOL.md) · [Signed physical clock and service inputs](portable-field-physical.json.gz)

| Workers and policy | Ready on accelerated CPU model | Ready on portable C CPU model | Ready on portable C wall model | Portable C CPU model age p50 / p95 | Last delivery waiting / running | Final deadline waiting / running |
|---|---:|---:|---:|---:|---:|---:|
| 1, FIFO | 25 | 27 | 41 | 968 / 995 ms | 8 / 1 | 0 / 0 |
| 1, replace oldest | 1,008 | 1,194 | 1,105 | 553 / 692 ms | 8 / 1 | 0 / 1 |
| 1, RF round robin | 1,098 | 1,212 | 1,096 | 421 / 652 ms | 7 / 1 | 0 / 0 |
| 4, FIFO | 3,665 | 4,955 | 4,064 | 675 / 835 ms | 8 / 4 | 0 / 0 |
| 4, replace oldest | 4,035 | 4,901 | 4,268 | 540 / 682 ms | 8 / 4 | 0 / 0 |
| 4, RF round robin | 4,060 | 4,979 | 4,288 | 422 / 627 ms | 4 / 4 | 0 / 0 |
| 1, zero wait, next delivery | 0 | 0 | 0 | — | 0 / 1 | 0 / 0 |

The eight-worker raw replay measured portable C median service of 211.9 ms CPU and 214.0 ms wall per valid visit. Mean CPU service was 241.5 ms, equivalent to about 5.44 cores at this arrival density before queue and inference overhead. Four-worker RF round robin offered the most ready visits and the lowest p95 age among its peers. Its 622–623 ready visits per RF target were also the most evenly distributed. By the last delivery, four-worker FIFO, replace oldest, and RF round robin had already finished 4,943, 4,889, and 4,971 usable visits. The one-second drain added 12, 12, and 8, respectively. In the wall-service sensitivity one visit also remained running for one-worker FIFO at the final deadline. The score table uses the portable C CPU-service model to select fits. [Accelerated model](accelerated-secondary-schedules.json.gz) · [Portable C model and exact outcomes](portable-field-schedules.json.gz)

## Paced C measurement

One pinned host CPU replayed the first 64 authenticated windows through the same portable C adapter over 2.8 s of recorded arrivals. The harness predecoded 102.4 MB of signed IQ before the timed stream. It finished nine detector jobs, verified all nine probe pairs against the full C raw replay, and published five within one second. The waiting queue was full with one job running at the last delivery and empty with no job running at the final deadline. The independent CPU- and wall-service models also predicted five timely publications, with three visit identities in common with the paced run. Among six matched finishes, the measured completion was a median 180 ms later than the CPU-service model. The measured detector median was 209.6 ms CPU and 312.6 ms wall. Producer release jitter was 0.075 ms median and 24.2 ms p95. All five measured packets missed their next physical delivery and had a 730 ms median age. This short run exposes host timing and handoff effects. The full-recording selections and four-worker queue timings remain modeled. [Paced events](paced-fifo.json) · [Paced and modeled comparison](paced-comparison.json)

## Actual paired compact fits

Each measured compact attempt used the same causal TLE inventory, original request settings, and offered 25 km tile for its two calibration arms. The same selected observations were supplied to both arms. Original invalid-capture records, signed delivery clocks and the sample-counter span survived the rebuild. The six attempted queue fits took 0.61–49.63 s each with 109–363 MiB peak memory under a 512 MiB no-swap cap and a 180 s deadline. The one-worker FIFO service completed and withheld the fix for lack of active curvature. The zero-wait control had no timely probe pair and skipped the solve. [Fit receipts](queue-fits.json.gz) · [Causal and original source bindings](source-bindings.json)

| Input | Position error c = 0 / fitted c | CFO RMS c = 0 / fitted c | Fitted c minus c = 0 frequency score |
|---|---:|---:|---:|
| 4-worker FIFO | 1.170 / 1.196 km | 72.110 / 72.108 Hz | +9.43 |
| 4-worker RF round robin | 1.441 / 1.455 km | 73.307 / 73.275 Hz | +8.08 |
| 4-worker replace oldest | 1.605 / 1.614 km | 71.526 / 71.516 Hz | +9.64 |
| 1-worker RF round robin | 4.651 / 4.658 km | 65.443 / 65.459 Hz | +11.48 |
| 1-worker replace oldest | 4.805 / 4.693 km | 85.376 / 84.108 Hz | +11.88 |
| 1-worker FIFO | withheld / withheld | — | — |
| Zero-wait next delivery | no solve / no solve | — | — |
| Full portable C | 0.813 / 0.734 km | 72.547 / 72.512 Hz | +8.94 |
| Archived compact | 0.813 / 0.734 km | 72.547 / 72.512 Hz | +8.94 |
| Original v5 no repair | 0.818 / 0.739 km | 72.548 / 72.513 Hz | — |
| Original v5 selective gap | 0.818 / 0.739 km | 72.548 / 72.513 Hz | — |
| Original v5 omitted track one | 0.756 / 0.670 km | 73.002 / 72.834 Hz | — |
| Original v5 omitted tracks | timeout / timeout | — | — |

Fitted c increased the frequency score of every queue fit that returned a fix. Geographic error increased for four of those five and fell by 112 m for one-worker replacement. Four-worker FIFO had slightly lower fitted CFO RMS than full portable C, while its fitted position error was 462 m higher. Its combined modeled detector deadline and measured compact wall time put a serial end-of-recording fix about 49 s after the last delivery. This experiment measures a short paced host detector and separate compact fits. Whole-recording real-time integration, concurrent detector and inference contention, and embedded memory and timings remain open. [Numeric stage figure](bounded-arrival.png) · [Stage data](stage.csv) · [Prediction seal](prediction-lock.json) · [Score seal](score-lock.json)
